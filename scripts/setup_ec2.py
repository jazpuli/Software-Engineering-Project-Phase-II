#!/usr/bin/env python3
"""
EC2 Instance Setup Script for Trustworthy Model Registry

This script uses boto3 to:
1. Create a security group with necessary ports
2. Create a key pair for SSH access
3. Launch an EC2 instance with user data to set up the application
4. Wait for the instance to be running and output connection details

Prerequisites:
- AWS credentials configured (via scripts/tokens.txt, ~/.aws/credentials, environment variables, or IAM role)
- boto3 installed (pip install boto3)

Usage:
    python scripts/setup_ec2.py [--region REGION] [--instance-type TYPE] [--key-name NAME]
"""

import argparse
import os
import sys
import time
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Error: boto3 is not installed. Install it with: pip install boto3")
    sys.exit(1)


def load_credentials_from_tokens_file():
    """Load AWS credentials from scripts/tokens.txt if it exists."""
    # Try to find tokens.txt relative to this script
    script_dir = Path(__file__).parent
    tokens_file = script_dir / "tokens.txt"

    if not tokens_file.exists():
        return False

    print(f"Loading credentials from {tokens_file}...")
    loaded = False

    with open(tokens_file, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE format
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Only set if not already in environment
                if key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "AWS_SESSION_TOKEN"):
                    if not os.environ.get(key):
                        os.environ[key] = value
                        loaded = True

    if loaded:
        print("✓ Credentials loaded from tokens.txt")
    return loaded


# Default configuration
DEFAULT_REGION = "us-east-1"
DEFAULT_INSTANCE_TYPE = "t2.micro"  # Free tier eligible
DEFAULT_KEY_NAME = "trustworthy-registry-key"
DEFAULT_SECURITY_GROUP_NAME = "trustworthy-registry-sg"

# Ubuntu 22.04 LTS AMI IDs by region (update as needed)
# These are official Ubuntu AMIs - you can find updated ones at https://cloud-images.ubuntu.com/locator/ec2/
UBUNTU_AMIS = {
    "us-east-1": "ami-0c7217cdde317cfec",  # Ubuntu 22.04 LTS
    "us-east-2": "ami-05fb0b8c1424f266b",
    "us-west-1": "ami-0ce2cb35386fc22e9",
    "us-west-2": "ami-008fe2fc65df48dac",
    "eu-west-1": "ami-0905a3c97561e0b69",
    "eu-central-1": "ami-0faab6bdbac9486fb",
    "ap-southeast-1": "ami-078c1149d8ad719a7",
    "ap-northeast-1": "ami-07c589821f2b353aa",
}

# User data script to set up the instance
USER_DATA_SCRIPT = """#!/bin/bash
set -e

# Log everything to a file for debugging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "=== Starting EC2 Instance Setup ==="

# Update system packages
echo "Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Install required system packages
echo "Installing system dependencies..."
apt-get install -y python3.11 python3.11-venv python3-pip git nginx

# Create application user
echo "Creating application user..."
useradd -m -s /bin/bash appuser || true

# Create application directory
echo "Setting up application directory..."
mkdir -p /opt/trustworthy-registry
chown appuser:appuser /opt/trustworthy-registry

# Clone or copy the application (using a placeholder - update with your repo URL)
echo "Setting up application..."
cd /opt/trustworthy-registry

# Create virtual environment
echo "Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Create requirements file
cat > requirements.txt << 'EOF'
huggingface_hub>=0.24
requests>=2.31
pytest>=8.0
gitpython>=3.1.0
PyGithub>=2.0.0
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0.25
boto3>=1.34.0
pydantic>=2.5.0
python-multipart>=0.0.6
python-dotenv>=1.0.0
EOF

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create systemd service file
echo "Creating systemd service..."
cat > /etc/systemd/system/trustworthy-registry.service << 'EOF'
[Unit]
Description=Trustworthy Model Registry API
After=network.target

[Service]
Type=simple
User=appuser
Group=appuser
WorkingDirectory=/opt/trustworthy-registry
Environment="PATH=/opt/trustworthy-registry/venv/bin"
Environment="HOST=0.0.0.0"
Environment="PORT=8000"
ExecStart=/opt/trustworthy-registry/venv/bin/python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx as reverse proxy
echo "Configuring Nginx..."
cat > /etc/nginx/sites-available/trustworthy-registry << 'EOF'
server {
    listen 80;
    server_name _;

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
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/trustworthy-registry /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and reload Nginx
nginx -t
systemctl restart nginx
systemctl enable nginx

# Set proper ownership
chown -R appuser:appuser /opt/trustworthy-registry

echo "=== EC2 Instance Setup Complete ==="
echo "Note: You need to deploy your application code to /opt/trustworthy-registry"
echo "Then run: sudo systemctl start trustworthy-registry"
"""


def get_or_create_key_pair(ec2_client, key_name: str, save_path: str) -> str:
    """Create a new key pair or use existing one."""
    key_file = Path(save_path) / f"{key_name}.pem"

    try:
        # Check if key pair already exists
        ec2_client.describe_key_pairs(KeyNames=[key_name])
        print(f"✓ Key pair '{key_name}' already exists")

        if not key_file.exists():
            print(f"⚠ Warning: Key file {key_file} not found locally. You may not be able to SSH.")
        return key_name

    except ClientError as e:
        if "InvalidKeyPair.NotFound" in str(e):
            print(f"Creating new key pair: {key_name}")

            # Create the key pair
            response = ec2_client.create_key_pair(KeyName=key_name)
            private_key = response["KeyMaterial"]

            # Save the private key
            key_file.write_text(private_key)
            os.chmod(key_file, 0o400)  # Set restrictive permissions

            print(f"✓ Key pair created and saved to: {key_file}")
            return key_name
        else:
            raise


def get_or_create_security_group(ec2_client, group_name: str, vpc_id: str = None) -> str:
    """Create a security group with necessary ports or use existing one."""

    try:
        # Check if security group already exists
        if vpc_id:
            response = ec2_client.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [group_name]},
                    {"Name": "vpc-id", "Values": [vpc_id]}
                ]
            )
        else:
            response = ec2_client.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": [group_name]}]
            )

        if response["SecurityGroups"]:
            security_group_id = response["SecurityGroups"][0]["GroupId"]
            print(f"✓ Security group '{group_name}' already exists: {security_group_id}")
            return security_group_id

    except ClientError:
        pass

    # Get default VPC if not specified
    if not vpc_id:
        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        if vpcs["Vpcs"]:
            vpc_id = vpcs["Vpcs"][0]["VpcId"]
        else:
            # Use first available VPC
            vpcs = ec2_client.describe_vpcs()
            if vpcs["Vpcs"]:
                vpc_id = vpcs["Vpcs"][0]["VpcId"]
            else:
                raise Exception("No VPC found. Please create a VPC first.")

    print(f"Creating security group: {group_name}")

    # Create the security group
    response = ec2_client.create_security_group(
        GroupName=group_name,
        Description="Security group for Trustworthy Model Registry",
        VpcId=vpc_id
    )
    security_group_id = response["GroupId"]

    # Add inbound rules
    ingress_rules = [
        # SSH access
        {
            "IpProtocol": "tcp",
            "FromPort": 22,
            "ToPort": 22,
            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH access"}]
        },
        # HTTP access (Nginx)
        {
            "IpProtocol": "tcp",
            "FromPort": 80,
            "ToPort": 80,
            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTP access"}]
        },
        # HTTPS access
        {
            "IpProtocol": "tcp",
            "FromPort": 443,
            "ToPort": 443,
            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS access"}]
        },
        # Direct API access (for development/testing)
        {
            "IpProtocol": "tcp",
            "FromPort": 8000,
            "ToPort": 8000,
            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Direct API access"}]
        },
    ]

    ec2_client.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpPermissions=ingress_rules
    )

    print(f"✓ Security group created: {security_group_id}")
    print("  - Port 22 (SSH)")
    print("  - Port 80 (HTTP)")
    print("  - Port 443 (HTTPS)")
    print("  - Port 8000 (API)")

    return security_group_id


def get_ami_id(ec2_client, region: str) -> str:
    """Get the appropriate AMI ID for the region."""
    # Try to use predefined AMI
    if region in UBUNTU_AMIS:
        ami_id = UBUNTU_AMIS[region]
        print(f"Using predefined Ubuntu AMI: {ami_id}")
        return ami_id

    # Search for Ubuntu 22.04 AMI
    print(f"Searching for Ubuntu 22.04 AMI in {region}...")
    response = ec2_client.describe_images(
        Filters=[
            {"Name": "name", "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]},
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
        ],
        Owners=["099720109477"]  # Canonical's AWS account ID
    )

    if not response["Images"]:
        raise Exception(f"No Ubuntu AMI found in region {region}")

    # Get the most recent AMI
    images = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)
    ami_id = images[0]["ImageId"]
    print(f"Found Ubuntu AMI: {ami_id}")
    return ami_id


def launch_instance(
    ec2_client,
    ec2_resource,
    ami_id: str,
    instance_type: str,
    key_name: str,
    security_group_id: str,
    instance_name: str = "TrustworthyModelRegistry"
) -> dict:
    """Launch an EC2 instance with the specified configuration."""

    print(f"\nLaunching EC2 instance...")
    print(f"  AMI: {ami_id}")
    print(f"  Instance Type: {instance_type}")
    print(f"  Key Pair: {key_name}")
    print(f"  Security Group: {security_group_id}")

    # Launch the instance
    instances = ec2_resource.create_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        KeyName=key_name,
        SecurityGroupIds=[security_group_id],
        MinCount=1,
        MaxCount=1,
        UserData=USER_DATA_SCRIPT,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": instance_name},
                    {"Key": "Project", "Value": "TrustworthyModelRegistry"},
                    {"Key": "Environment", "Value": "production"},
                ]
            }
        ],
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 20,  # GB
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                }
            }
        ]
    )

    instance = instances[0]
    instance_id = instance.id

    print(f"✓ Instance launched: {instance_id}")
    print("Waiting for instance to be running...")

    # Wait for the instance to be running
    instance.wait_until_running()
    instance.reload()

    print(f"✓ Instance is running!")

    return {
        "instance_id": instance_id,
        "public_ip": instance.public_ip_address,
        "public_dns": instance.public_dns_name,
        "private_ip": instance.private_ip_address,
        "state": instance.state["Name"],
    }


def print_summary(instance_info: dict, key_name: str, key_path: str, region: str):
    """Print a summary of the deployed instance."""
    print("\n" + "=" * 60)
    print("EC2 INSTANCE DEPLOYMENT COMPLETE")
    print("=" * 60)
    print(f"\nInstance Details:")
    print(f"  Instance ID:  {instance_info['instance_id']}")
    print(f"  State:        {instance_info['state']}")
    print(f"  Public IP:    {instance_info['public_ip']}")
    print(f"  Public DNS:   {instance_info['public_dns']}")
    print(f"  Private IP:   {instance_info['private_ip']}")
    print(f"  Region:       {region}")

    print(f"\nSSH Connection:")
    key_file = Path(key_path) / f"{key_name}.pem"
    print(f"  ssh -i \"{key_file}\" ubuntu@{instance_info['public_ip']}")

    print(f"\nApplication URLs (after deployment):")
    print(f"  HTTP:      http://{instance_info['public_ip']}")
    print(f"  Direct:    http://{instance_info['public_ip']}:8000")
    print(f"  API Docs:  http://{instance_info['public_ip']}/docs")
    print(f"  Health:    http://{instance_info['public_ip']}/health")

    print(f"\nNext Steps:")
    print("  1. Wait 2-3 minutes for the instance initialization to complete")
    print("  2. SSH into the instance")
    print("  3. Clone your repository to /opt/trustworthy-registry:")
    print("     cd /opt/trustworthy-registry")
    print("     sudo git clone <your-repo-url> .")
    print("     sudo chown -R appuser:appuser /opt/trustworthy-registry")
    print("  4. Start the application:")
    print("     sudo systemctl start trustworthy-registry")
    print("     sudo systemctl enable trustworthy-registry")
    print("  5. Check logs if needed:")
    print("     sudo journalctl -u trustworthy-registry -f")
    print("     sudo cat /var/log/user-data.log")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy Trustworthy Model Registry to AWS EC2"
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"AWS region (default: {DEFAULT_REGION})"
    )
    parser.add_argument(
        "--instance-type",
        default=DEFAULT_INSTANCE_TYPE,
        help=f"EC2 instance type (default: {DEFAULT_INSTANCE_TYPE})"
    )
    parser.add_argument(
        "--key-name",
        default=DEFAULT_KEY_NAME,
        help=f"Name for the SSH key pair (default: {DEFAULT_KEY_NAME})"
    )
    parser.add_argument(
        "--key-path",
        default=str(Path.home() / ".ssh"),
        help="Directory to save the key pair (default: ~/.ssh)"
    )
    parser.add_argument(
        "--security-group",
        default=DEFAULT_SECURITY_GROUP_NAME,
        help=f"Security group name (default: {DEFAULT_SECURITY_GROUP_NAME})"
    )
    parser.add_argument(
        "--instance-name",
        default="TrustworthyModelRegistry",
        help="Name tag for the EC2 instance"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without launching instance"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Trustworthy Model Registry - EC2 Deployment")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Region:         {args.region}")
    print(f"  Instance Type:  {args.instance_type}")
    print(f"  Key Name:       {args.key_name}")
    print(f"  Security Group: {args.security_group}")

    # Ensure key path exists
    key_path = Path(args.key_path)
    key_path.mkdir(parents=True, exist_ok=True)

    try:
        # Load credentials from tokens.txt if available
        load_credentials_from_tokens_file()

        # Initialize boto3 clients
        print("\nInitializing AWS clients...")
        session = boto3.Session(region_name=args.region)
        ec2_client = session.client("ec2")
        ec2_resource = session.resource("ec2")

        # Verify AWS credentials
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        print(f"✓ AWS Account: {identity['Account']}")
        print(f"✓ User/Role: {identity['Arn']}")

        if args.dry_run:
            print("\n[DRY RUN] Configuration validated. No resources will be created.")
            return

        # Create or get key pair
        key_name = get_or_create_key_pair(ec2_client, args.key_name, str(key_path))

        # Create or get security group
        security_group_id = get_or_create_security_group(ec2_client, args.security_group)

        # Get AMI ID
        ami_id = get_ami_id(ec2_client, args.region)

        # Launch the instance
        instance_info = launch_instance(
            ec2_client,
            ec2_resource,
            ami_id,
            args.instance_type,
            key_name,
            security_group_id,
            args.instance_name
        )

        # Print summary
        print_summary(instance_info, key_name, str(key_path), args.region)

    except ClientError as e:
        print(f"\n❌ AWS Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
