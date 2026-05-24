"""
Unit tests for the upload manager module.

Tests cover the provider fallback logic, provider configuration checks,
size limit enforcement, and all-fail scenarios. All uploader functions
are mocked to avoid real API calls.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tools.upload_manager import (
    UploadError,
    UploadResult,
    get_effective_max_upload_mb,
    get_providers,
    is_413_error,
    is_provider_configured,
    upload_with_fallback,
)


class TestGetProviders:
    """Tests for the get_providers function."""

    def test_returns_all_providers(self, mock_env):
        """Test that all three providers are returned when configured."""
        providers = get_providers()
        names = [p.name for p in providers]
        assert "Bale" in names
        assert "Eitaa" in names
        assert "ParsaSpace" in names

    def test_respects_priority_order(self, mock_env, monkeypatch):
        """Test that providers are returned in PROVIDER_PRIORITY order."""
        monkeypatch.setenv("PROVIDER_PRIORITY", "Eitaa,Bale,ParsaSpace")
        providers = get_providers()
        names = [p.name for p in providers]
        assert names == ["Eitaa", "Bale", "ParsaSpace"]

    def test_handles_unknown_providers(self, mock_env, monkeypatch):
        """Test that unknown provider names in priority are skipped."""
        monkeypatch.setenv("PROVIDER_PRIORITY", "UnknownProvider,Bale")
        providers = get_providers()
        names = [p.name for p in providers]
        assert "UnknownProvider" not in names
        assert "Bale" in names

    def test_partial_priority_list(self, mock_env, monkeypatch):
        """Test that providers not in priority list are appended at the end."""
        monkeypatch.setenv("PROVIDER_PRIORITY", "ParsaSpace")
        providers = get_providers()
        names = [p.name for p in providers]
        assert names[0] == "ParsaSpace"
        assert len(names) == 3  # All three should be present


class TestIsProviderConfigured:
    """Tests for the is_provider_configured function."""

    def test_configured_provider(self, mock_env):
        """Test that a provider with all env vars set is detected as configured."""
        from tools.upload_manager import ProviderConfig

        provider = ProviderConfig(
            name="TestProvider",
            upload_func=AsyncMock(),
            max_size_mb=100,
            env_required=["TELEGRAM_BOT_TOKEN"],  # Set by mock_env
        )
        assert is_provider_configured(provider) is True

    def test_not_configured_provider(self, monkeypatch):
        """Test that a provider with missing env vars is not configured."""
        monkeypatch.delenv("NONEXISTENT_TOKEN", raising=False)

        from tools.upload_manager import ProviderConfig

        provider = ProviderConfig(
            name="MissingProvider",
            upload_func=AsyncMock(),
            max_size_mb=100,
            env_required=["NONEXISTENT_TOKEN"],
        )
        assert is_provider_configured(provider) is False


class TestUploadWithFallback:
    """Tests for the upload_with_fallback function."""

    @pytest.mark.asyncio
    async def test_first_provider_succeeds(self, sample_file, mock_env):
        """Test that the first available provider is used when it succeeds."""
        with patch(
            "tools.upload_manager.get_providers",
            return_value=[
                _make_mock_provider("Bale", "https://example.com/file.rar", 100),
            ],
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=True,
            ):
                result = await upload_with_fallback(sample_file)

        assert result.provider == "Bale"
        assert result.url == "https://example.com/file.rar"

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self, sample_file, mock_env):
        """Test fallback to second provider when first fails."""
        providers = [
            _make_mock_provider(
                "ProviderA",
                None,
                100,
                side_effect=RuntimeError("ProviderA is down"),
            ),
            _make_mock_provider("ProviderB", "https://providerB.com/file.rar", 100),
        ]

        with patch(
            "tools.upload_manager.get_providers",
            return_value=providers,
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=True,
            ):
                result = await upload_with_fallback(sample_file)

        assert result.provider == "ProviderB"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, sample_file, mock_env):
        """Test that RuntimeError is raised when all providers fail."""
        providers = [
            _make_mock_provider(
                "ProviderA",
                None,
                100,
                side_effect=RuntimeError("Down"),
            ),
            _make_mock_provider(
                "ProviderB",
                None,
                100,
                side_effect=RuntimeError("Down too"),
            ),
        ]

        with patch(
            "tools.upload_manager.get_providers",
            return_value=providers,
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=True,
            ):
                with pytest.raises(RuntimeError, match="All upload providers failed"):
                    await upload_with_fallback(sample_file)

    @pytest.mark.asyncio
    async def test_file_too_large_skipped(self, sample_file, mock_env):
        """Test that providers with insufficient size limits are skipped."""
        providers = [
            _make_mock_provider("SmallProvider", None, 0.0001),  # Too small
            _make_mock_provider("BigProvider", "https://big.com/file.rar", 1000),
        ]

        with patch(
            "tools.upload_manager.get_providers",
            return_value=providers,
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=True,
            ):
                result = await upload_with_fallback(sample_file)

        assert result.provider == "BigProvider"

    @pytest.mark.asyncio
    async def test_unconfigured_provider_skipped(self, sample_file, mock_env):
        """Test that providers without config are skipped without error."""
        providers = [
            _make_mock_provider("Unconfigured", None, 100),
            _make_mock_provider("Configured", "https://ok.com/file.rar", 100),
        ]

        def mock_configured(p):
            return p.name == "Configured"

        with patch(
            "tools.upload_manager.get_providers",
            return_value=providers,
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                side_effect=mock_configured,
            ):
                result = await upload_with_fallback(sample_file)

        assert result.provider == "Configured"

    @pytest.mark.asyncio
    async def test_no_providers_configured(self, sample_file, mock_env):
        """Test error when no providers are available at all."""
        with patch(
            "tools.upload_manager.get_providers",
            return_value=[],
        ):
            with pytest.raises(RuntimeError, match="No upload providers available"):
                await upload_with_fallback(sample_file)

    @pytest.mark.asyncio
    async def test_file_not_found(self, mock_env):
        """Test that FileNotFoundError is raised for missing file."""
        missing = Path("/tmp/nonexistent_hrb_upload_test.bin")

        with pytest.raises(FileNotFoundError):
            await upload_with_fallback(missing)

    @pytest.mark.asyncio
    async def test_no_attempted_providers(self, sample_file, mock_env):
        """Test error when providers exist but none are attempted."""
        providers = [
            _make_mock_provider("A", None, 100),
        ]

        with patch(
            "tools.upload_manager.get_providers",
            return_value=providers,
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=False,  # All unconfigured
            ):
                with pytest.raises(RuntimeError, match="No upload providers were attempted"):
                    await upload_with_fallback(sample_file)


def _make_mock_provider(name, return_url, max_size_mb, side_effect=None):
    """Helper to create a mock ProviderConfig."""
    from tools.upload_manager import ProviderConfig

    if side_effect:
        mock_func = AsyncMock(side_effect=side_effect)
    elif return_url:
        mock_func = AsyncMock(return_value=return_url)
    else:
        mock_func = AsyncMock(return_value="some_url")

    return ProviderConfig(
        name=name,
        upload_func=mock_func,
        max_size_mb=max_size_mb,
        env_required=[f"{name.upper()}_TOKEN"],
    )


class TestUploadResult:
    """Tests for the UploadResult dataclass."""

    def test_creation(self):
        """Test UploadResult can be created with all fields."""
        result = UploadResult(
            url="https://example.com/file.rar",
            provider="Bale",
            file_name="file.rar",
            file_size_mb=10.5,
        )
        assert result.url == "https://example.com/file.rar"
        assert result.provider == "Bale"
        assert result.file_name == "file.rar"
        assert result.file_size_mb == 10.5


class TestUploadError:
    """Tests for the UploadError exception class."""

    def test_upload_error_is_runtime_error(self):
        """Test that UploadError extends RuntimeError."""
        exc = UploadError(
            file_path=Path("test.rar"),
            file_size_mb=100.0,
            attempted=["Bale"],
            errors=["Bale: 413 error"],
        )
        assert isinstance(exc, RuntimeError)

    def test_upload_error_message(self):
        """Test that UploadError contains file info in its message."""
        exc = UploadError(
            file_path=Path("big_file.rar"),
            file_size_mb=438.17,
            attempted=["Bale"],
            errors=["Bale: HTTP 413"],
        )
        assert "big_file.rar" in str(exc)
        assert "438.17" in str(exc)
        assert "413" in str(exc)

    def test_upload_error_attributes(self):
        """Test that UploadError stores structured attributes."""
        exc = UploadError(
            file_path=Path("test.rar"),
            file_size_mb=50.0,
            attempted=["Bale", "Eitaa"],
            errors=["Bale: down", "Eitaa: down"],
        )
        assert exc.file_size_mb == 50.0
        assert exc.attempted == ["Bale", "Eitaa"]
        assert len(exc.errors) == 2


class TestIs413Error:
    """Tests for the is_413_error helper function."""

    def test_detects_413_status_code(self):
        """Test detection of HTTP 413 status code in error message."""
        assert is_413_error(RuntimeError("Bale HTTP API returned status 413: <html>")) is True

    def test_detects_entity_too_large(self):
        """Test detection of 'entity too large' in error message."""
        assert is_413_error(RuntimeError("entity too large")) is True

    def test_detects_request_entity_too_large(self):
        """Test detection of 'request entity too large' in error message."""
        assert is_413_error(RuntimeError("413 Request Entity Too Large")) is True

    def test_not_413_for_other_errors(self):
        """Test that non-413 errors are not flagged."""
        assert is_413_error(RuntimeError("Connection refused")) is False
        assert is_413_error(RuntimeError("500 Internal Server Error")) is False
        assert is_413_error(RuntimeError("timeout")) is False


class TestGetEffectiveMaxUploadMb:
    """Tests for get_effective_max_upload_mb function."""

    def test_returns_min_of_configured_providers(self):
        """Test that the smallest configured provider limit is returned."""
        with patch(
            "tools.upload_manager.get_providers",
            return_value=[
                _make_mock_provider("Bale", "url", 50),
                _make_mock_provider("ParsaSpace", "url", 51200),
            ],
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=True,
            ):
                assert get_effective_max_upload_mb() == 50.0

    def test_returns_default_when_no_provider_configured(self):
        """Test that 50 MB is returned when no provider is configured."""
        with patch(
            "tools.upload_manager.get_providers",
            return_value=[_make_mock_provider("Bale", "url", 50)],
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=False,
            ):
                assert get_effective_max_upload_mb() == 50.0

    def test_uses_env_var_for_bale_limit(self, monkeypatch):
        """Test that BALE_MAX_UPLOAD_MB env var is respected."""
        monkeypatch.setenv("BALE_MAX_UPLOAD_MB", "100")
        # Force re-import to pick up the env var
        import importlib
        import tools.upload_manager
        importlib.reload(tools.upload_manager)
        try:
            providers = tools.upload_manager.get_providers()
            bale = next(p for p in providers if p.name == "Bale")
            assert bale.max_size_mb == 100.0
        finally:
            monkeypatch.delenv("BALE_MAX_UPLOAD_MB", raising=False)
            importlib.reload(tools.upload_manager)
