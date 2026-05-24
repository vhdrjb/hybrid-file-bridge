"""
PicoFile uploader module.

Uploads files to PicoFile (picofile.com) — an Iranian file-sharing
service offering 20 GB of free storage with a 2 GB per-file limit and
public download links.

**IMPORTANT**: PicoFile does not provide an official public upload API.
This module reverse-engineers the web upload flow.  It may break if
PicoFile changes its website.  When that happens, check the upload
log for updated CSRF / endpoint details and adjust accordingly.

Configuration (via environment variables):
    PICOFILE_EMAIL:    Account email (required for uploads).
    PICOFILE_PASSWORD: Account password.
    PICOFILE_VALID_DAYS: Delete files older than N days (default: 0 = off).
"""

import logging
import os
import re
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

PICOFILE_MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB

MB = 1024 * 1024

# Known PicoFile upload endpoints (tried in order)
PICOFILE_UPLOAD_URLS = [
    "https://www.picofile.com/api/file/upload",
    "https://www.picofile.com/file/upload",
]


def _create_session() -> requests.Session:
    """Create an authenticated requests session for PicoFile.

    Logs in with the configured credentials and stores the session
    cookies for subsequent upload / delete requests.

    Returns:
        An authenticated requests.Session.

    Raises:
        RuntimeError: If login fails or credentials are missing.
    """
    email = os.getenv("PICOFILE_EMAIL")
    password = os.getenv("PICOFILE_PASSWORD")

    if not email:
        raise RuntimeError("PICOFILE_EMAIL environment variable is not set")
    if not password:
        raise RuntimeError("PICOFILE_PASSWORD environment variable is not set")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        }
    )

    # Step 1: GET login page to grab CSRF token
    login_page = session.get("https://www.picofile.com/login", timeout=30)
    csrf_match = re.search(
        r'name=["\']_token["\']\s+content=["\']([^"\']+)',
        login_page.text,
    )
    csrf_token = csrf_match.group(1) if csrf_match else ""

    # Step 2: POST login
    login_resp = session.post(
        "https://www.picofile.com/login",
        data={
            "email": email,
            "password": password,
            "_token": csrf_token,
        },
        timeout=30,
        allow_redirects=True,
    )

    if "logout" not in login_page.text and "dashboard" not in login_page.text:
        # Check if redirected to a logged-in page
        if session.cookies.get("picofile_session") is None:
            raise RuntimeError(
                "PicoFile login failed — check PICOFILE_EMAIL and PICOFILE_PASSWORD"
            )

    logger.info("PicoFile login successful")
    return session


async def upload(file_path: Path) -> str:
    """Upload a file to PicoFile.

    Authenticates with the configured account, uploads the file via the
    web form endpoint, and returns the public download link.

    Args:
        file_path: Path to the file to upload.

    Returns:
        A public download URL string.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If the upload fails or configuration is missing.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size
    file_size_mb = file_size / MB
    logger.info("Uploading to PicoFile: %s (%.2f MB)", file_path.name, file_size_mb)

    try:
        session = _create_session()

        # Try each known upload endpoint
        last_error = None
        for upload_url in PICOFILE_UPLOAD_URLS:
            try:
                with open(file_path, "rb") as f:
                    resp = session.post(
                        upload_url,
                        files={"file": (file_path.name, f)},
                        timeout=1800,
                    )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    download_url = (
                        data.get("url")
                        or data.get("download_url")
                        or data.get("link")
                        or data.get("file_url")
                    )

                    if download_url:
                        # Ensure URL has scheme
                        if download_url.startswith("//"):
                            download_url = "https:" + download_url
                        elif download_url.startswith("/"):
                            download_url = "https://www.picofile.com" + download_url

                        logger.info("PicoFile upload successful: %s", download_url)
                        return download_url

                last_error = f"status {resp.status_code}: {resp.text[:500]}"

            except requests.exceptions.Timeout:
                last_error = f"timeout uploading to {upload_url}"
                continue
            except requests.exceptions.ConnectionError as e:
                last_error = f"connection error: {e}"
                continue

        raise RuntimeError(
            f"PicoFile upload failed for {file_path.name}. "
            f"Last error: {last_error}. "
            f"PicoFile's API may have changed — check the website."
        )

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to upload {file_path.name} to PicoFile: {e}") from e


async def cleanup_old_files(valid_days: int) -> int:
    """Delete files older than *valid_days* from PicoFile.

    Fetches the user's file list and deletes old entries.

    Args:
        valid_days: Minimum age (in days) for files to be deleted.

    Returns:
        Number of files deleted.
    """
    if valid_days <= 0:
        return 0

    try:
        session = _create_session()
        deleted_count = 0

        from datetime import datetime, timezone

        cutoff_ts = datetime.now(timezone.utc).timestamp() - (valid_days * 86400)

        # Fetch file list (try known API paths)
        list_urls = [
            "https://www.picofile.com/api/files",
            "https://www.picofile.com/api/file/list",
        ]

        files = []
        for list_url in list_urls:
            try:
                resp = session.get(list_url, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    files = data.get("files", data.get("data", data.get("items", [])))
                    break
            except Exception:
                continue

        for file_info in files:
            file_id = file_info.get("id", file_info.get("file_id", ""))
            created_str = file_info.get(
                "created_at", file_info.get("date", file_info.get("upload_date", ""))
            )

            if not file_id or not created_str:
                continue

            try:
                from dateutil import parser as dateparser

                created_dt = dateparser.parse(created_str)
                if created_dt.timestamp() < cutoff_ts:
                    del_resp = session.delete(
                        f"https://www.picofile.com/api/file/{file_id}",
                        timeout=30,
                    )
                    if del_resp.status_code in (200, 204):
                        deleted_count += 1
            except (ImportError, ValueError, TypeError):
                # Fallback: skip files we can't parse
                continue

        if deleted_count:
            logger.info(
                "PicoFile cleanup: deleted %d files older than %d days",
                deleted_count,
                valid_days,
            )

        return deleted_count

    except Exception as e:
        logger.error("PicoFile cleanup failed: %s", e)
        return 0
