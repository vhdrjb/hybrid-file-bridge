"""
Unified file cleaner — coordinates age-based cleanup across providers.

Before each upload the upload manager calls ``maybe_cleanup()`` which
checks the per-provider ``*_VALID_DAYS`` environment variable.  When the
value is greater than zero, files older than that many days are deleted
from the provider's storage.

There is **no polling / cron** — cleanup happens inline, right before a
new file is uploaded.  This keeps things simple and avoids background
threads.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Mapping: provider name → (env var for valid days, cleanup coroutine path)
_CLEANUP_REGISTRY: dict[str, str] = {
    "ArvanCloud": "tools.arvan_uploader",
    "Liara": "tools.liara_uploader",
    "PicoFile": "tools.picofile_uploader",
}


def get_valid_days(provider_name: str) -> int:
    """Return the ``*_VALID_DAYS`` value for a provider.

    Environment variable names follow the pattern
    ``{PROVIDER}_VALID_DAYS`` (e.g. ``ARVAN_VALID_DAYS``).
    A value of ``0`` (the default) means cleanup is disabled.

    Args:
        provider_name: Provider display name (e.g. ``ArvanCloud``).

    Returns:
        Number of days after which files should be deleted (0 = off).
    """
    env_map = {
        "ArvanCloud": "ARVAN_VALID_DAYS",
        "Liara": "LIARA_VALID_DAYS",
        "PicoFile": "PICOFILE_VALID_DAYS",
    }
    env_key = env_map.get(provider_name)
    if not env_key:
        return 0
    try:
        return int(os.getenv(env_key, "0"))
    except (ValueError, TypeError):
        logger.warning("Invalid %s value, ignoring", env_key)
        return 0


async def maybe_cleanup(provider_name: str) -> int:
    """Run cleanup for a provider if VALID_DAYS is configured.

    Args:
        provider_name: Provider display name (e.g. ``ArvanCloud``).

    Returns:
        Number of objects/files deleted, or 0 if disabled or errored.
    """
    valid_days = get_valid_days(provider_name)
    if valid_days <= 0:
        return 0

    module_path = _CLEANUP_REGISTRY.get(provider_name)
    if not module_path:
        return 0

    try:
        import importlib

        mod = importlib.import_module(module_path)
        deleted = await mod.cleanup_old_files(valid_days)
        if deleted:
            logger.info(
                "Cleaned up %d old objects from %s (valid_days=%d)",
                deleted,
                provider_name,
                valid_days,
            )
        return deleted
    except Exception as e:
        logger.error("Cleanup failed for %s: %s", provider_name, e)
        return 0
