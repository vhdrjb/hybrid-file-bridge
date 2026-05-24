"""
Eitaa Messenger uploader module.

Uploads files to an Eitaa channel or chat via the Eitaa Bot API.
Eitaa provides a Telegram-compatible Bot API that supports file uploads
and returns direct download links for uploaded files.

Configuration (via environment variables):
    EITAA_BOT_TOKEN: Token for the Eitaa bot obtained from EitaaYar.
    EITAA_CHAT_ID: Numeric chat or channel ID.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Eitaa maximum file upload size in bytes (~2 GB)
EITAA_MAX_SIZE = 2 * 1024 * 1024 * 1024


async def upload(file_path: Path) -> str:
    """Upload a file to Eitaa using the Eitaa Bot API.

    Sends the file as a document message to the configured chat/channel.
    On success, constructs a direct download URL using the returned file ID.

    Args:
        file_path: Path to the file to upload.

    Returns:
        A direct download URL string for the uploaded file on Eitaa.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If the upload fails or configuration is missing.
    """
    import os

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    token = os.getenv("EITAA_BOT_TOKEN")
    chat_id = os.getenv("EITAA_CHAT_ID")

    if not token:
        raise RuntimeError("EITAA_BOT_TOKEN environment variable is not set")
    if not chat_id:
        raise RuntimeError("EITAA_CHAT_ID environment variable is not set")

    file_size = file_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    logger.info("Uploading to Eitaa: %s (%.2f MB)", file_path.name, file_size_mb)

    try:
        from eitaa import Eitaa

        eitaa_bot = Eitaa(token)
        resp = eitaa_bot.send_file(chat_id, str(file_path))

        if resp and resp.get("ok"):
            file_id = resp.get("result", {}).get("file_id", "unknown")
            download_url = f"https://eitaa.com/file/{file_id}"
            logger.info("Eitaa upload successful: %s", download_url)
            return download_url
        else:
            description = resp.get("description", "Unknown error") if resp else "Empty response"
            raise RuntimeError(f"Eitaa API error: {description}")

    except ImportError:
        # Fallback to HTTP API
        logger.warning("eitaa package not installed, using HTTP API fallback for Eitaa")
        return await _upload_via_http(file_path, token, chat_id)

    except Exception as e:
        raise RuntimeError(f"Failed to upload {file_path.name} to Eitaa: {e}") from e


async def _upload_via_http(file_path: Path, token: str, chat_id: str) -> str:
    """Upload file to Eitaa via direct HTTP API.

    Fallback uploader using the requests library when the eitaa package
    is not available. Eitaa's Bot API is largely compatible with Telegram's,
    so we use the same endpoint format.

    Args:
        file_path: Path to the file to upload.
        token: Eitaa Bot API token.
        chat_id: Target chat or channel ID.

    Returns:
        A direct download URL for the uploaded file.

    Raises:
        RuntimeError: If the HTTP request fails.
    """
    import requests

    url = f"https://api.eitaa.com/bot{token}/sendDocument"

    with open(file_path, "rb") as f:
        response = requests.post(
            url,
            data={"chat_id": chat_id},
            files={"document": (file_path.name, f)},
            timeout=600,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Eitaa HTTP API returned status {response.status_code}: " f"{response.text}"
        )

    data = response.json()
    if not data.get("ok"):
        description = data.get("description", "Unknown error")
        raise RuntimeError(f"Eitaa API error: {description}")

    file_id = data.get("result", {}).get("document", {}).get("file_id", "unknown")
    download_url = f"https://eitaa.com/file/{file_id}"
    logger.info("Eitaa upload successful: %s", download_url)
    return download_url
