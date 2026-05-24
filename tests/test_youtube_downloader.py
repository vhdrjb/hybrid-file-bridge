"""
Unit tests for the YouTube downloader module.

Tests cover YouTube URL detection, format parsing, info fetching,
video downloading, and button label formatting. All yt-dlp subprocess
calls are mocked.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest

from tools.youtube_downloader import (
    VideoFormat,
    download_video,
    format_quality_button_label,
    get_video_info,
    is_youtube_url,
    parse_formats,
)


# ---------------------------------------------------------------------------
# Sample yt-dlp JSON response for testing
# ---------------------------------------------------------------------------

SAMPLE_YTDLP_INFO = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
    "duration": 213,
    "formats": [
        {
            "format_id": "137",
            "ext": "mp4",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "resolution": "1920x1080",
            "filesize": 50000000,
            "format_note": "1080p",
            "vcodec": "avc1.640028",
            "acodec": "none",
        },
        {
            "format_id": "22",
            "ext": "mp4",
            "width": 1280,
            "height": 720,
            "fps": 30,
            "resolution": "1280x720",
            "filesize": 30000000,
            "format_note": "720p",
            "vcodec": "avc1.4d401f",
            "acodec": "mp4a.40.2",
        },
        {
            "format_id": "136",
            "ext": "mp4",
            "width": 854,
            "height": 480,
            "fps": 30,
            "resolution": "854x480",
            "filesize": 15000000,
            "format_note": "480p",
            "vcodec": "avc1.4d401f",
            "acodec": "none",
        },
        {
            "format_id": "140",
            "ext": "m4a",
            "width": 0,
            "height": 0,
            "fps": None,
            "resolution": "audio only",
            "filesize": 3500000,
            "format_note": "tiny",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
        },
        {
            "format_id": "251",
            "ext": "webm",
            "width": 0,
            "height": 0,
            "fps": None,
            "resolution": "audio only",
            "filesize_approx": 4000000,
            "format_note": "",
            "vcodec": "none",
            "acodec": "opus",
        },
        {
            "format_id": "storyboard",
            "ext": "mhtml",
            "width": 0,
            "height": 0,
            "resolution": "0x0",
            "filesize": None,
            "format_note": "",
            "vcodec": "none",
            "acodec": "none",
        },
    ],
}

SAMPLE_YTDLP_JSON = json.dumps(SAMPLE_YTDLP_INFO)


class TestIsYoutubeUrl:
    """Tests for the is_youtube_url function."""

    def test_standard_watch_url(self):
        assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_standard_watch_url_no_www(self):
        assert is_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_short_url(self):
        assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ") is True

    def test_shorts_url(self):
        assert is_youtube_url("https://www.youtube.com/shorts/abc123XYZ") is True

    def test_embed_url(self):
        assert is_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ") is True

    def test_music_url(self):
        assert is_youtube_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_with_query_params(self):
        assert is_youtube_url(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLabc"
        ) is True

    def test_non_youtube_url(self):
        assert is_youtube_url("https://example.com/file.zip") is False

    def test_regular_download_url(self):
        assert is_youtube_url("https://cdn.example.com/videos/file.mp4") is False

    def test_empty_string(self):
        assert is_youtube_url("") is False

    def test_case_insensitive(self):
        assert is_youtube_url("HTTPS://WWW.YOUTUBE.COM/watch?v=abc") is True

    def test_with_text_around(self):
        """YouTube URL embedded in other text should still be detected."""
        assert is_youtube_url(
            "Check this out: https://youtu.be/dQw4w9WgXcQ it's great!"
        ) is True


class TestParseFormats:
    """Tests for the parse_formats function."""

    def test_parse_standard_formats(self):
        formats = parse_formats(SAMPLE_YTDLP_INFO)
        # Should have 5 formats (exclude storyboard and mhtml)
        assert len(formats) == 5

    def test_video_formats_sorted_by_resolution(self):
        formats = parse_formats(SAMPLE_YTDLP_INFO)
        video_formats = [f for f in formats if not f.is_audio_only]
        assert len(video_formats) == 3
        # Should be sorted 1080p, 720p, 480p
        assert video_formats[0].resolution == "1920x1080"
        assert video_formats[1].resolution == "1280x720"
        assert video_formats[2].resolution == "854x480"

    def test_audio_formats_at_end(self):
        formats = parse_formats(SAMPLE_YTDLP_INFO)
        assert formats[-1].is_audio_only is True
        assert formats[-2].is_audio_only is True

    def test_audio_only_resolution(self):
        formats = parse_formats(SAMPLE_YTDLP_INFO)
        audio = [f for f in formats if f.is_audio_only]
        for fmt in audio:
            assert fmt.resolution == "audio only"

    def test_filesize_mb_conversion(self):
        formats = parse_formats(SAMPLE_YTDLP_INFO)
        fmt_137 = next(f for f in formats if f.format_id == "137")
        # 50000000 bytes ≈ 47.68 MB
        assert fmt_137.filesize_mb == pytest.approx(47.68, abs=0.1)

    def test_filesize_approx_supported(self):
        formats = parse_formats(SAMPLE_YTDLP_INFO)
        fmt_251 = next(f for f in formats if f.format_id == "251")
        # 4000000 bytes ≈ 3.81 MB
        assert fmt_251.filesize_mb == pytest.approx(3.81, abs=0.1)

    def test_storyboards_filtered(self):
        formats = parse_formats(SAMPLE_YTDLP_INFO)
        storyboard_ids = [f.format_id for f in formats if "storyboard" in f.format_id]
        assert storyboard_ids == []

    def test_empty_formats_list(self):
        info = {"formats": []}
        formats = parse_formats(info)
        assert formats == []

    def test_no_formats_key(self):
        info = {}
        formats = parse_formats(info)
        assert formats == []

    def test_duplicates_removed(self):
        info = {
            "formats": [
                {
                    "format_id": "137", "ext": "mp4",
                    "width": 1920, "height": 1080, "fps": 30,
                    "resolution": "1920x1080", "filesize": 50000000,
                },
                {
                    "format_id": "137", "ext": "mp4",
                    "width": 1920, "height": 1080, "fps": 30,
                    "resolution": "1920x1080", "filesize": 50000000,
                },
            ],
        }
        formats = parse_formats(info)
        assert len(formats) == 1


class TestGetVideoInfo:
    """Tests for the get_video_info function."""

    @pytest.mark.asyncio
    async def test_successful_info_fetch(self):
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(SAMPLE_YTDLP_JSON.encode(), b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            info = await get_video_info("https://youtube.com/watch?v=test")

        assert info["id"] == "dQw4w9WgXcQ"
        assert info["title"].startswith("Rick Astley")

    @pytest.mark.asyncio
    async def test_ytdlp_failure(self):
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"ERROR: Video unavailable")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError, match="yt-dlp info fetch failed"):
                await get_video_info("https://youtube.com/watch?v=invalid")

    @pytest.mark.asyncio
    async def test_invalid_json_response(self):
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"not valid json {{{", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError, match="Failed to parse yt-dlp JSON"):
                await get_video_info("https://youtube.com/watch?v=test")

    @pytest.mark.asyncio
    async def test_timeout(self):
        mock_process = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(asyncio.TimeoutError):
                await get_video_info("https://youtube.com/watch?v=test")


class TestDownloadVideo:
    """Tests for the download_video function."""

    @pytest.mark.asyncio
    async def test_successful_download(self, temp_dir):
        # Pre-create the downloaded file that yt-dlp would produce
        downloaded = temp_dir / "yt_download" / "Video Title.mp4"
        downloaded.parent.mkdir(parents=True)
        downloaded.write_bytes(b"fake video content")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await download_video(
                url="https://youtube.com/watch?v=test",
                format_id="137",
                output_dir=downloaded.parent,
            )

        assert result.exists()

    @pytest.mark.asyncio
    async def test_missing_output_dir(self):
        with pytest.raises(FileNotFoundError):
            await download_video(
                url="https://youtube.com/watch?v=test",
                format_id="137",
                output_dir=Path("/tmp/nonexistent_dir_hrb_test"),
            )

    @pytest.mark.asyncio
    async def test_ytdlp_download_failure(self, temp_dir):
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"ERROR: unable to download")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError, match="yt-dlp download failed"):
                await download_video(
                    url="https://youtube.com/watch?v=test",
                    format_id="137",
                    output_dir=temp_dir,
                )

    @pytest.mark.asyncio
    async def test_download_timeout(self, temp_dir):
        mock_process = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=None)
        mock_process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(asyncio.TimeoutError):
                await download_video(
                    url="https://youtube.com/watch?v=test",
                    format_id="137",
                    output_dir=temp_dir,
                )


class TestFormatQualityButtonLabel:
    """Tests for the format_quality_button_label function."""

    def test_video_format_label(self):
        fmt = VideoFormat(
            format_id="137",
            resolution="1920x1080",
            extension="mp4",
            filesize_mb=47.68,
            fps=30.0,
            note="1080p",
            is_audio_only=False,
        )
        label = format_quality_button_label(fmt, 1)
        assert "1920x1080" in label
        assert "mp4" in label
        assert "30fps" in label
        assert "48 MB" in label
        assert "1080p" in label

    def test_audio_only_label(self):
        fmt = VideoFormat(
            format_id="140",
            resolution="audio only",
            extension="m4a",
            filesize_mb=3.5,
            fps=None,
            note="tiny",
            is_audio_only=True,
        )
        label = format_quality_button_label(fmt, 1)
        assert "Audio" in label
        assert "m4a" in label
        assert "4 MB" in label

    def test_unknown_size(self):
        fmt = VideoFormat(
            format_id="22",
            resolution="1280x720",
            extension="mp4",
            filesize_mb=None,
            fps=30.0,
            note="",
            is_audio_only=False,
        )
        label = format_quality_button_label(fmt, 1)
        assert "? MB" in label

    def test_no_fps(self):
        fmt = VideoFormat(
            format_id="18",
            resolution="640x360",
            extension="mp4",
            filesize_mb=10.0,
            fps=None,
            note="",
            is_audio_only=False,
        )
        label = format_quality_button_label(fmt, 1)
        assert "fps" not in label
        assert "640x360" in label
