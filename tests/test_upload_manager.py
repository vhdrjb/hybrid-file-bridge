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
    UploadResult,
    get_providers,
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
        mock_result = UploadResult(
            url="https://example.com/file.rar",
            provider="Bale",
            file_name=sample_file.name,
            file_size_mb=0.01,
        )

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
                "ProviderA", None, 100,
                side_effect=RuntimeError("ProviderA is down"),
            ),
            _make_mock_provider("ProviderB", "https://providerB.com/file.rar", 100),
        ]

        with patch(
            "tools.upload_manager.get_providers", return_value=providers,
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
                "ProviderA", None, 100,
                side_effect=RuntimeError("Down"),
            ),
            _make_mock_provider(
                "ProviderB", None, 100,
                side_effect=RuntimeError("Down too"),
            ),
        ]

        with patch(
            "tools.upload_manager.get_providers", return_value=providers,
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
            "tools.upload_manager.get_providers", return_value=providers,
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
            "tools.upload_manager.get_providers", return_value=providers,
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
            "tools.upload_manager.get_providers", return_value=[],
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
            "tools.upload_manager.get_providers", return_value=providers,
        ):
            with patch(
                "tools.upload_manager.is_provider_configured",
                return_value=False,  # All unconfigured
            ):
                with pytest.raises(RuntimeError, match="No upload providers were attempted"):
                    await upload_with_fallback(sample_file)


def _make_mock_provider(
    name, return_url, max_size_mb, side_effect=None
):
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
