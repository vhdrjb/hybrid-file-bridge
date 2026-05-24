"""
Unit tests for the downloader module.

Tests cover the download_file function including success scenarios,
failure handling, timeout behavior, and filename extraction from URLs.
All external subprocess calls are mocked.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.downloader import download_file, extract_filename_from_url


class TestExtractFilenameFromUrl:
    """Tests for the extract_filename_from_url helper function."""

    def test_basic_url(self):
        """Extract filename from a standard URL with a clear filename."""
        url = "https://example.com/files/my_document.pdf"
        assert extract_filename_from_url(url) == "my_document.pdf"

    def test_url_with_query_params(self):
        """Extract filename from a URL with query parameters."""
        url = "https://example.com/download?file=data.zip&token=abc123"
        # When query params are in the path without clear filename, should fallback
        result = extract_filename_from_url(url)
        assert result is not None

    def test_url_with_encoded_chars(self):
        """Extract filename from a URL with percent-encoded characters."""
        url = "https://example.com/files/my%20document.pdf"
        assert extract_filename_from_url(url) == "my document.pdf"

    def test_url_with_trailing_slash(self):
        """Handle URL ending with a trailing slash (should use fallback name)."""
        url = "https://example.com/path/"
        result = extract_filename_from_url(url)
        assert "download_" in result

    def test_url_with_nested_path(self):
        """Extract filename from a deeply nested URL path."""
        url = "https://cdn.example.com/a/b/c/d/final_archive.rar"
        assert extract_filename_from_url(url) == "final_archive.rar"

    def test_url_without_extension(self):
        """Handle URL where the last path segment has no file extension."""
        url = "https://example.com/files/download"
        result = extract_filename_from_url(url)
        assert "download_" in result

    def test_url_single_char_segment(self):
        """Handle URL with suspiciously short filename segments."""
        url = "https://example.com/a"
        result = extract_filename_from_url(url)
        assert "download_" in result


class TestDownloadFile:
    """Tests for the async download_file function."""

    @pytest.mark.asyncio
    async def test_download_success(self, temp_dir):
        """Test successful download with mocked aria2c subprocess."""
        # Pre-create the file that aria2c would have downloaded
        expected_file = temp_dir / "test_file.txt"
        expected_file.write_text("downloaded content")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await download_file(
                url="https://example.com/test_file.txt",
                dest_dir=temp_dir,
                filename="test_file.txt",
            )

        assert result == expected_file

    @pytest.mark.asyncio
    async def test_download_creates_file(self, temp_dir):
        """Test that download creates the expected output file."""
        # Pre-create the file that aria2c would have created
        expected_file = temp_dir / "test_download.bin"
        expected_file.write_bytes(b"downloaded content")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await download_file(
                url="https://example.com/test_download.bin",
                dest_dir=temp_dir,
                filename="test_download.bin",
            )

        assert result == expected_file
        assert result.exists()

    @pytest.mark.asyncio
    async def test_download_failure_raises(self, temp_dir):
        """Test that non-zero return code raises RuntimeError."""
        mock_process = AsyncMock()
        mock_process.returncode = 3
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Download failed: permission denied")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError, match="aria2c failed"):
                await download_file(
                    url="https://example.com/missing.zip",
                    dest_dir=temp_dir,
                )

    @pytest.mark.asyncio
    async def test_download_timeout(self, temp_dir):
        """Test that download timeout is handled correctly."""
        mock_process = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=None)

        import asyncio

        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(asyncio.TimeoutError):
                await download_file(
                    url="https://example.com/slow_file.bin",
                    dest_dir=temp_dir,
                )

    @pytest.mark.asyncio
    async def test_download_missing_dest_dir(self):
        """Test that non-existent destination directory raises FileNotFoundError."""
        non_existent = Path("/tmp/nonexistent_dir_hrb_test")

        with pytest.raises(FileNotFoundError):
            await download_file(
                url="https://example.com/file.txt",
                dest_dir=non_existent,
            )

    @pytest.mark.asyncio
    async def test_download_auto_filename_extraction(self, temp_dir):
        """Test that filename is extracted from URL when not provided."""
        expected_file = temp_dir / "archive.zip"
        expected_file.write_bytes(b"content")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await download_file(
                url="https://example.com/path/to/archive.zip",
                dest_dir=temp_dir,
            )

        assert result == expected_file
