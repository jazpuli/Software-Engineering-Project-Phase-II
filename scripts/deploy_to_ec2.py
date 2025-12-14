#!/usr/bin/env python3
"""
Deploy application code to an EC2 instance.

This script:
1. Syncs the local codebase to the EC2 instance
2. Installs/updates dependencies
3. Restarts the application service

Prerequisites:
- EC2 instance already created with setup_ec2.py
- SSH key available locally
- boto3 installed

Usage:
    python scripts/deploy_to_ec2.py --instance-id i-xxxxx --key-file ~/.ssh/trustworthy-registry-key.pem
    python scripts/deploy_to_ec2.py --ip-address 1.2.3.4 --key-file ~/.ssh/trustworthy-registry-key.pem
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Error: boto3 is not installed. Install it with: pip install boto3")
    sys.exit(1)


def load_credentials_from_tokens_file():
    """Load AWS credentials from scripts/tokens.txt if it exists."""
    script_dir = Path(__file__).parent
    tokens_file = script_dir / "tokens.txt"

    if not tokens_file.exists():
        return False

    print(f"Loading credentials from {tokens_file}...")
    loaded = False

    with open(tokens_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "AWS_SESSION_TOKEN"):
                    if not os.environ.get(key):
                        os.environ[key] = value
                        loaded = True

    if loaded:
        print("[OK] Credentials loaded from tokens.txt")
    return loaded


DEFAULT_REGION = "us-east-1"
DEFAULT_USER = "ubuntu"
REMOTE_PATH = "/opt/trustworthy-registry"

# Files and directories to exclude from sync
EXCLUDE_PATTERNS = [
    ".git",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".coverage",
    "*.egg-info",
    ".env",
    "venv",
    ".venv",
    "node_modules",
    ".idea",
    ".vscode",
    "*.db",
    "registry.db",
]


def get_instance_ip(instance_id: str, region: str) -> str:
    """Get the public IP address of an EC2 instance."""
    print(f"Looking up instance {instance_id}...")

    session = boto3.Session(region_name=region)
    ec2 = session.resource("ec2")

    instance = ec2.Instance(instance_id)

    if instance.state["Name"] != "running":
        raise Exception(f"Instance is not running. Current state: {instance.state['Name']}")

    if not instance.public_ip_address:
        raise Exception("Instance does not have a public IP address")

    print(f"[OK] Instance IP: {instance.public_ip_address}")
    return instance.public_ip_address


def run_ssh_command(ip: str, key_file: str, command: str, user: str = DEFAULT_USER) -> bool:
    """Run a command on the remote instance via SSH."""
    ssh_cmd = [
        "ssh",
        "-i", key_file,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        f"{user}@{ip}",
        command
    ]

    result = subprocess.run(ssh_cmd, capture_output=False)
    return result.returncode == 0


def should_exclude(file_path: str, base_path: str) -> bool:
    """Check if a file should be excluded from sync."""
    import fnmatch
    rel_path = os.path.relpath(file_path, base_path)
    rel_path_parts = rel_path.replace("\\", "/").split("/")

    for pattern in EXCLUDE_PATTERNS:
        # Check against full relative path
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        if fnmatch.fnmatch(rel_path.replace("\\", "/"), pattern):
            return True
        # Check against each path component
        for part in rel_path_parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def sync_files(ip: str, key_file: str, local_path: str, user: str = DEFAULT_USER):
    """Sync local files to the remote instance using zip + scp (Windows compatible)."""
    import zipfile
    import tempfile

    print(f"\nSyncing files to {ip}:{REMOTE_PATH}...")

    # Create a zip archive (works on all platforms)
    print("Creating deployment archive...")
    temp_dir = tempfile.gettempdir()
    zip_file = os.path.join(temp_dir, "deploy.zip")

    with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(local_path):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d), local_path)]

            for file in files:
                file_path = os.path.join(root, file)
                if not should_exclude(file_path, local_path):
                    arc_name = os.path.relpath(file_path, local_path)
                    zf.write(file_path, arc_name)

    print(f"Archive created: {zip_file}")

    # Copy the archive to the remote server
    print("Uploading archive to server...")
    scp_cmd = [
        "scp",
        "-i", key_file,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        zip_file,
        f"{user}@{ip}:/tmp/deploy.zip"
    ]
    result = subprocess.run(scp_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"scp failed: {result.stderr}")

    print("Extracting archive on server...")
    # Extract on remote (using unzip which should be available, or python)
    extract_cmd = f"sudo rm -rf {REMOTE_PATH}/* && cd {REMOTE_PATH} && sudo unzip -o /tmp/deploy.zip || sudo python3 -m zipfile -e /tmp/deploy.zip {REMOTE_PATH}"
    run_ssh_command(ip, key_file, extract_cmd)

    # Cleanup local zip
    os.remove(zip_file)

    print("[OK] Files synced successfully")


def setup_remote(ip: str, key_file: str, user: str = DEFAULT_USER):
    """Set up the remote environment and restart the service."""
    print("\nSetting up remote environment...")

    commands = [
        # Fix ownership
        f"sudo chown -R appuser:appuser {REMOTE_PATH}",

        # Activate venv and install/update dependencies
        f"cd {REMOTE_PATH} && sudo -u appuser bash -c 'source venv/bin/activate && pip install -r requirements.txt'",

        # Restart the service
        "sudo systemctl restart trustworthy-registry",

        # Check service status
        "sudo systemctl status trustworthy-registry --no-pager || true",
    ]

    for cmd in commands:
        print(f"  Running: {cmd[:60]}...")
        success = run_ssh_command(ip, key_file, cmd, user)
        if not success and "status" not in cmd:
            print(f"  [WARN] Command may have failed: {cmd}")

    print("[OK] Remote setup complete")


def verify_deployment(ip: str):
    """Verify that the application is running."""
    print("\nVerifying deployment...")

    import urllib.request
    import urllib.error

    urls = [
        f"http://{ip}/health",
        f"http://{ip}:8000/health",
    ]

    for url in urls:
        try:
            response = urllib.request.urlopen(url, timeout=10)
            if response.status == 200:
                print(f"[OK] Application is responding at {url}")
                return True
        except urllib.error.URLError:
            pass
        except Exception:
            pass

    print("[WARN] Application may not be responding yet. Check logs with:")
    print(f"  ssh -i <key-file> ubuntu@{ip} 'sudo journalctl -u trustworthy-registry -f'")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Deploy application to EC2 instance"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--instance-id",
        help="EC2 instance ID (will look up IP address)"
    )
    group.add_argument(
        "--ip-address",
        help="Direct IP address of the instance"
    )

    parser.add_argument(
        "--key-file",
        required=True,
        help="Path to SSH private key file"
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"AWS region (default: {DEFAULT_REGION})"
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_USER,
        help=f"SSH user (default: {DEFAULT_USER})"
    )
    parser.add_argument(
        "--local-path",
        default=str(Path(__file__).parent.parent),
        help="Local path to sync (default: project root)"
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip deployment verification"
    )

    args = parser.parse_args()

    # Validate key file
    key_file = Path(args.key_file).expanduser()
    if not key_file.exists():
        print(f"[ERROR] Key file not found: {key_file}")
        sys.exit(1)

    # Validate local path
    local_path = Path(args.local_path).resolve()
    if not local_path.exists():
        print(f"[ERROR] Local path not found: {local_path}")
        sys.exit(1)

    print("=" * 60)
    print("Trustworthy Model Registry - EC2 Deployment")
    print("=" * 60)

    # Load credentials from tokens.txt if available
    load_credentials_from_tokens_file()

    try:
        # Get IP address
        if args.instance_id:
            ip = get_instance_ip(args.instance_id, args.region)
        else:
            ip = args.ip_address
            print(f"Using IP address: {ip}")

        # Test SSH connection
        print(f"\nTesting SSH connection to {ip}...")
        if not run_ssh_command(ip, str(key_file), "echo 'SSH OK'", args.user):
            print("[ERROR] SSH connection failed. Make sure the instance is ready and the key file is correct.")
            sys.exit(1)
        print("[OK] SSH connection successful")

        # Sync files
        sync_files(ip, str(key_file), str(local_path), args.user)

        # Setup remote
        setup_remote(ip, str(key_file), args.user)

        # Verify deployment
        if not args.skip_verify:
            verify_deployment(ip)

        print("\n" + "=" * 60)
        print("DEPLOYMENT COMPLETE")
        print("=" * 60)
        print(f"\nApplication URLs:")
        print(f"  HTTP:      http://{ip}")
        print(f"  Direct:    http://{ip}:8000")
        print(f"  API Docs:  http://{ip}/docs")
        print(f"  Health:    http://{ip}/health")

    except Exception as e:
        print(f"\n[ERROR] Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
