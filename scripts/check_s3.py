#!/usr/bin/env python3
"""
Quick diagnostic script to check AWS S3 connectivity.
Run this to verify your S3 configuration is correct.
"""

import os
import sys
from pathlib import Path

# Load .env file from project root
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from: {env_file}\n")
    else:
        load_dotenv()  # Try current directory
except ImportError:
    print("Note: python-dotenv not installed. Run: pip install python-dotenv\n")

def check_environment():
    """Check if required environment variables are set."""
    print("=" * 50)
    print("Checking Environment Variables")
    print("=" * 50)

    required = {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    }

    optional = {
        "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
        "S3_BUCKET": os.environ.get("S3_BUCKET", "trustworthy-model-registry"),
    }

    all_set = True
    for key, value in required.items():
        if value:
            masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
            print(f"  ✓ {key}: {masked}")
        else:
            print(f"  ✗ {key}: NOT SET")
            all_set = False

    for key, value in optional.items():
        print(f"  • {key}: {value}")

    print()
    return all_set, optional["AWS_REGION"], optional["S3_BUCKET"]


def check_boto3():
    """Check if boto3 is installed."""
    print("Checking boto3 installation...")
    try:
        import boto3
        print(f"  ✓ boto3 version: {boto3.__version__}")
        return True
    except ImportError:
        print("  ✗ boto3 is not installed. Run: pip install boto3")
        return False


def check_s3_connection(region, bucket):
    """Test S3 connectivity."""
    print("=" * 50)
    print("Testing S3 Connection")
    print("=" * 50)

    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

    try:
        s3 = boto3.client("s3", region_name=region)

        # Test 1: List buckets (tests credentials)
        print("\n1. Testing AWS credentials...")
        try:
            response = s3.list_buckets()
            bucket_names = [b["Name"] for b in response["Buckets"]]
            print(f"   ✓ Credentials valid. Found {len(bucket_names)} bucket(s).")

            if bucket in bucket_names:
                print(f"   ✓ Target bucket '{bucket}' exists!")
            else:
                print(f"   ✗ Target bucket '{bucket}' NOT FOUND in your account.")
                print(f"     Available buckets: {', '.join(bucket_names) or 'None'}")
                print(f"\n   To create the bucket, run:")
                print(f"     aws s3 mb s3://{bucket} --region {region}")
                return False

        except NoCredentialsError:
            print("   ✗ No credentials found!")
            print("     Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            return False
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            print(f"   ✗ Credentials error: {error_code}")
            print(f"     {e}")
            return False

        # Test 2: Head bucket (tests bucket access)
        print(f"\n2. Testing access to bucket '{bucket}'...")
        try:
            s3.head_bucket(Bucket=bucket)
            print(f"   ✓ Bucket is accessible!")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                print(f"   ✗ Bucket '{bucket}' does not exist.")
                print(f"     Create it with: aws s3 mb s3://{bucket}")
            elif error_code == "403":
                print(f"   ✗ Access denied to bucket '{bucket}'.")
                print("     Check your IAM permissions.")
            else:
                print(f"   ✗ Error accessing bucket: {e}")
            return False

        # Test 3: Try to upload a test object
        print(f"\n3. Testing write access...")
        test_key = "_connectivity_test.txt"
        try:
            s3.put_object(
                Bucket=bucket,
                Key=test_key,
                Body=b"connectivity test",
                ContentType="text/plain"
            )
            print(f"   ✓ Write access OK!")

            # Clean up test object
            s3.delete_object(Bucket=bucket, Key=test_key)
            print(f"   ✓ Delete access OK!")

        except ClientError as e:
            print(f"   ✗ Write failed: {e}")
            return False

        # Test 4: Generate presigned URL
        print(f"\n4. Testing presigned URL generation...")
        try:
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": "test"},
                ExpiresIn=60
            )
            print(f"   ✓ Presigned URLs working!")
            print(f"     Example: {url[:60]}...")
        except Exception as e:
            print(f"   ✗ Presigned URL failed: {e}")
            return False

        return True

    except EndpointConnectionError:
        print("   ✗ Cannot connect to AWS. Check your internet connection.")
        return False
    except Exception as e:
        print(f"   ✗ Unexpected error: {e}")
        return False


def main():
    print("\n" + "=" * 50)
    print("  AWS S3 Connectivity Checker")
    print("=" * 50 + "\n")

    # Check environment
    env_ok, region, bucket = check_environment()
    if not env_ok:
        print("✗ Missing required environment variables!")
        print("\nSet them in your terminal:")
        print("  export AWS_ACCESS_KEY_ID=your-access-key")
        print("  export AWS_SECRET_ACCESS_KEY=your-secret-key")
        print("\nOr create a .env file in the project root.")
        sys.exit(1)

    # Check boto3
    if not check_boto3():
        sys.exit(1)

    print()

    # Test S3
    if check_s3_connection(region, bucket):
        print("\n" + "=" * 50)
        print("  ✓ ALL CHECKS PASSED!")
        print("=" * 50)
        print("\nYour S3 configuration is correct.")
        print("The frontend health page should show storage as 'healthy'.")
        sys.exit(0)
    else:
        print("\n" + "=" * 50)
        print("  ✗ S3 CHECK FAILED")
        print("=" * 50)
        print("\nFix the issues above, then restart the server.")
        sys.exit(1)


if __name__ == "__main__":
    main()

