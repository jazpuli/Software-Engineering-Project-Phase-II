"""S3 storage adapter for artifact blob storage."""

import os
from typing import Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# S3 configuration from environment variables
S3_BUCKET = os.environ.get("S3_BUCKET", "trustworthy-model-registry")
S3_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")  # For local testing with moto/localstack

# Initialize S3 client
_s3_client = None


def get_s3_client():
    """Get or create S3 client (lazy initialization)."""
    global _s3_client
    if _s3_client is None:
        kwargs = {
            "region_name": S3_REGION,
        }
        if S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = S3_ENDPOINT_URL

        try:
            _s3_client = boto3.client("s3", **kwargs)
        except NoCredentialsError:
            # Return None if no credentials configured
            return None
    return _s3_client


def upload_object(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    Upload an object to S3.

    Args:
        key: S3 object key (path within bucket)
        data: File content as bytes
        content_type: MIME type of the content

    Returns:
        The S3 key where the object was stored

    Raises:
        RuntimeError: If upload fails
    """
    client = get_s3_client()
    if client is None:
        raise RuntimeError("S3 client not configured (missing credentials)")

    try:
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key
    except ClientError as e:
        raise RuntimeError(f"Failed to upload to S3: {e}")


def get_download_url(key: str, expires_in: int = 3600) -> str:
    """
    Get a download URL for an S3 object.

    For MVP, returns a presigned URL valid for the specified duration.

    Args:
        key: S3 object key
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned download URL
    """
    client = get_s3_client()
    if client is None:
        # Return a placeholder URL if S3 not configured
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"

    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
        return url
    except ClientError:
        # Fallback to public URL format
        return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"


def delete_object(key: str) -> bool:
    """
    Delete an object from S3.

    Args:
        key: S3 object key to delete

    Returns:
        True if deletion succeeded, False otherwise
    """
    client = get_s3_client()
    if client is None:
        return False

    try:
        client.delete_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError:
        return False


def get_object_size(key: str) -> Optional[int]:
    """
    Get the size of an S3 object in bytes.

    Args:
        key: S3 object key

    Returns:
        Size in bytes, or None if object not found
    """
    client = get_s3_client()
    if client is None:
        return None

    try:
        response = client.head_object(Bucket=S3_BUCKET, Key=key)
        return response.get("ContentLength")
    except ClientError:
        return None


def check_health() -> bool:
    """
    Check S3 connectivity.

    Returns:
        True if S3 is reachable, False otherwise
    """
    client = get_s3_client()
    if client is None:
        return False

    try:
        # Try to list bucket (or head bucket for faster check)
        client.head_bucket(Bucket=S3_BUCKET)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        # 404 means bucket doesn't exist, 403 means no permission
        # Both indicate S3 is reachable but there's a configuration issue
        if error_code in ("404", "403"):
            return True  # S3 is reachable
        return False
    except Exception:
        return False


def ensure_bucket_exists():
    """Create the S3 bucket if it doesn't exist (for testing/setup)."""
    client = get_s3_client()
    if client is None:
        return False

    try:
        client.head_bucket(Bucket=S3_BUCKET)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "404":
            try:
                if S3_REGION == "us-east-1":
                    client.create_bucket(Bucket=S3_BUCKET)
                else:
                    client.create_bucket(
                        Bucket=S3_BUCKET,
                        CreateBucketConfiguration={"LocationConstraint": S3_REGION},
                    )
                return True
            except ClientError:
                return False
        return False

