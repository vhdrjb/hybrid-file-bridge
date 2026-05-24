"""
Unit tests for individual uploader modules.

Tests cover each uploader (Bale, Eitaa, ParsaSpace) with mocked
external API calls, verifying success responses, error handling,
missing configuration, and file validation.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.bale_uploader import upload as bale_upload
from tools.eitaa_uploader import upload as eitaa_upload
from tools.parsaspace_uploader import upload as parsaspace_upload


class TestBaleUploader:
    """Tests for the Bale Messenger uploader."""

    @pytest.mark.asyncio
    async def test_upload_success(self, sample_file, mock_env):
        """Test successful upload to Bale via balebot package."""
        mock_bot = MagicMock()
        mock_message = MagicMock()
        mock_message.document = MagicMock()
        mock_message.document.file_id = "bale_file_12345"
        mock_bot.send_document.return_value = mock_message

        with patch.dict("sys.modules", {"balebot": MagicMock(Bot=lambda **kw: mock_bot)}):
            result = await bale_upload(sample_file)

        assert "bale_file_12345" in result
        assert "Bale upload successful" in result

    @pytest.mark.asyncio
    async def test_upload_missing_token(self, sample_file, monkeypatch):
        """Test that missing BALE_BOT_TOKEN raises RuntimeError."""
        monkeypatch.delenv("BALE_BOT_TOKEN", raising=False)
        monkeypatch.delenv("BALE_CHAT_ID", raising=False)

        with pytest.raises(RuntimeError, match="BALE_BOT_TOKEN"):
            await bale_upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_missing_chat_id(self, sample_file, monkeypatch):
        """Test that missing BALE_CHAT_ID raises RuntimeError."""
        monkeypatch.setenv("BALE_BOT_TOKEN", "token")
        monkeypatch.delenv("BALE_CHAT_ID", raising=False)

        with pytest.raises(RuntimeError, match="BALE_CHAT_ID"):
            await bale_upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_env):
        """Test that non-existent file raises FileNotFoundError."""
        missing = Path("/tmp/nonexistent_hrb_test_file.bin")

        with pytest.raises(FileNotFoundError):
            await bale_upload(missing)

    @pytest.mark.asyncio
    async def test_upload_http_fallback_success(self, sample_file, mock_env):
        """Test HTTP API fallback when balebot is not installed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"document": {"file_id": "http_fallback_123"}},
        }

        with patch.dict("sys.modules", {"balebot": None}):
            with patch("requests.post", return_value=mock_response):
                result = await bale_upload(sample_file)

        assert "http_fallback_123" in result

    @pytest.mark.asyncio
    async def test_upload_http_fallback_failure(self, sample_file, mock_env):
        """Test HTTP API fallback error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden: bot was blocked by the user"

        with patch.dict("sys.modules", {"balebot": None}):
            with patch("requests.post", return_value=mock_response):
                with pytest.raises(RuntimeError, match="status 403"):
                    await bale_upload(sample_file)


class TestEitaaUploader:
    """Tests for the Eitaa Messenger uploader."""

    @pytest.mark.asyncio
    async def test_upload_success(self, sample_file, mock_env):
        """Test successful upload to Eitaa."""
        mock_eitaa = MagicMock()
        mock_eitaa.send_file.return_value = {
            "ok": True,
            "result": {"file_id": "eitaa_file_67890"},
        }

        with patch.dict("sys.modules", {"eitaa": MagicMock(Eitaa=lambda token: mock_eitaa)}):
            result = await eitaa_upload(sample_file)

        assert result == "https://eitaa.com/file/eitaa_file_67890"

    @pytest.mark.asyncio
    async def test_upload_missing_token(self, sample_file, monkeypatch):
        """Test that missing EITAA_BOT_TOKEN raises RuntimeError."""
        monkeypatch.delenv("EITAA_BOT_TOKEN", raising=False)
        monkeypatch.delenv("EITAA_CHAT_ID", raising=False)

        with pytest.raises(RuntimeError, match="EITAA_BOT_TOKEN"):
            await eitaa_upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_api_error(self, sample_file, mock_env):
        """Test handling of Eitaa API error response."""
        mock_eitaa = MagicMock()
        mock_eitaa.send_file.return_value = {
            "ok": False,
            "description": "Bad Request: file too large",
        }

        with patch.dict("sys.modules", {"eitaa": MagicMock(Eitaa=lambda token: mock_eitaa)}):
            with pytest.raises(RuntimeError, match="Eitaa API error"):
                await eitaa_upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_env):
        """Test that non-existent file raises FileNotFoundError."""
        missing = Path("/tmp/nonexistent_hrb_test_file.bin")

        with pytest.raises(FileNotFoundError):
            await eitaa_upload(missing)

    @pytest.mark.asyncio
    async def test_upload_http_fallback_success(self, sample_file, mock_env):
        """Test HTTP API fallback when eitaa package is not installed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"document": {"file_id": "http_eitaa_123"}},
        }

        with patch.dict("sys.modules", {"eitaa": None}):
            with patch("requests.post", return_value=mock_response):
                result = await eitaa_upload(sample_file)

        assert result == "https://eitaa.com/file/http_eitaa_123"


class TestParsaSpaceUploader:
    """Tests for the ParsaSpace uploader."""

    @pytest.mark.asyncio
    async def test_upload_success(self, sample_file, mock_env):
        """Test successful upload to ParsaSpace."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": "success",
            "url": "https://test.parsaspace.com/sample.txt",
        }

        with patch("requests.post", return_value=mock_response):
            result = await parsaspace_upload(sample_file)

        assert result == "https://test.parsaspace.com/sample.txt"

    @pytest.mark.asyncio
    async def test_upload_success_with_ok(self, sample_file, mock_env):
        """Test successful upload with 'ok' format response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "download_url": "https://test.parsaspace.com/sample.txt",
        }

        with patch("requests.post", return_value=mock_response):
            result = await parsaspace_upload(sample_file)

        assert result == "https://test.parsaspace.com/sample.txt"

    @pytest.mark.asyncio
    async def test_upload_missing_token(self, sample_file, monkeypatch):
        """Test that missing PARSASPACE_TOKEN raises RuntimeError."""
        monkeypatch.delenv("PARSASPACE_TOKEN", raising=False)
        monkeypatch.delenv("PARSASPACE_DOMAIN", raising=False)

        with pytest.raises(RuntimeError, match="PARSASPACE_TOKEN"):
            await parsaspace_upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_api_failure(self, sample_file, mock_env):
        """Test handling of ParsaSpace API failure response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": "error",
            "message": "Storage quota exceeded",
        }

        with patch("requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Storage quota exceeded"):
                await parsaspace_upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_http_error(self, sample_file, mock_env):
        """Test handling of HTTP error responses."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError, match="status 500"):
                await parsaspace_upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_env):
        """Test that non-existent file raises FileNotFoundError."""
        missing = Path("/tmp/nonexistent_hrb_test_file.bin")

        with pytest.raises(FileNotFoundError):
            await parsaspace_upload(missing)
