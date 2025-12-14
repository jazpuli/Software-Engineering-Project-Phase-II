# EC2 Deployment Guide

This guide explains how to deploy the Trustworthy Model Registry to AWS EC2 using the provided boto3 scripts.

## Prerequisites

1. **AWS Account** with EC2 permissions
2. **AWS Credentials** configured via one of:
   - `scripts/tokens.txt` file (copy example and fill in your credentials)
   - `~/.aws/credentials` file
   - Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
   - IAM role (if running from AWS)

3. **Python 3.10+** with boto3 installed:
   ```bash
   pip install boto3
   ```

4. **SSH client** available (for deployment script)

## Setting Up Credentials

Edit `scripts/tokens.txt` with your AWS credentials:

```bash
# Windows (PowerShell)
notepad scripts/tokens.txt

# Then load them as environment variables:
Get-Content scripts/tokens.txt | ForEach-Object { if ($_ -match '^([^#].+?)=(.+)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }

# Linux/Mac
source <(grep -v '^#' scripts/tokens.txt | sed 's/^/export /')
```

## Quick Start

### 1. Create the EC2 Instance

```bash
# Basic usage (uses defaults: us-east-1, t2.micro)
python scripts/setup_ec2.py

# Custom configuration
python scripts/setup_ec2.py \
    --region us-west-2 \
    --instance-type t3.small \
    --key-name my-key \
    --instance-name MyRegistry

# Dry run (validate without creating resources)
python scripts/setup_ec2.py --dry-run
```

### 2. Deploy the Application

After the instance is running (wait 2-3 minutes for initialization):

```bash
# Using instance ID
python scripts/deploy_to_ec2.py \
    --instance-id i-0123456789abcdef0 \
    --key-file ~/.ssh/trustworthy-registry-key.pem

# Using IP address directly
python scripts/deploy_to_ec2.py \
    --ip-address 54.123.45.67 \
    --key-file ~/.ssh/trustworthy-registry-key.pem
```

## Script Details

### setup_ec2.py

Creates all necessary AWS resources:

| Resource | Description |
|----------|-------------|
| **Key Pair** | SSH key for instance access (saved to `~/.ssh/`) |
| **Security Group** | Opens ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 8000 (API) |
| **EC2 Instance** | Ubuntu 22.04 LTS with Python, Nginx, and systemd service configured |

**Command Line Options:**

```
--region          AWS region (default: us-east-1)
--instance-type   EC2 instance type (default: t2.micro)
--key-name        SSH key pair name (default: trustworthy-registry-key)
--key-path        Directory to save key (default: ~/.ssh)
--security-group  Security group name (default: trustworthy-registry-sg)
--instance-name   EC2 instance name tag
--dry-run         Validate without creating resources
```

### deploy_to_ec2.py

Deploys application code to an existing instance:

1. Syncs local files using rsync (or scp fallback)
2. Updates Python dependencies
3. Restarts the application service
4. Verifies deployment

**Command Line Options:**

```
--instance-id     EC2 instance ID (looks up IP automatically)
--ip-address      Direct IP address (alternative to instance-id)
--key-file        Path to SSH private key (required)
--region          AWS region (default: us-east-1)
--user            SSH user (default: ubuntu)
--local-path      Local path to sync (default: project root)
--skip-verify     Skip deployment verification
```

## Instance Configuration

The EC2 instance is configured with:

- **Ubuntu 22.04 LTS**
- **Python 3.11** with virtual environment at `/opt/trustworthy-registry/venv`
- **Nginx** as reverse proxy (port 80 → 8000)
- **Systemd service** for automatic startup and restart

### Service Management

```bash
# SSH into the instance
ssh -i ~/.ssh/trustworthy-registry-key.pem ubuntu@<IP>

# View application logs
sudo journalctl -u trustworthy-registry -f

# Restart the application
sudo systemctl restart trustworthy-registry

# Check service status
sudo systemctl status trustworthy-registry

# View initialization logs
sudo cat /var/log/user-data.log
```

### Application Paths

| Path | Description |
|------|-------------|
| `/opt/trustworthy-registry/` | Application root |
| `/opt/trustworthy-registry/venv/` | Python virtual environment |
| `/etc/systemd/system/trustworthy-registry.service` | Systemd service file |
| `/etc/nginx/sites-available/trustworthy-registry` | Nginx configuration |
| `/var/log/user-data.log` | Instance initialization log |

## Environment Variables

The application uses these environment variables (configured in systemd service):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

To add custom environment variables, edit the systemd service:

```bash
sudo systemctl edit trustworthy-registry
```

Add:
```ini
[Service]
Environment="MY_VAR=value"
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart trustworthy-registry
```

## Security Considerations

### Production Recommendations

1. **Restrict SSH access**: Edit the security group to limit SSH (port 22) to your IP only
2. **Enable HTTPS**: Set up SSL/TLS with Let's Encrypt or AWS Certificate Manager
3. **Use IAM roles**: Instead of embedding AWS credentials
4. **Enable CloudWatch**: For monitoring and alerting
5. **Regular updates**: Keep the system packages updated

### Restricting SSH Access

```python
# In setup_ec2.py, change the SSH rule:
{
    "IpProtocol": "tcp",
    "FromPort": 22,
    "ToPort": 22,
    "IpRanges": [{"CidrIp": "YOUR_IP/32", "Description": "SSH from my IP only"}]
}
```

## Troubleshooting

### Instance won't start
- Check AWS service quotas
- Verify the AMI ID is valid for your region
- Check IAM permissions

### SSH connection refused
- Wait for instance initialization (2-3 minutes)
- Verify security group allows port 22
- Check key file permissions (`chmod 400 key.pem`)

### Application not responding
- Check if service is running: `sudo systemctl status trustworthy-registry`
- Check logs: `sudo journalctl -u trustworthy-registry -n 100`
- Verify Nginx: `sudo nginx -t && sudo systemctl status nginx`

### Deployment fails
- Ensure rsync or tar is available locally
- Check SSH connectivity: `ssh -i key.pem ubuntu@IP`
- Verify file permissions on the instance

## Cost Estimation

| Resource | Free Tier | On-Demand (us-east-1) |
|----------|-----------|----------------------|
| t2.micro | 750 hrs/month | ~$0.0116/hr |
| t3.small | - | ~$0.0208/hr |
| t3.medium | - | ~$0.0416/hr |
| 20 GB gp3 EBS | 30 GB free | ~$0.08/GB/month |

**Tip**: Use `t2.micro` for development/testing (free tier eligible for 12 months).

## Cleanup

To delete all created resources:

```bash
# Terminate instance (via AWS Console or CLI)
aws ec2 terminate-instances --instance-ids i-xxxxx

# Delete security group (after instance terminated)
aws ec2 delete-security-group --group-name trustworthy-registry-sg

# Delete key pair
aws ec2 delete-key-pair --key-name trustworthy-registry-key
rm ~/.ssh/trustworthy-registry-key.pem
```
