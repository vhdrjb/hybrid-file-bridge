"""
YouTube downloader module using yt-dlp.

This module provides async functions to:
- Detect YouTube URLs.
- Fetch available video/audio formats with quality information.
- Download a video in the user-selected format.

It wraps yt-dlp (a fork of youtube-dl) as subprocess calls to avoid
blocking the event loop during potentially long downloads.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# YouTube URL patterns (covers youtube.com, youtu.be, music.youtube.com)
YOUTUBE_PATTERNS = [
    re.compile(r"https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+", re.IGNORECASE),
    re.compile(r"https?://youtu\.be/[\w-]+", re.IGNORECASE),
    re.compile(r"https?://(?:www\.)?youtube\.com/shorts/[\w-]+", re.IGNORECASE),
    re.compile(r"https?://(?:www\.)?youtube\.com/embed/[\w-]+", re.IGNORECASE),
    re.compile(r"https?://(?:music\.)?youtube\.com/watch\?v=[\w-]+", re.IGNORECASE),
]


def is_youtube_url(url: str) -> bool:
    """Check whether a URL is a YouTube video URL.

    Matches against common YouTube URL formats including regular
    watch pages, short links, embeds, YouTube Music, and Shorts.

    Args:
        url: The URL string to check.

    Returns:
        True if the URL matches a known YouTube pattern, False otherwise.
    """
    return any(pattern.search(url) for pattern in YOUTUBE_PATTERNS)


@dataclass
class VideoFormat:
    """Represents a downloadable video/audio format.

    Attributes:
        format_id: The yt-dlp format identifier (e.g., '137', 'bestaudio').
        resolution: Display resolution (e.g., '1920x1080'), or 'audio only'.
        extension: File extension (e.g., 'mp4', 'webm', 'm4a').
        filesize_mb: Approximate file size in megabytes (may be None).
        fps: Frames per second for video formats, None for audio-only.
        note: Human-readable format note from yt-dlp.
        is_audio_only: Whether this format contains only audio.
    """

    format_id: str
    resolution: str
    extension: str
    filesize_mb: float | None
    fps: float | None
    note: str
    is_audio_only: bool


def _parse_filesize(value) -> float | None:
    """Convert a yt-dlp filesize value to megabytes.

    yt-dlp reports filesizes as either integers (bytes) or None
    when the size cannot be determined. This helper normalises
    the value to megabytes or returns None.

    Args:
        value: The filesize value from yt-dlp (int, float, or None).

    Returns:
        File size in megabytes, or None if unknown.
    """
    if value is None:
        return None
    try:
        return round(float(value) / (1024 * 1024), 2)
    except (TypeError, ValueError):
        return None


def parse_formats(info: dict) -> list[VideoFormat]:
    """Parse yt-dlp extracted info into a list of VideoFormat objects.

    Filters out duplicate and uninteresting formats, keeping only
    those that contain either video or audio streams. Formats without
    a resolution or with a '0x0' resolution are treated as audio-only.

    Args:
        info: The info dictionary returned by yt-dlp's extract_info.

    Returns:
        List of VideoFormat objects sorted by video quality (descending)
        with audio-only formats at the end.
    """
    raw_formats = info.get("formats", [])
    seen = set()
    video_formats = []
    audio_formats = []

    for fmt in raw_formats:
        fid = fmt.get("format_id", "")

        # Skip duplicates, storyboards, and manifest-only entries
        if fid in seen or fid.startswith("storyboard"):
            continue
        if fmt.get("ext") in ("mhtml",):
            continue

        seen.add(fid)

        resolution = fmt.get("resolution", "0x0") or "0x0"
        width = fmt.get("width", 0) or 0
        height = fmt.get("height", 0) or 0

        if width == 0 or height == 0 or resolution == "audio only":
            resolution_display = "audio only"
            is_audio = True
        else:
            resolution_display = f"{width}x{height}"
            is_audio = False

        parsed = VideoFormat(
            format_id=fid,
            resolution=resolution_display,
            extension=fmt.get("ext", "unknown"),
            filesize_mb=_parse_filesize(fmt.get("filesize") or fmt.get("filesize_approx")),
            fps=fmt.get("fps"),
            note=fmt.get("format_note", ""),
            is_audio_only=is_audio,
        )

        if is_audio:
            audio_formats.append(parsed)
        else:
            video_formats.append(parsed)

    # Sort video by resolution (descending), audio by bitrate-like order
    video_formats.sort(key=lambda f: (
        int(f.resolution.split("x")[1]) if "x" in f.resolution else 0
    ), reverse=True)
    audio_formats.sort(key=lambda f: f.filesize_mb or 0, reverse=True)

    return video_formats + audio_formats


async def get_video_info(url: str) -> dict:
    """Extract video metadata from a YouTube URL using yt-dlp.

    Runs `yt-dlp --dump-json` to fetch video information including
    title, duration, and available formats without downloading.

    Args:
        url: The YouTube video URL.

    Returns:
        The info dictionary from yt-dlp.

    Raises:
        RuntimeError: If yt-dlp exits with a non-zero code or returns
            invalid JSON.
    """
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        "--no-warnings",
        url,
    ]

    logger.info("Fetching video info: %s", url)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await asyncio.wait_for(
        process.communicate(), timeout=120
    )

    if process.returncode != 0:
        error_msg = stderr.decode().strip() or "Unknown error"
        raise RuntimeError(
            f"yt-dlp info fetch failed (code {process.returncode}): {error_msg}"
        )

    import json
    try:
        info = json.loads(stdout.decode())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse yt-dlp JSON output: {e}")

    logger.info(
        "Video found: '%s' (%d formats available)",
        info.get("title", "unknown"),
        len(info.get("formats", [])),
    )

    return info


async def download_video(
    url: str,
    format_id: str,
    output_dir: Path,
    output_template: str = "%(title).200s.%(ext)s",
) -> Path:
    """Download a YouTube video in a specific format using yt-dlp.

    Downloads the video with the given format ID and saves it to the
    specified directory. The output filename is derived from the video
    title provided by yt-dlp.

    Args:
        url: The YouTube video URL.
        format_id: The yt-dlp format identifier to download.
        output_dir: Directory where the downloaded file will be saved.
        output_template: yt-dlp output filename template. Defaults to
            using the video title with up to 200 characters.

    Returns:
        Path to the downloaded file.

    Raises:
        FileNotFoundError: If output_dir does not exist.
        RuntimeError: If yt-dlp fails or the output file is not found.
    """
    output_dir = Path(output_dir)
    if not output_dir.exists():
        raise FileNotFoundError(f"Output directory does not exist: {output_dir}")

    output_template_path = str(output_dir / output_template)

    cmd = [
        "yt-dlp",
        "-f", format_id,
        "--merge-output-format", "mp4",
        "-o", output_template_path,
        "--no-playlist",
        "--no-warnings",
        "--progress",
        "--newline",
        "--concurrent-fragments", "4",
        url,
    ]

    logger.info(
        "Downloading YouTube video: %s (format: %s)", url, format_id
    )

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=3600
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise asyncio.TimeoutError(
            f"YouTube download timed out after 3600s: {url}"
        )

    if process.returncode != 0:
        error_msg = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(
            f"yt-dlp download failed (code {process.returncode}): {error_msg}"
        )

    # Find the downloaded file
    downloaded_files = list(output_dir.glob("*"))
    if not downloaded_files:
        raise FileNotFoundError(
            f"yt-dlp completed but no file found in {output_dir}"
        )

    # The most recently modified file is the download
    downloaded = max(downloaded_files, key=lambda p: p.stat().st_mtime)

    file_size_mb = downloaded.stat().st_size / (1024 * 1024)
    logger.info(
        "YouTube download complete: %s (%.2f MB)", downloaded.name, file_size_mb
    )

    return downloaded


def format_quality_button_label(fmt: VideoFormat, index: int) -> str:
    """Create a human-readable label for a Telegram inline keyboard button.

    Generates a concise label showing resolution, extension, file size,
    and FPS to help the user choose the right quality.

    Args:
        fmt: The VideoFormat to label.
        index: The format index number (1-based for display).

    Returns:
        A formatted button label string.
    """
    size_str = f"{fmt.filesize_mb:.0f} MB" if fmt.filesize_mb else "? MB"

    if fmt.is_audio_only:
        return f"🎵 Audio ({fmt.extension}) – {size_str}"

    fps_str = f" {int(fmt.fps)}fps" if fmt.fps else ""
    note_str = f" {fmt.note}" if fmt.note else ""

    return (
        f"▶ {fmt.resolution} ({fmt.extension}){fps_str} – {size_str}{note_str}"
    )
