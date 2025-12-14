# AWS EC2 Deployment Guide

This guide covers deploying the Trustworthy Model Registry to an AWS EC2 instance with S3 storage.

## Prerequisites

- AWS Account with EC2 and S3 access
- EC2 instance (t2.micro or larger) running Ubuntu 22.04
- S3 bucket created for artifact storage
- Domain name (optional, for HTTPS)

## EC2 Instance Setup

### 1. Launch EC2 Instance

Launch an EC2 instance with the following specifications:
- **AMI**: Ubuntu 22.04 LTS
- **Instance Type**: t2.micro (free tier) or t2.small for production
- **Security Group**: Allow inbound ports 22 (SSH), 80 (HTTP), 443 (HTTPS)
- **Storage**: 20GB minimum

### 2. Connect to Instance

```bash
ssh -i your-key.pem ubuntu@<ec2-public-ip>
```

### 3. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install nginx (reverse proxy)
sudo apt install -y nginx

# Install git
sudo apt install -y git
```

### 4. Clone Repository

```bash
cd ~
git clone https://github.com/your-org/your-repo.git app
cd app
```

### 5. Set Up Python Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 6. Configure Environment Variables

Create `/home/ubuntu/app/.env`:

```bash
# Database
DATABASE_URL=sqlite:///./registry.db

# AWS S3
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name

# Application
HOST=0.0.0.0
PORT=8000
```

### 7. Create Systemd Service

Create `/etc/systemd/system/model-registry.service`:

```ini
[Unit]
Description=Trustworthy Model Registry
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/app
Environment="PATH=/home/ubuntu/app/venv/bin"
EnvironmentFile=/home/ubuntu/app/.env
ExecStart=/home/ubuntu/app/venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable model-registry
sudo systemctl start model-registry
```

### 8. Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/model-registry`:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Or use EC2 public IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # Serve static files directly
    location /static/ {
        alias /home/ubuntu/app/static/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/model-registry /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove default site
sudo nginx -t  # Test configuration
sudo systemctl restart nginx
```

## S3 Bucket Setup

### 1. Create S3 Bucket

```bash
aws s3 mb s3://your-bucket-name --region us-east-1
```

### 2. Configure CORS (if needed)

Create `cors.json`:

```json
{
    "CORSRules": [
        {
            "AllowedOrigins": ["*"],
            "AllowedMethods": ["GET", "PUT", "POST"],
            "AllowedHeaders": ["*"],
            "MaxAgeSeconds": 3600
        }
    ]
}
```

Apply CORS:

```bash
aws s3api put-bucket-cors --bucket your-bucket-name --cors-configuration file://cors.json
```

### 3. IAM Policy for EC2

Create an IAM role with this policy and attach to EC2:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                "s3:HeadBucket"
            ],
            "Resource": [
                "arn:aws:s3:::your-bucket-name",
                "arn:aws:s3:::your-bucket-name/*"
            ]
        }
    ]
}
```

## Verification

### Check Service Status

```bash
sudo systemctl status model-registry
```

### Check Logs

```bash
sudo journalctl -u model-registry -f
```

### Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# API docs
curl http://localhost:8000/docs
```

## Updating the Application

### Manual Update

```bash
cd ~/app
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart model-registry
```

### Automated via GitHub Actions

The repository includes a GitHub Actions workflow for automated deployment. Configure these secrets in your repository:

- `EC2_HOST`: Your EC2 public IP or domain
- `EC2_USER`: `ubuntu`
- `EC2_SSH_KEY`: Your private SSH key

## Troubleshooting

### Application Won't Start

```bash
# Check logs
sudo journalctl -u model-registry -n 50

# Test manually
cd ~/app
source venv/bin/activate
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### Nginx 502 Bad Gateway

```bash
# Check if app is running
curl http://127.0.0.1:8000/health

# Check nginx logs
sudo tail -f /var/log/nginx/error.log
```

### S3 Connection Issues

```bash
# Test S3 connectivity
aws s3 ls s3://your-bucket-name

# Check environment variables
cat ~/app/.env
```

## Security Recommendations

1. **Enable HTTPS**: Use Let's Encrypt with Certbot
2. **Firewall**: Configure UFW to only allow necessary ports
3. **Updates**: Keep system and dependencies updated
4. **Monitoring**: Set up CloudWatch for logs and metrics
5. **Backups**: Schedule regular database backups

```bash
# Install certbot for HTTPS
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

