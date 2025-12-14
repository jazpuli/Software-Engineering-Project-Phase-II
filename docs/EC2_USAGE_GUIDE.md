# EC2 Deployment Usage Guide

This guide covers deploying and managing the Trustworthy Model Registry on AWS EC2.

## Quick Reference

| Resource | Value |
|----------|-------|
| **Instance IP** | `52.90.170.225` |
| **Instance ID** | `i-024fd8b1be8e757b0` |
| **Region** | `us-east-1` |
| **SSH Key** | `~/.ssh/trustworthy-registry-key.pem` |

## Application URLs

| Endpoint | URL |
|----------|-----|
| Main App | http://52.90.170.225 |
| API Documentation | http://52.90.170.225/docs |
| Health Check | http://52.90.170.225/health |
| Direct API (port 8000) | http://52.90.170.225:8000 |

---

## Deployment Commands

### Initial Setup (Already Done)

```powershell
# Create EC2 instance
python scripts/setup_ec2.py

# Deploy application code
python scripts/deploy_to_ec2.py --ip-address 52.90.170.225 --key-file "$env:USERPROFILE\.ssh\trustworthy-registry-key.pem"
```

### Redeploy After Code Changes

After making local changes, redeploy with:

```powershell
python scripts/deploy_to_ec2.py --ip-address 52.90.170.225 --key-file "$env:USERPROFILE\.ssh\trustworthy-registry-key.pem"
```

---

## SSH Access

### Connect to the Instance

```powershell
ssh -i "$env:USERPROFILE\.ssh\trustworthy-registry-key.pem" ubuntu@52.90.170.225
```

### Common SSH Commands

```bash
# Check application status
sudo systemctl status trustworthy-registry

# View live logs
sudo journalctl -u trustworthy-registry -f

# Restart the application
sudo systemctl restart trustworthy-registry

# Stop the application
sudo systemctl stop trustworthy-registry

# Start the application
sudo systemctl start trustworthy-registry
```

---

## Server Paths

| Path | Description |
|------|-------------|
| `/opt/trustworthy-registry/` | Application root |
| `/opt/trustworthy-registry/venv/` | Python virtual environment |
| `/opt/trustworthy-registry/src/` | Source code |
| `/etc/systemd/system/trustworthy-registry.service` | Systemd service file |
| `/etc/nginx/sites-available/trustworthy-registry` | Nginx configuration |
| `/var/log/user-data.log` | Instance initialization log |

---

## API Testing Examples

### Test Health Endpoint

```powershell
Invoke-WebRequest -Uri "http://52.90.170.225/health" -UseBasicParsing | Select-Object -ExpandProperty Content
```

### Ingest a Model

```powershell
$body = @{
    url = "https://huggingface.co/bert-base-uncased"
    artifact_type = "model"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://52.90.170.225/ingest" -Method POST -Body $body -ContentType "application/json"
```

### List Artifacts

```powershell
Invoke-RestMethod -Uri "http://52.90.170.225/artifacts" -Method GET
```

### Search Artifacts

```powershell
Invoke-RestMethod -Uri "http://52.90.170.225/artifacts/search?query=bert" -Method GET
```

### Get Artifact Rating

```powershell
Invoke-RestMethod -Uri "http://52.90.170.225/artifacts/model/{artifact_id}/rating" -Method GET
```

---

## Troubleshooting

### Application Not Responding

1. Check if service is running:
   ```bash
   sudo systemctl status trustworthy-registry
   ```

2. Check application logs:
   ```bash
   sudo journalctl -u trustworthy-registry -n 100
   ```

3. Restart the service:
   ```bash
   sudo systemctl restart trustworthy-registry
   ```

### SSH Connection Issues

1. Verify security group allows port 22
2. Check key file permissions:
   ```powershell
   icacls "$env:USERPROFILE\.ssh\trustworthy-registry-key.pem" /inheritance:r /grant:r "$env:USERNAME:R"
   ```

3. Wait 2-3 minutes after instance creation for initialization

### Nginx Errors

```bash
# Test nginx configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx

# View nginx logs
sudo tail -50 /var/log/nginx/error.log
```

---

## Environment Variables

To add or modify environment variables, edit the systemd service:

```bash
sudo systemctl edit trustworthy-registry
```

Add your variables:
```ini
[Service]
Environment="AWS_ACCESS_KEY_ID=your_key"
Environment="AWS_SECRET_ACCESS_KEY=your_secret"
Environment="S3_BUCKET_NAME=your_bucket"
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart trustworthy-registry
```

---

## Cleanup

To delete all AWS resources:

```powershell
# Terminate the instance
aws ec2 terminate-instances --instance-ids i-024fd8b1be8e757b0

# Wait for termination, then delete security group
aws ec2 delete-security-group --group-name trustworthy-registry-sg

# Delete key pair
aws ec2 delete-key-pair --key-name trustworthy-registry-key
Remove-Item "$env:USERPROFILE\.ssh\trustworthy-registry-key.pem"
```

---

## Cost Management

| Resource | Free Tier | On-Demand Cost |
|----------|-----------|----------------|
| t2.micro | 750 hrs/month (12 months) | ~$0.0116/hr |
| 20 GB gp3 EBS | 30 GB free | ~$0.08/GB/month |

**Tip**: Stop the instance when not in use to save costs:
```powershell
aws ec2 stop-instances --instance-ids i-024fd8b1be8e757b0
aws ec2 start-instances --instance-ids i-024fd8b1be8e757b0
```
