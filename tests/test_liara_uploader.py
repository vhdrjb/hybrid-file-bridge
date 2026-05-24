"""
Unit tests for the Liara uploader module.

Tests cover upload configuration, presigned-URL flow, and cleanup.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.liara_uploader import cleanup_old_files, upload


class TestLiaraUpload:
    """Tests for the Liara upload function."""

    @pytest.mark.asyncio
    async def test_upload_missing_api_key(self, sample_file):
        """Test that upload fails when LIARA_API_KEY is not set."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("LIARA_API_KEY", None)
            with pytest.raises(RuntimeError, match="LIARA_API_KEY"):
                await upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_missing_bucket(self, sample_file, mock_env):
        """Test that upload fails when LIARA_BUCKET is not set."""
        with patch.dict("os.environ", {"LIARA_API_KEY": "key"}, clear=False):
            import os

            os.environ.pop("LIARA_BUCKET", None)
            with pytest.raises(RuntimeError, match="LIARA_BUCKET"):
                await upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_env):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            await upload(Path("/tmp/nonexistent_liara_test.bin"))

    @pytest.mark.asyncio
    async def test_upload_success(self, sample_file):
        """Test successful upload flow via mocked presigned URL."""
        env = {
            "LIARA_API_KEY": "test_key",
            "LIARA_BUCKET": "test-bucket",
        }
        with patch.dict("os.environ", env, clear=False):
            # Mock presign response
            presign_resp = MagicMock()
            presign_resp.status_code = 200
            presign_resp.json.return_value = {
                "upload_url": "https://storage.iran.liara.ir/presigned-put",
                "download_url": "https://test-bucket.storage.iran.liara.ir/file.rar",
            }

            # Mock PUT response
            put_resp = MagicMock()
            put_resp.status_code = 200

            with patch("tools.liara_uploader.requests") as mock_requests:
                mock_requests.post.return_value = presign_resp
                mock_requests.put.return_value = put_resp

                url = await upload(sample_file)

        assert "file.rar" in url
        mock_requests.post.assert_called_once()
        mock_requests.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_presign_failure(self, sample_file):
        """Test that upload fails when presign request returns error."""
        env = {
            "LIARA_API_KEY": "key",
            "LIARA_BUCKET": "bucket",
        }
        with patch.dict("os.environ", env, clear=False):
            presign_resp = MagicMock()
            presign_resp.status_code = 403
            presign_resp.text = "Forbidden"

            with patch("tools.liara_uploader.requests") as mock_requests:
                mock_requests.post.return_value = presign_resp

                with pytest.raises(RuntimeError, match="Liara presign request failed"):
                    await upload(sample_file)


class TestLiaraCleanup:
    """Tests for the Liara cleanup_old_files function."""

    @pytest.mark.asyncio
    async def test_cleanup_disabled_when_zero_days(self):
        """Test that cleanup returns 0 when valid_days is 0."""
        assert await cleanup_old_files(0) == 0

    @pytest.mark.asyncio
    async def test_cleanup_skips_when_not_configured(self):
        """Test that cleanup returns 0 when env vars are missing."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            for k in ("LIARA_API_KEY", "LIARA_BUCKET"):
                os.environ.pop(k, None)
            assert await cleanup_old_files(7) == 0
