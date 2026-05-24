"""
Bale Messenger uploader module.

Uploads files to a Bale channel via the Bale Bot API. The bot sends
documents to a configured channel, and users can access the file
through the channel. Direct download URLs are not provided by default
through the Bale Bot API, so the channel serves as the distribution point.

Configuration (via environment variables):
    BALE_BOT_TOKEN: Token for the Bale bot obtained from @BotFather on Bale.
    BALE_CHAT_ID: Channel username (e.g., @my_channel) or numeric ID.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Bale maximum file upload size in bytes (~2 GB)
BALE_MAX_SIZE = 2 * 1024 * 1024 * 1024


async def upload(file_path: Path) -> str:
    """Upload a file to a Bale channel using the Bale Bot API.

    Opens the file in binary mode and sends it as a document to the
    configured channel. The uploaded file will appear in the channel
    for users to download.

    Args:
        file_path: Path to the file to upload.

    Returns:
        A string indicating successful upload with channel reference.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If the upload fails due to API error or missing config.
    """
    import os

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    token = os.getenv("BALE_BOT_TOKEN")
    chat_id = os.getenv("BALE_CHAT_ID")

    if not token:
        raise RuntimeError("BALE_BOT_TOKEN environment variable is not set")
    if not chat_id:
        raise RuntimeError("BALE_CHAT_ID environment variable is not set")

    file_size = file_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    logger.info(
        "Uploading to Bale: %s (%.2f MB)", file_path.name, file_size_mb
    )

    try:
        from balebot import Bot

        bot = Bot(token=token)

        with open(file_path, "rb") as f:
            message = bot.send_document(
                chat_id=chat_id,
                document=f,
                caption=file_path.name,
            )

        file_id = getattr(message, "document", None)
        if file_id:
            file_id = getattr(file_id, "file_id", "unknown")

        result = (
            f"Bale upload successful (File ID: {file_id}) "
            f"-- check your channel {chat_id}"
        )
        logger.info(result)
        return result

    except ImportError:
        # Fallback: use HTTP API directly if balebot package is not installed
        logger.warning(
            "balebot package not installed, using HTTP API fallback for Bale"
        )
        return await _upload_via_http(file_path, token, chat_id)

    except Exception as e:
        raise RuntimeError(
            f"Failed to upload {file_path.name} to Bale: {e}"
        ) from e


async def _upload_via_http(
    file_path: Path, token: str, chat_id: str
) -> str:
    """Upload file to Bale via direct HTTP API.

    Fallback uploader using requests library when the balebot package
    is not available. Sends the file as a multipart/form-data POST
    request to the Bale Bot API sendDocument endpoint.

    Args:
        file_path: Path to the file to upload.
        token: Bale Bot API token.
        chat_id: Target channel or chat ID.

    Returns:
        A string with upload confirmation details.

    Raises:
        RuntimeError: If the HTTP request fails.
    """
    import requests

    url = f"https://tapi.bale.ai/bot{token}/sendDocument"

    with open(file_path, "rb") as f:
        response = requests.post(
            url,
            data={"chat_id": chat_id},
            files={"document": (file_path.name, f)},
            timeout=600,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Bale HTTP API returned status {response.status_code}: "
            f"{response.text}"
        )

    data = response.json()
    if not data.get("ok"):
        description = data.get("description", "Unknown error")
        raise RuntimeError(f"Bale API error: {description}")

    file_id = (
        data.get("result", {}).get("document", {}).get("file_id", "unknown")
    )
    result = (
        f"Bale upload successful (File ID: {file_id}) "
        f"-- check your channel {chat_id}"
    )
    logger.info(result)
    return result
