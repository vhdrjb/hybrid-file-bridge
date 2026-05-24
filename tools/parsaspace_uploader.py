"""
ParsaSpace uploader module.

Uploads files to ParsaSpace (an Iranian cloud storage service) via its
REST API. ParsaSpace provides direct download links, making it ideal
for sharing large files with users who can then download them without
any messenger intermediary.

Configuration (via environment variables):
    PARSASPACE_TOKEN: API token obtained from the ParsaSpace dashboard.
    PARSASPACE_DOMAIN: Your subdomain on ParsaSpace (e.g., myfiles.parsaspace.com).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ParsaSpace maximum file upload size in bytes (50 GB)
PARSASPACE_MAX_SIZE = 50 * 1024 * 1024 * 1024

# ParsaSpace API endpoints
PARSASPACE_UPLOAD_URL = "https://api.parsaspace.com/v1/files/upload"


async def upload(file_path: Path) -> str:
    """Upload a file to ParsaSpace using its REST API.

    Sends the file as a multipart/form-data POST request to the
    ParsaSpace upload endpoint. The API returns a direct download link
    upon successful upload.

    Args:
        file_path: Path to the file to upload.

    Returns:
        A direct download URL string on ParsaSpace.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If the upload fails or configuration is missing.
    """
    import os
    import requests

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    token = os.getenv("PARSASPACE_TOKEN")
    domain = os.getenv("PARSASPACE_DOMAIN")

    if not token:
        raise RuntimeError("PARSASPACE_TOKEN environment variable is not set")
    if not domain:
        raise RuntimeError("PARSASPACE_DOMAIN environment variable is not set")

    file_size = file_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    logger.info(
        "Uploading to ParsaSpace: %s (%.2f MB)", file_path.name, file_size_mb
    )

    headers = {
        "Authorization": f"Bearer {token}",
    }

    try:
        # ParsaSpace upload with streaming for large files
        with open(file_path, "rb") as f:
            response = requests.post(
                PARSASPACE_UPLOAD_URL,
                headers=headers,
                files={"file": (file_path.name, f)},
                data={"domain": domain},
                timeout=1800,  # 30 minute timeout for large files
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"ParsaSpace API returned status {response.status_code}: "
                f"{response.text}"
            )

        data = response.json()

        if data.get("result") == "success" or data.get("ok"):
            download_url = data.get("url") or data.get("download_url")
            if download_url:
                logger.info("ParsaSpace upload successful: %s", download_url)
                return download_url

            # Construct URL if API doesn't return one directly
            download_url = f"https://{domain}/{file_path.name}"
            logger.info("ParsaSpace upload successful: %s", download_url)
            return download_url
        else:
            error_msg = data.get("message") or data.get("error") or "Unknown error"
            raise RuntimeError(f"ParsaSpace upload failed: {error_msg}")

    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"ParsaSpace upload timed out for {file_path.name} "
            f"({file_size_mb:.2f} MB)"
        )
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            f"ParsaSpace connection error while uploading {file_path.name}: {e}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Failed to upload {file_path.name} to ParsaSpace: {e}"
        ) from e
