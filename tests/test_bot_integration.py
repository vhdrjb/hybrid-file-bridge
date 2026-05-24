"""
Integration tests for the Telegram bot.

Tests simulate the full conversation flow: user sends a URL, bot processes
it, and replies with download links. All external operations (download,
archive, upload) are mocked to avoid network calls and file system
dependencies.

These tests verify that the bot's handler correctly orchestrates the
pipeline and produces the expected user-facing messages.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User

from bot import (
    CALLBACK_PREFIX,
    extract_url,
    generate_password,
    handle_link,
    handle_youtube_quality_callback,
    is_authorized,
    start,
)


def _make_update(text: str, user_id: int = 123456789) -> Update:
    """Create a mock Telegram Update for testing.

    Args:
        text: Message text content.
        user_id: Telegram user ID (default authorized user).

    Returns:
        A mock Update object with a message containing the text.
    """
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = "TestUser"
    user.username = "testuser"

    chat = MagicMock(spec=Chat)
    chat.id = user_id

    message = MagicMock(spec=Message)
    message.text = text
    message.from_user = user
    message.chat = chat
    message.edit_text = AsyncMock()
    message.reply_text = AsyncMock(return_value=message)

    update = MagicMock(spec=Update)
    update.message = message
    update.effective_user = user

    return update


class TestBotHelpers:
    """Tests for bot helper functions."""

    def test_generate_password_length(self):
        """Test that generated password has the correct length."""
        for length in [8, 16, 24, 32]:
            password = generate_password(length)
            assert len(password) == length

    def test_generate_password_has_mixed_chars(self):
        """Test that generated password contains all character types."""
        for _ in range(100):  # Run multiple times due to randomness
            password = generate_password(16)
            has_upper = any(c.isupper() for c in password)
            has_lower = any(c.islower() for c in password)
            has_digit = any(c.isdigit() for c in password)
            has_special = any(c in "@#$%&*!?+=" for c in password)
            if has_upper and has_lower and has_digit and has_special:
                return
        pytest.fail("Generated 100 passwords but none had all character types")

    def test_generate_password_uniqueness(self):
        """Test that generated passwords are unique across calls."""
        passwords = {generate_password(16) for _ in range(50)}
        assert len(passwords) == 50, "Generated duplicate passwords"

    def test_extract_url_simple(self):
        """Test URL extraction from a simple message."""
        assert extract_url("https://example.com/file.zip") == "https://example.com/file.zip"

    def test_extract_url_from_text(self):
        """Test URL extraction from text surrounding a URL."""
        result = extract_url("Please download this: https://example.com/path/to/file.rar thanks!")
        assert result == "https://example.com/path/to/file.rar"

    def test_extract_url_none(self):
        """Test that None is returned when no URL is present."""
        assert extract_url("Hello, no URL here") is None

    def test_extract_url_http_and_https(self):
        """Test extraction of both HTTP and HTTPS URLs."""
        assert extract_url("http://example.com/file.zip").startswith("http://")
        assert extract_url("https://example.com/file.zip").startswith("https://")

    def test_is_authorized(self, mock_env):
        """Test authorization check for known user."""
        assert is_authorized(123456789) is True

    def test_is_unauthorized(self, mock_env):
        """Test authorization check for unknown user."""
        assert is_authorized(999999999) is False

    def test_is_authorized_empty_list(self, monkeypatch):
        """Test authorization with empty authorized users list."""
        monkeypatch.setenv("AUTHORIZED_USERS", "")
        from bot import is_authorized as check

        assert check(123456789) is False


class TestStartHandler:
    """Tests for the /start command handler."""

    @pytest.mark.asyncio
    async def test_start_authorized(self, mock_env):
        """Test that authorized users receive welcome message."""
        update = _make_update("/start", user_id=123456789)
        context = MagicMock()

        await start(update, context)

        update.message.reply_text.assert_called_once()
        args = update.message.reply_text.call_args
        assert "Hybrid RAR File Bridge" in str(args)

    @pytest.mark.asyncio
    async def test_start_unauthorized(self, mock_env):
        """Test that unauthorized users receive rejection message."""
        update = _make_update("/start", user_id=999999999)
        context = MagicMock()

        await start(update, context)

        update.message.reply_text.assert_called_once()
        args = update.message.reply_text.call_args
        assert "not authorized" in str(args).lower()


class TestHandleLinkHandler:
    """Tests for the link handling pipeline."""

    @pytest.mark.asyncio
    async def test_handle_link_no_url(self, mock_env):
        """Test handling a message without a URL."""
        update = _make_update("Hello there!", user_id=123456789)
        context = MagicMock()

        await handle_link(update, context)

        # Bot sends reply_text for no-URL case
        reply_calls = update.message.reply_text.call_args_list
        assert any("No valid URL" in str(c) for c in reply_calls)

    @pytest.mark.asyncio
    async def test_handle_link_unauthorized(self, mock_env):
        """Test that unauthorized users are rejected."""
        update = _make_update("https://example.com/file.zip", user_id=999999999)
        context = MagicMock()

        await handle_link(update, context)

        update.message.reply_text.assert_called_once()
        args = update.message.reply_text.call_args
        assert "not authorized" in str(args).lower()

    @pytest.mark.asyncio
    async def test_handle_link_single_file_success(self, mock_env, temp_dir, sample_file):
        """Test the full pipeline for a single file upload."""
        # Move sample file to downloads dir to simulate aria2c output
        downloads = temp_dir / "downloads"
        downloads.mkdir()
        downloaded = downloads / "sample.txt"
        downloaded.write_bytes(sample_file.read_bytes())

        update = _make_update("https://example.com/sample.txt", user_id=123456789)
        context = MagicMock()

        # Mock the download function to return our sample file
        mock_download = AsyncMock(return_value=downloaded)
        # Mock archive creation to create a real file
        mock_archive = AsyncMock(side_effect=lambda **kwargs: sample_file)  # return something
        # Mock upload to return a URL
        from tools.upload_manager import UploadResult

        mock_upload = AsyncMock(
            return_value=UploadResult(
                url="https://bale.example.com/file.rar",
                provider="Bale",
                file_name="file.rar",
                file_size_mb=0.01,
            )
        )

        with patch("bot.download_file", mock_download):
            with patch("bot.create_rar_archive", mock_archive):
                with patch("bot.upload_with_fallback", mock_upload):
                    with patch("bot.DOWNLOADS_DIR", downloads):
                        await handle_link(update, context)

        # Verify edit_text was called with status updates
        edit_calls = update.message.edit_text.call_args_list
        assert len(edit_calls) >= 1
        # The final edit should contain success info
        final_text = str(edit_calls[-1])
        assert "File Ready" in final_text or "password" in final_text.lower()

    @pytest.mark.asyncio
    async def test_handle_link_download_error(self, mock_env):
        """Test error handling when download fails."""
        update = _make_update("https://example.com/big_file.zip", user_id=123456789)
        context = MagicMock()

        mock_download = AsyncMock(side_effect=RuntimeError("aria2c failed with return code 3"))

        with patch("bot.download_file", mock_download):
            await handle_link(update, context)

        # Verify error message was sent via edit_text
        all_calls = str(update.message.edit_text.call_args_list) + str(
            update.message.reply_text.call_args_list
        )
        assert "Error" in all_calls or "error" in all_calls.lower()


class TestYoutubeRouting:
    """Tests that YouTube URLs are correctly routed."""

    @pytest.mark.asyncio
    async def test_youtube_url_routed_to_youtube_handler(self, mock_env):
        """Test that YouTube URLs trigger the YouTube quality flow."""
        update = _make_update(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            user_id=123456789,
        )
        context = MagicMock()
        context.user_data = {}

        mock_yt_handler = AsyncMock()

        with patch("bot._handle_youtube_url", mock_yt_handler):
            await handle_link(update, context)

        mock_yt_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_youtu_be_routed(self, mock_env):
        """Test that youtu.be short URLs are routed to YouTube handler."""
        update = _make_update(
            "https://youtu.be/dQw4w9WgXcQ",
            user_id=123456789,
        )
        context = MagicMock()
        context.user_data = {}

        mock_yt_handler = AsyncMock()

        with patch("bot._handle_youtube_url", mock_yt_handler):
            await handle_link(update, context)

        mock_yt_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_youtube_not_routed(self, mock_env, temp_dir, sample_file):
        """Test that non-YouTube URLs go through normal download flow."""
        downloads = temp_dir / "downloads"
        downloads.mkdir()
        downloaded = downloads / "sample.txt"
        downloaded.write_bytes(sample_file.read_bytes())

        update = _make_update(
            "https://example.com/file.zip",
            user_id=123456789,
        )
        context = MagicMock()
        context.user_data = {}

        mock_yt_handler = AsyncMock()
        mock_download = AsyncMock(return_value=downloaded)
        mock_archive = AsyncMock(return_value=sample_file)
        from tools.upload_manager import UploadResult

        mock_upload = AsyncMock(
            return_value=UploadResult(
                url="https://example.com/file.rar",
                provider="Bale",
                file_name="file.rar",
                file_size_mb=0.01,
            )
        )

        with patch("bot._handle_youtube_url", mock_yt_handler):
            with patch("bot.download_file", mock_download):
                with patch("bot.create_rar_archive", mock_archive):
                    with patch("bot.upload_with_fallback", mock_upload):
                        with patch("bot.DOWNLOADS_DIR", downloads):
                            await handle_link(update, context)

        mock_yt_handler.assert_not_called()


class TestYoutubeQualityCallback:
    """Tests for the YouTube quality callback handler."""

    def _make_callback_update(self, callback_data: str, user_id: int = 123456789):
        """Create a mock callback query update."""
        user = MagicMock(spec=User)
        user.id = user_id
        user.first_name = "TestUser"

        message = MagicMock(spec=Message)
        message.edit_text = AsyncMock()

        callback_query = MagicMock()
        callback_query.data = callback_data
        callback_query.answer = AsyncMock()
        callback_query.edit_message_text = AsyncMock()
        callback_query.message = message

        update = MagicMock(spec=Update)
        update.callback_query = callback_query
        update.effective_user = user

        return update

    @pytest.mark.asyncio
    async def test_callback_authorized_success(self, mock_env, temp_dir):
        """Test successful quality selection and download pipeline."""
        yt_dir = temp_dir / "yt_video"
        yt_dir.mkdir()
        video_file = yt_dir / "Test Video.mp4"
        video_file.write_bytes(b"fake video data")

        update = self._make_callback_update(f"{CALLBACK_PREFIX}137")
        context = MagicMock()
        context.user_data = {
            "yt_url": "https://youtube.com/watch?v=test",
            "yt_title": "Test Video Title",
            "yt_formats": [],
        }

        mock_download = AsyncMock(return_value=video_file)
        mock_archive = AsyncMock(return_value=video_file)
        from tools.upload_manager import UploadResult

        mock_upload = AsyncMock(
            return_value=UploadResult(
                url="https://example.com/video.rar",
                provider="ParsaSpace",
                file_name="video.rar",
                file_size_mb=5.0,
            )
        )

        with patch("bot.download_video", mock_download):
            with patch("bot.create_rar_archive", mock_archive):
                with patch("bot.upload_with_fallback", mock_upload):
                    await handle_youtube_quality_callback(update, context)

        update.callback_query.answer.assert_called_once()
        # Should have edit_message_text calls (status + final)
        assert update.callback_query.edit_message_text.called

    @pytest.mark.asyncio
    async def test_callback_unauthorized(self, mock_env):
        """Test that unauthorized users get rejected on callback."""
        update = self._make_callback_update(
            f"{CALLBACK_PREFIX}137",
            user_id=999999999,
        )
        context = MagicMock()
        context.user_data = {}

        await handle_youtube_quality_callback(update, context)

        update.callback_query.edit_message_text.assert_called_once()
        args = update.callback_query.edit_message_text.call_args
        assert "not authorized" in str(args).lower()

    @pytest.mark.asyncio
    async def test_callback_expired_session(self, mock_env):
        """Test handling of expired session (no stored URL)."""
        update = self._make_callback_update(f"{CALLBACK_PREFIX}137")
        context = MagicMock()
        context.user_data = {}  # No yt_url stored

        await handle_youtube_quality_callback(update, context)

        args = update.callback_query.edit_message_text.call_args
        assert "Session expired" in str(args) or "expired" in str(args).lower()

    @pytest.mark.asyncio
    async def test_callback_ignores_non_yt_callbacks(self, mock_env):
        """Test that non-YouTube callbacks are ignored."""
        update = self._make_callback_update("some_other_callback:123")
        context = MagicMock()
        context.user_data = {}

        await handle_youtube_quality_callback(update, context)

        # Should answer but NOT edit the message
        update.callback_query.answer.assert_called_once()
        update.callback_query.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_download_error(self, mock_env):
        """Test error handling when YouTube download fails in callback."""
        update = self._make_callback_update(f"{CALLBACK_PREFIX}137")
        context = MagicMock()
        context.user_data = {
            "yt_url": "https://youtube.com/watch?v=test",
            "yt_title": "Test",
            "yt_formats": [],
        }

        mock_download = AsyncMock(side_effect=RuntimeError("yt-dlp download failed"))

        with patch("bot.download_video", mock_download):
            await handle_youtube_quality_callback(update, context)

        args = update.callback_query.edit_message_text.call_args_list[-1]
        assert "Error" in str(args)

    @pytest.mark.asyncio
    async def test_callback_cleans_up_user_data(self, mock_env, temp_dir):
        """Test that stored job data is cleaned up after success."""
        yt_dir = temp_dir / "yt_video"
        yt_dir.mkdir()
        video_file = yt_dir / "Test Video.mp4"
        video_file.write_bytes(b"fake video data")

        update = self._make_callback_update(f"{CALLBACK_PREFIX}137")
        context = MagicMock()
        context.user_data = {
            "yt_url": "https://youtube.com/watch?v=test",
            "yt_title": "Test Video",
            "yt_formats": [],
        }

        mock_download = AsyncMock(return_value=video_file)
        mock_archive = AsyncMock(return_value=video_file)
        from tools.upload_manager import UploadResult

        mock_upload = AsyncMock(
            return_value=UploadResult(
                url="https://example.com/video.rar",
                provider="Bale",
                file_name="video.rar",
                file_size_mb=1.0,
            )
        )

        with patch("bot.download_video", mock_download):
            with patch("bot.create_rar_archive", mock_archive):
                with patch("bot.upload_with_fallback", mock_upload):
                    await handle_youtube_quality_callback(update, context)

        # Verify cleanup
        assert "yt_url" not in context.user_data
        assert "yt_title" not in context.user_data
