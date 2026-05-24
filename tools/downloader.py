"""
File downloader module using aria2c for fast, resumable downloads.

This module provides an async interface to download files from URLs
using aria2c as the backend download engine. aria2c supports multi-connection
downloads, metalink, BitTorrent, and provides superior performance
compared to standard HTTP clients for large file downloads.
"""

import asyncio
import logging
from pathlib import Path
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

# Default aria2c options optimized for VPS environments
DEFAULT_ARIA2_OPTS = [
    "--max-connection-per-server=16",
    "--split=16",
    "--min-split-size=1M",
    "--max-tries=5",
    "--retry-wait=3",
    "--timeout=60",
    "--connect-timeout=30",
    "--allow-overwrite=true",
    "--auto-file-renaming=false",
    "--check-certificate=true",
    "--summary-interval=0",
    "--console-log-level=warn",
]


def extract_filename_from_url(url: str) -> str:
    """Extract a meaningful filename from a download URL.

    Parses the URL path and attempts to extract the filename component.
    Falls back to a timestamp-based name if the URL doesn't contain
    a clear filename.

    Args:
        url: The download URL to parse.

    Returns:
        A cleaned-up filename string.
    """
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = path.rstrip("/").split("/")[-1]

    # Filter out empty or suspiciously short filenames
    if not filename or len(filename) < 2 or "." not in filename:
        import time

        filename = f"download_{int(time.time())}"

    return filename


async def download_file(
    url: str,
    dest_dir: Path,
    filename: str | None = None,
    aria2_options: list[str] | None = None,
) -> Path:
    """Download a file from a URL using aria2c.

    Spawns aria2c as an asynchronous subprocess with optimized settings
    for high-speed downloads on VPS environments. The download supports
    multi-connection transfers for improved throughput.

    Args:
        url: The direct download URL of the file.
        dest_dir: Directory where the downloaded file will be saved.
        filename: Optional custom filename. If None, extracted from URL.
        aria2_options: Optional list of additional aria2c command-line options.

    Returns:
        Path to the downloaded file.

    Raises:
        FileNotFoundError: If dest_dir does not exist.
        RuntimeError: If aria2c exits with a non-zero return code.
        asyncio.TimeoutError: If the download exceeds the timeout.
    """
    dest_dir = Path(dest_dir)
    if not dest_dir.exists():
        raise FileNotFoundError(f"Destination directory does not exist: {dest_dir}")

    if filename is None:
        filename = extract_filename_from_url(url)

    output_path = dest_dir / filename
    opts = list(DEFAULT_ARIA2_OPTS)

    if aria2_options:
        opts.extend(aria2_options)

    cmd = [
        "aria2c",
        *opts,
        "--dir",
        str(dest_dir),
        "--out",
        filename,
        "--auto-file-renaming=false",
        url,
    ]

    logger.info("Starting download: %s -> %s", url, output_path)
    logger.debug("aria2c command: %s", " ".join(cmd))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=3600  # 1 hour max per file
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise asyncio.TimeoutError(f"Download timed out after 3600 seconds: {url}")

    if process.returncode != 0:
        error_msg = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(f"aria2c failed with return code {process.returncode}: {error_msg}")

    if not output_path.exists():
        # aria2c might have saved with a different name (e.g., added .1)
        candidates = list(dest_dir.glob(f"{filename}*"))
        if candidates:
            output_path = candidates[0]
            logger.warning("aria2c saved file with different name: %s", output_path.name)
        else:
            raise FileNotFoundError(f"Download completed but output file not found: {output_path}")

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Download complete: %s (%.2f MB)", output_path.name, file_size_mb)

    return output_path
