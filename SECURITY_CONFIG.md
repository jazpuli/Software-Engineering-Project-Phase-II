# Security Configuration Guide

This document provides step-by-step instructions for implementing the security mitigations identified in the STRIDE threat analysis.

## Table of Contents

1. [HTTPS/TLS Configuration](#httpstls-configuration)
2. [S3 Bucket Security](#s3-bucket-security)
3. [IAM Least-Privilege Configuration](#iam-least-privilege-configuration)
4. [Application-Level Security (Already Implemented)](#application-level-security)

---

## HTTPS/TLS Configuration

**STRIDE Threats Addressed:**
- Spoofing Risk 1: Client identity spoofing via HTTP
- Information Disclosure Risk 1: Eavesdropping on HTTP traffic

### Option A: AWS Application Load Balancer (Recommended for Production)

1. **Request an SSL Certificate from ACM:**
   ```bash
   aws acm request-certificate \
     --domain-name your-domain.com \
     --validation-method DNS
   ```

2. **Create an Application Load Balancer:**
   - Go to EC2 > Load Balancers > Create Load Balancer
   - Choose "Application Load Balancer"
   - Configure HTTPS listener on port 443
   - Select your ACM certificate
   - Create target group pointing to your EC2 instance on port 8000

3. **Update Security Group:**
   ```bash
   # Allow HTTPS from anywhere
   aws ec2 authorize-security-group-ingress \
     --group-id sg-xxxxxxxx \
     --protocol tcp \
     --port 443 \
     --cidr 0.0.0.0/0
   
   # Restrict HTTP to ALB only (optional)
   aws ec2 authorize-security-group-ingress \
     --group-id sg-xxxxxxxx \
     --protocol tcp \
     --port 8000 \
     --source-group sg-alb-security-group
   ```

### Option B: Nginx Reverse Proxy with Let's Encrypt

1. **Install Nginx and Certbot:**
   ```bash
   sudo yum install nginx -y
   sudo yum install certbot python3-certbot-nginx -y
   ```

2. **Configure Nginx (`/etc/nginx/conf.d/registry.conf`):**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           return 301 https://$server_name$request_uri;
       }
   }
   
   server {
       listen 443 ssl http2;
       server_name your-domain.com;
       
       ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
       
       # Security headers
       add_header Strict-Transport-Security "max-age=31536000" always;
       add_header X-Content-Type-Options nosniff;
       add_header X-Frame-Options DENY;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

3. **Obtain Certificate:**
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```

---

## S3 Bucket Security

**STRIDE Threats Addressed:**
- Tampering Risk 1: Artifacts overwritten/deleted by unauthorized users
- Information Disclosure Risk 3: Publicly exposed S3 bucket

### Step 1: Block All Public Access

```bash
aws s3api put-public-access-block \
  --bucket trustworthy-model-registry \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### Step 2: Verify Public Access is Blocked

```bash
aws s3api get-public-access-block --bucket trustworthy-model-registry
```

Expected output:
```json
{
    "PublicAccessBlockConfiguration": {
        "BlockPublicAcls": true,
        "IgnorePublicAcls": true,
        "BlockPublicPolicy": true,
        "RestrictPublicBuckets": true
    }
}
```

### Step 3: Bucket Policy (Restrict to EC2 Role Only)

Create a bucket policy that only allows access from the EC2 instance role:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowEC2RoleOnly",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": [
                "arn:aws:s3:::trustworthy-model-registry",
                "arn:aws:s3:::trustworthy-model-registry/*"
            ],
            "Condition": {
                "StringNotEquals": {
                    "aws:PrincipalArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/TrustworthyRegistryEC2Role"
                }
            }
        }
    ]
}
```

Apply the policy:
```bash
aws s3api put-bucket-policy \
  --bucket trustworthy-model-registry \
  --policy file://bucket-policy.json
```

---

## IAM Least-Privilege Configuration

**STRIDE Threats Addressed:**
- Elevation of Privilege Risk 1: EC2 compromise leads to full S3/RDS access

### Step 1: Create Least-Privilege IAM Policy

Create a file `ec2-registry-policy.json`:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "S3ArtifactAccess",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:HeadObject"
            ],
            "Resource": "arn:aws:s3:::trustworthy-model-registry/*"
        },
        {
            "Sid": "S3BucketList",
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:HeadBucket"
            ],
            "Resource": "arn:aws:s3:::trustworthy-model-registry"
        },
        {
            "Sid": "CloudWatchLogs",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:log-group:/aws/ec2/trustworthy-registry:*"
        }
    ]
}
```

### Step 2: Create the IAM Role

```bash
# Create the role
aws iam create-role \
  --role-name TrustworthyRegistryEC2Role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Create the policy
aws iam create-policy \
  --policy-name TrustworthyRegistryPolicy \
  --policy-document file://ec2-registry-policy.json

# Attach the policy to the role
aws iam attach-role-policy \
  --role-name TrustworthyRegistryEC2Role \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/TrustworthyRegistryPolicy
```

### Step 3: Create Instance Profile and Attach to EC2

```bash
# Create instance profile
aws iam create-instance-profile \
  --instance-profile-name TrustworthyRegistryProfile

# Add role to instance profile
aws iam add-role-to-instance-profile \
  --instance-profile-name TrustworthyRegistryProfile \
  --role-name TrustworthyRegistryEC2Role

# Associate with EC2 instance
aws ec2 associate-iam-instance-profile \
  --instance-id i-xxxxxxxx \
  --iam-instance-profile Name=TrustworthyRegistryProfile
```

---

## Application-Level Security

The following security mitigations are **already implemented** in the application code:

### API Key Authentication (Spoofing - Risk 1)

**File:** `src/api/main.py`

API key authentication protects the API from unauthorized access:

```python
# Set the API key via environment variable
export API_KEY="your-secret-key-here"

# Clients must include the header:
# X-API-Key: your-secret-key-here
```

**To enable:**
1. Generate a secure key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Set environment variable: `export API_KEY="generated-key"`
3. Restart the application

**Public endpoints (no key required):**
- `/health` - Health checks
- `/docs` - API documentation
- `/static/*` - Static files
- `/` - Root redirect

### Generic Error Messages (Information Disclosure - Risk 2)

**File:** `src/api/main.py`

A global exception handler returns generic error messages to clients while logging detailed errors server-side:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_error(...)  # Detailed server-side logging
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."}
    )
```

### Request Logging with Audit Trail (Repudiation - Risk 1)

**File:** `src/api/services/logging.py`

All requests are logged with:
- Timestamp (UTC)
- Unique request ID (for correlation)
- Client IP address (including X-Forwarded-For)
- User-Agent header
- Request method, path, and body
- Response status code and latency

### Rate Limiting (DoS - Risk 1)

**File:** `src/api/main.py`, `src/api/routes/search.py`

Rate limiting is implemented using `slowapi`:
- Global rate limit protects all endpoints
- Stricter limits on expensive regex search operations
- ReDoS protection validates regex patterns before execution

### ReDoS Protection (DoS - Risk 1)

**File:** `src/api/routes/search.py`

The `is_safe_regex()` function rejects patterns known to cause catastrophic backtracking:
- Nested quantifiers: `(.*)+`, `(.+)*`
- Large repetition counts: `{100,}`
- Complex alternations: `(a|b)+`

---

## Security Checklist

Before going to production, verify:

- [ ] HTTPS is enabled (ALB or Nginx)
- [ ] HTTP redirects to HTTPS
- [ ] S3 bucket has public access blocked
- [ ] EC2 uses least-privilege IAM role
- [ ] Security groups restrict access appropriately
- [ ] CloudWatch logging is enabled
- [ ] Rate limiting is active (check with `pip list | grep slowapi`)

---

## Verification Commands

```bash
# Check S3 public access block
aws s3api get-public-access-block --bucket trustworthy-model-registry

# Check EC2 instance profile
aws ec2 describe-iam-instance-profile-associations

# Test HTTPS (should succeed)
curl -I https://your-domain.com/health

# Test HTTP redirect (should 301 to HTTPS)
curl -I http://your-domain.com/health
```
