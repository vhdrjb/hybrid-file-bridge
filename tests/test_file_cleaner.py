"""
Unit tests for the file cleaner module.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.file_cleaner import get_valid_days, maybe_cleanup


class TestGetValidDays:
    """Tests for get_valid_days function."""

    def test_arvan_valid_days(self):
        """Test reading ARVAN_VALID_DAYS."""
        with patch.dict(os.environ, {"ARVAN_VALID_DAYS": "3"}):
            assert get_valid_days("ArvanCloud") == 3

    def test_liara_valid_days(self):
        """Test reading LIARA_VALID_DAYS."""
        with patch.dict(os.environ, {"LIARA_VALID_DAYS": "7"}):
            assert get_valid_days("Liara") == 7

    def test_picofile_valid_days(self):
        """Test reading PICOFILE_VALID_DAYS."""
        with patch.dict(os.environ, {"PICOFILE_VALID_DAYS": "2"}):
            assert get_valid_days("PicoFile") == 2

    def test_default_zero(self):
        """Test that default is 0 when env var not set."""
        with patch.dict(os.environ, {}, clear=False):
            assert get_valid_days("ArvanCloud") == 0

    def test_invalid_value_returns_zero(self):
        """Test that invalid value returns 0."""
        with patch.dict(os.environ, {"ARVAN_VALID_DAYS": "abc"}):
            assert get_valid_days("ArvanCloud") == 0

    def test_unknown_provider(self):
        """Test that unknown provider returns 0."""
        assert get_valid_days("UnknownProvider") == 0


class TestMaybeCleanup:
    """Tests for maybe_cleanup function."""

    @pytest.mark.asyncio
    async def test_cleanup_skipped_when_zero(self):
        """Test that cleanup is skipped when VALID_DAYS is 0."""
        assert await maybe_cleanup("ArvanCloud") == 0

    @pytest.mark.asyncio
    async def test_cleanup_calls_module(self):
        """Test that cleanup delegates to the provider module."""
        with patch.dict(os.environ, {"ARVAN_VALID_DAYS": "5"}):
            mock_cleanup = AsyncMock(return_value=3)
            mock_module = MagicMock()
            mock_module.cleanup_old_files = mock_cleanup

            with patch.dict("sys.modules", {"tools.arvan_uploader": mock_module}):
                result = await maybe_cleanup("ArvanCloud")

        assert result == 3
        mock_cleanup.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_cleanup_handles_error_gracefully(self):
        """Test that cleanup returns 0 on error."""
        with patch.dict(os.environ, {"LIARA_VALID_DAYS": "2"}):
            with patch.dict("sys.modules", {}, clear=False):
                import importlib

                with patch.object(importlib, "import_module", side_effect=ImportError("no module")):
                    result = await maybe_cleanup("Liara")

        assert result == 0
