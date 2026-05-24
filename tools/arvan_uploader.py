"""
ArvanCloud Object Storage uploader module.

Uploads files to ArvanCloud Object Storage using the S3-compatible API
with boto3.  ArvanCloud provides 50 GB free bandwidth per month and
1 million requests, with unlimited upload sizes via the API.  Public
bucket links provide direct download access.

Configuration (via environment variables):
    ARVAN_ACCESS_KEY: S3-compatible access key from ArvanCloud panel.
    ARVAN_SECRET_KEY: S3-compatible secret key from ArvanCloud panel.
    ARVAN_BUCKET: Bucket name (must exist and be publicly readable).
    ARVAN_ENDPOINT: S3 endpoint (default: s3.ir-thr-at1.arvanstorage.ir).
    ARVAN_VALID_DAYS: Delete objects older than N days (default: 0 = disabled).
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ArvanCloud S3 default endpoint (Tehran region)
ARVAN_DEFAULT_ENDPOINT = "s3.ir-thr-at1.arvanstorage.ir"
ARVAN_MAX_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB (practical single-request limit)

MB = 1024 * 1024


async def upload(file_path: Path) -> str:
    """Upload a file to ArvanCloud Object Storage via S3 API.

    Uses boto3 to PUT the object into the configured bucket.  The bucket
    must already exist and have public-read ACL for direct download links.

    Args:
        file_path: Path to the file to upload.

    Returns:
        A direct download URL string.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If the upload fails or configuration is missing.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    access_key = os.getenv("ARVAN_ACCESS_KEY")
    secret_key = os.getenv("ARVAN_SECRET_KEY")
    bucket = os.getenv("ARVAN_BUCKET")
    endpoint = os.getenv("ARVAN_ENDPOINT", ARVAN_DEFAULT_ENDPOINT)

    if not access_key:
        raise RuntimeError("ARVAN_ACCESS_KEY environment variable is not set")
    if not secret_key:
        raise RuntimeError("ARVAN_SECRET_KEY environment variable is not set")
    if not bucket:
        raise RuntimeError("ARVAN_BUCKET environment variable is not set")

    file_size = file_path.stat().st_size
    file_size_mb = file_size / MB
    logger.info("Uploading to ArvanCloud: %s (%.2f MB)", file_path.name, file_size_mb)

    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                connect_timeout=60,
                read_timeout=1800,  # 30 min for large files
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )

        object_key = f"hybrid-rar-bridge/{file_path.name}"

        with open(file_path, "rb") as f:
            s3.upload_fileobj(f, bucket, object_key)

        download_url = f"https://{bucket}.{endpoint}/{object_key}"
        logger.info("ArvanCloud upload successful: %s", download_url)
        return download_url

    except ImportError:
        raise RuntimeError(
            "boto3 package is required for ArvanCloud uploads. "
            "Install it with: pip install boto3"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to upload {file_path.name} to ArvanCloud: {e}") from e


async def cleanup_old_files(valid_days: int) -> int:
    """Delete objects older than *valid_days* from the ArvanCloud bucket.

    Only objects under the ``hybrid-rar-bridge/`` prefix are considered,
    so other bucket contents remain untouched.

    Args:
        valid_days: Minimum age (in days) for files to be deleted.

    Returns:
        Number of objects deleted.
    """
    if valid_days <= 0:
        return 0

    access_key = os.getenv("ARVAN_ACCESS_KEY")
    secret_key = os.getenv("ARVAN_SECRET_KEY")
    bucket = os.getenv("ARVAN_BUCKET")
    endpoint = os.getenv("ARVAN_ENDPOINT", ARVAN_DEFAULT_ENDPOINT)

    if not all([access_key, secret_key, bucket]):
        return 0

    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(connect_timeout=30, read_timeout=60),
        )

        cutoff = datetime.now(timezone.utc).timestamp() - (valid_days * 86400)
        prefix = "hybrid-rar-bridge/"
        deleted_count = 0

        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects_to_delete = []
            for obj in page.get("Contents", []):
                last_modified = obj["LastModified"].timestamp()
                if last_modified < cutoff:
                    objects_to_delete.append({"Key": obj["Key"]})

            if objects_to_delete:
                s3.delete_objects(
                    Bucket=bucket, Delete={"Objects": objects_to_delete}
                )
                deleted_count += len(objects_to_delete)
                logger.info(
                    "ArvanCloud cleanup: deleted %d objects older than %d days",
                    len(objects_to_delete),
                    valid_days,
                )

        return deleted_count

    except ImportError:
        logger.warning("boto3 not installed, skipping ArvanCloud cleanup")
        return 0
    except Exception as e:
        logger.error("ArvanCloud cleanup failed: %s", e)
        return 0
