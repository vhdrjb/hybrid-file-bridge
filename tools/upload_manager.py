"""
Upload manager with automatic provider fallback.

This module orchestrates file uploads across multiple Iranian file-sharing
providers (Bale, Eitaa, ParsaSpace). It implements a priority-based
fallback system: providers are tried in the order specified by the
PROVIDER_PRIORITY environment variable. If a provider fails or the file
exceeds its size limit, the next provider is tried automatically.

This design ensures maximum reliability — even if one provider is down
or has restrictions, the user still receives their download link.

Configuration (via environment variables):
    PROVIDER_PRIORITY: Comma-separated list of provider names in priority order.
    SINGLE_UPLOAD_MAX_MB: Maximum file size for a single upload attempt.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of an upload attempt.

    Attributes:
        url: The download URL or reference string returned by the provider.
        provider: Name of the provider that successfully handled the upload.
        file_name: Name of the uploaded file.
        file_size_mb: Size of the uploaded file in megabytes.
    """

    url: str
    provider: str
    file_name: str
    file_size_mb: float


@dataclass
class ProviderConfig:
    """Configuration for a single upload provider.

    Attributes:
        name: Display name of the provider.
        upload_func: Async function reference that performs the upload.
        max_size_mb: Maximum file size this provider accepts in megabytes.
        env_required: List of required environment variable names.
    """

    name: str
    upload_func: object
    max_size_mb: float
    env_required: list[str] = field(default_factory=list)


def get_providers() -> list[ProviderConfig]:
    """Build the ordered list of available upload providers.

    Reads the PROVIDER_PRIORITY environment variable to determine the
    order in which providers should be tried. Each provider's size limit
    is read from environment variables or defaults to reasonable values.

    Returns:
        List of ProviderConfig objects sorted by priority.
    """
    from tools.bale_uploader import upload as bale_upload
    from tools.eitaa_uploader import upload as eitaa_upload
    from tools.parsaspace_uploader import upload as parsaspace_upload

    all_providers = {
        "Bale": ProviderConfig(
            name="Bale",
            upload_func=bale_upload,
            max_size_mb=2 * 1024,  # ~2 GB
            env_required=["BALE_BOT_TOKEN", "BALE_CHAT_ID"],
        ),
        "Eitaa": ProviderConfig(
            name="Eitaa",
            upload_func=eitaa_upload,
            max_size_mb=2 * 1024,  # ~2 GB
            env_required=["EITAA_BOT_TOKEN", "EITAA_CHAT_ID"],
        ),
        "ParsaSpace": ProviderConfig(
            name="ParsaSpace",
            upload_func=parsaspace_upload,
            max_size_mb=50 * 1024,  # ~50 GB
            env_required=["PARSASPACE_TOKEN", "PARSASPACE_DOMAIN"],
        ),
    }

    priority_str = os.getenv("PROVIDER_PRIORITY", "Bale,Eitaa,ParsaSpace")
    priority_list = [p.strip() for p in priority_str.split(",")]

    ordered = []
    for name in priority_list:
        if name in all_providers:
            ordered.append(all_providers[name])
        else:
            logger.warning("Unknown provider '%s' in PROVIDER_PRIORITY, skipping", name)

    # Add any remaining providers not in the priority list
    for name, config in all_providers.items():
        if name not in priority_list:
            ordered.append(config)
            logger.info("Added provider '%s' (not in priority list)", name)

    if not ordered:
        logger.warning("No upload providers configured!")

    return ordered


def is_provider_configured(provider: ProviderConfig) -> bool:
    """Check whether all required environment variables are set for a provider.

    Args:
        provider: The provider configuration to check.

    Returns:
        True if all required env vars are present, False otherwise.
    """
    missing = [var for var in provider.env_required if not os.getenv(var)]
    if missing:
        logger.debug(
            "Provider %s is not configured (missing: %s)",
            provider.name,
            ", ".join(missing),
        )
        return False
    return True


async def upload_with_fallback(file_path: Path) -> UploadResult:
    """Upload a file trying each provider in priority order with fallback.

    For each configured provider, the manager checks:
      1. Whether the provider's required environment variables are set.
      2. Whether the file size is within the provider's limits.

    If both checks pass, the upload is attempted. On success, the result
    is returned immediately. On failure, the error is logged and the next
    provider is tried.

    Args:
        file_path: Path to the file to upload.

    Returns:
        UploadResult containing the download URL, provider name, and metadata.

    Raises:
        RuntimeError: If all providers fail or no providers are configured.
        FileNotFoundError: If the file does not exist.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size_bytes = file_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)

    providers = get_providers()

    if not providers:
        raise RuntimeError(
            "No upload providers available. Please configure at least one "
            "provider in PROVIDER_PRIORITY and set its environment variables."
        )

    errors = []
    attempted = []

    for provider in providers:
        # Check if provider is properly configured
        if not is_provider_configured(provider):
            logger.info("Skipping provider '%s': not configured", provider.name)
            continue

        # Check file size against provider limit
        if file_size_mb > provider.max_size_mb:
            logger.info(
                "Skipping provider '%s': file (%.2f MB) exceeds limit (%.2f MB)",
                provider.name,
                file_size_mb,
                provider.max_size_mb,
            )
            errors.append(
                f"{provider.name}: file too large "
                f"({file_size_mb:.1f} MB > {provider.max_size_mb} MB limit)"
            )
            continue

        attempted.append(provider.name)
        logger.info("Attempting upload to '%s' (%.2f MB)", provider.name, file_size_mb)

        try:
            url = await provider.upload_func(file_path)
            result = UploadResult(
                url=url,
                provider=provider.name,
                file_name=file_path.name,
                file_size_mb=file_size_mb,
            )
            logger.info("Upload successful via '%s': %s", provider.name, file_path.name)
            return result

        except Exception as e:
            error_msg = f"{provider.name}: {str(e)}"
            errors.append(error_msg)
            logger.error("Upload failed for provider '%s': %s", provider.name, e)
            continue

    # All providers failed
    if not attempted:
        raise RuntimeError(
            f"No upload providers were attempted. "
            f"Please configure at least one provider. "
            f"Provider errors: {'; '.join(errors)}"
        )

    error_summary = "; ".join(errors)
    raise RuntimeError(
        f"All upload providers failed for {file_path.name} "
        f"({file_size_mb:.2f} MB). "
        f"Attempted: {', '.join(attempted)}. "
        f"Errors: {error_summary}"
    )
