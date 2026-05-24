"""
Liara Object Storage uploader module.

Uploads files to Liara.ir Object Storage using the presigned-URL REST
API.  Liara offers a limited free tier (PAYG after that) with direct
download links.

Workflow:
    1.  POST to Liara to obtain a presigned PUT URL.
    2.  PUT the file body to the presigned URL.
    3.  The object is immediately available at the download URL.

Configuration (via environment variables):
    LIARA_API_KEY:       API key from the Liara dashboard.
    LIARA_BUCKET:       Bucket name (must already exist).
    LIARA_ENDPOINT:     API base URL (default: https://storage.iran.liara.ir).
    LIARA_VALID_DAYS:   Delete objects older than N days (default: 0 = off).
"""

import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

LIARA_DEFAULT_ENDPOINT = "https://storage.iran.liara.ir"
LIARA_MAX_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB

MB = 1024 * 1024


async def upload(file_path: Path) -> str:
    """Upload a file to Liara Object Storage via presigned URL.

    Requests a presigned PUT URL from the Liara API, uploads the file
    to that URL, and returns the direct download link.

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

    api_key = os.getenv("LIARA_API_KEY")
    bucket = os.getenv("LIARA_BUCKET")
    endpoint = os.getenv("LIARA_ENDPOINT", LIARA_DEFAULT_ENDPOINT)

    if not api_key:
        raise RuntimeError("LIARA_API_KEY environment variable is not set")
    if not bucket:
        raise RuntimeError("LIARA_BUCKET environment variable is not set")

    file_size = file_path.stat().st_size
    file_size_mb = file_size / MB
    logger.info("Uploading to Liara: %s (%.2f MB)", file_path.name, file_size_mb)

    object_key = f"hybrid-rar-bridge/{file_path.name}"

    try:
        # Step 1: Request a presigned upload URL
        presign_resp = requests.post(
            f"{endpoint}/v1/objects/{bucket}/{object_key}/upload-url",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={},
            timeout=30,
        )

        if presign_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Liara presign request failed ({presign_resp.status_code}): "
                f"{presign_resp.text}"
            )

        presign_data = presign_resp.json()
        upload_url = presign_data.get("upload_url") or presign_data.get("url")
        if not upload_url:
            raise RuntimeError(f"Liara returned no upload URL: {presign_data}")

        # Step 2: PUT the file to the presigned URL
        with open(file_path, "rb") as f:
            put_resp = requests.put(upload_url, data=f, timeout=1800)

        if put_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Liara PUT failed ({put_resp.status_code}): {put_resp.text}"
            )

        # Step 3: Build download URL
        download_url = (
            presign_data.get("download_url")
            or presign_data.get("url")
            or f"https://{bucket}.storage.iran.liara.ir/{object_key}"
        )

        logger.info("Liara upload successful: %s", download_url)
        return download_url

    except RuntimeError:
        raise
    except Exception as e:
        # Check for timeout/connection errors from requests
        if "timeout" in str(e).lower():
            raise RuntimeError(
                f"Liara upload timed out for {file_path.name} ({file_size_mb:.2f} MB)"
            ) from e
        if "connection" in str(e).lower():
            raise RuntimeError(
                f"Liara connection error while uploading {file_path.name}: {e}"
            ) from e
        raise RuntimeError(f"Failed to upload {file_path.name} to Liara: {e}") from e


async def cleanup_old_files(valid_days: int) -> int:
    """Delete objects older than *valid_days* from the Liara bucket.

    Only objects under the ``hybrid-rar-bridge/`` prefix are considered.

    Args:
        valid_days: Minimum age (in days) for files to be deleted.

    Returns:
        Number of objects deleted.
    """
    if valid_days <= 0:
        return 0

    api_key = os.getenv("LIARA_API_KEY")
    bucket = os.getenv("LIARA_BUCKET")
    endpoint = os.getenv("LIARA_ENDPOINT", LIARA_DEFAULT_ENDPOINT)

    if not all([api_key, bucket]):
        return 0

    try:
        from datetime import datetime, timezone

        cutoff = (
            datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"
            if valid_days > 0 else ""
        )

        # List objects under our prefix
        headers = {"Authorization": f"Bearer {api_key}"}
        list_resp = requests.get(
            f"{endpoint}/v1/objects/{bucket}",
            headers=headers,
            params={"prefix": "hybrid-rar-bridge/"},
            timeout=30,
        )

        if list_resp.status_code != 200:
            logger.warning("Liara list objects failed: %s", list_resp.status_code)
            return 0

        data = list_resp.json()
        objects = data.get("objects", data.get("items", []))

        cutoff_ts = datetime.now(timezone.utc).timestamp() - (valid_days * 86400)
        deleted_count = 0

        for obj in objects:
            key = obj.get("key", obj.get("name", ""))
            last_modified_str = obj.get("last_modified", obj.get("updatedAt", ""))

            if not key or not last_modified_str:
                continue

            try:
                # Parse ISO timestamp (handle both with and without 'Z')
                lm_str = last_modified_str.replace("Z", "+00:00")
                if "+" not in lm_str and lm_str.endswith("00:00"):
                    lm_str += "+00:00"
                lm_dt = datetime.fromisoformat(lm_str)
                if lm_dt.timestamp() < cutoff_ts:
                    del_resp = requests.delete(
                        f"{endpoint}/v1/objects/{bucket}/{key}",
                        headers=headers,
                        timeout=30,
                    )
                    if del_resp.status_code in (200, 204):
                        deleted_count += 1
            except (ValueError, TypeError):
                continue

        if deleted_count:
            logger.info(
                "Liara cleanup: deleted %d objects older than %d days",
                deleted_count,
                valid_days,
            )

        return deleted_count

    except Exception as e:
        logger.error("Liara cleanup failed: %s", e)
        return 0
