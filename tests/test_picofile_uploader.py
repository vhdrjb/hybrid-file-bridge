"""
Unit tests for the PicoFile uploader module.

Tests cover upload configuration, login flow, upload, and cleanup.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.picofile_uploader import upload


class TestPicoFileUpload:
    """Tests for the PicoFile upload function."""

    @pytest.mark.asyncio
    async def test_upload_missing_email(self, sample_file):
        """Test that upload fails when PICOFILE_EMAIL is not set."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("PICOFILE_EMAIL", None)
            with pytest.raises(RuntimeError, match="PICOFILE_EMAIL"):
                await upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_missing_password(self, sample_file, mock_env):
        """Test that upload fails when PICOFILE_PASSWORD is not set."""
        with patch.dict("os.environ", {"PICOFILE_EMAIL": "a@b.com"}, clear=False):
            import os

            os.environ.pop("PICOFILE_PASSWORD", None)
            with pytest.raises(RuntimeError, match="PICOFILE_PASSWORD"):
                await upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_env):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            await upload(Path("/tmp/nonexistent_picofile_test.bin"))

    @pytest.mark.asyncio
    async def test_upload_success(self, sample_file):
        """Test successful upload with mocked session."""
        env = {
            "PICOFILE_EMAIL": "test@example.com",
            "PICOFILE_PASSWORD": "testpass",
        }
        with patch.dict("os.environ", env, clear=False):
            mock_session = MagicMock()

            # Mock login page
            login_page = MagicMock()
            login_page.text = '<meta name="_token" content="csrf123">'
            mock_session.get.return_value = login_page
            mock_session.cookies = {"picofile_session": "abc"}

            # Mock upload response
            upload_resp = MagicMock()
            upload_resp.status_code = 200
            upload_resp.json.return_value = {
                "url": "https://s3.picofile.com/file/123/test.rar",
            }
            mock_session.post.return_value = upload_resp

            with patch("tools.picofile_uploader._create_session", return_value=mock_session):
                url = await upload(sample_file)

        assert "picofile.com" in url
        assert "test.rar" in url

    @pytest.mark.asyncio
    async def test_upload_all_endpoints_fail(self, sample_file):
        """Test that upload fails when all endpoints return errors."""
        env = {
            "PICOFILE_EMAIL": "test@example.com",
            "PICOFILE_PASSWORD": "testpass",
        }
        with patch.dict("os.environ", env, clear=False):
            mock_session = MagicMock()
            mock_session.get.return_value = MagicMock(text="")
            mock_session.cookies = {"picofile_session": "abc"}

            fail_resp = MagicMock()
            fail_resp.status_code = 500
            fail_resp.text = "Internal Error"
            mock_session.post.return_value = fail_resp

            with patch("tools.picofile_uploader._create_session", return_value=mock_session):
                with pytest.raises(RuntimeError, match="PicoFile upload failed"):
                    await upload(sample_file)
