"""
Shared test fixtures and configuration for pytest.

Provides reusable fixtures for temporary directories, mock environment
variables, file creation, and common test utilities used across all
test modules.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files.

    Yields:
        Path: Path to the temporary directory.
    """
    with tempfile.TemporaryDirectory(prefix="hrb_test_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_file(temp_dir):
    """Create a sample text file for testing.

    Creates a small text file with known content in the temp directory.

    Yields:
        Path: Path to the created sample file.
    """
    file_path = temp_dir / "sample.txt"
    file_path.write_text(
        "This is a test file for the Hybrid RAR File Bridge.\n"
        "It contains multiple lines of text for testing purposes.\n"
        "Line 3: Testing file operations.\n"
        "Line 4: End of file.\n"
    )
    yield file_path


@pytest.fixture
def large_sample_file(temp_dir):
    """Create a larger sample file for testing multi-part archives.

    Generates a file with repeating content to simulate a real download.

    Yields:
        Path: Path to the created sample file.
    """
    file_path = temp_dir / "large_sample.bin"
    # Create a 1MB file
    content = b"A" * (1024 * 1024)
    file_path.write_bytes(content)
    yield file_path


@pytest.fixture
def mock_env():
    """Set mock environment variables for testing.

    Temporarily sets all required environment variables to test values
    and restores the original values after the test.

    Yields:
        dict: The mock environment values that were set.
    """
    mock_values = {
        "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "AUTHORIZED_USERS": "123456789,987654321",
        "PROVIDER_PRIORITY": "Bale,Eitaa,ParsaSpace",
        "BALE_BOT_TOKEN": "test_bale_token",
        "BALE_CHAT_ID": "@test_channel",
        "EITAA_BOT_TOKEN": "test_eitaa_token",
        "EITAA_CHAT_ID": "123456789",
        "PARSASPACE_TOKEN": "test_parsaspace_token",
        "PARSASPACE_DOMAIN": "test.parsaspace.com",
        "SINGLE_UPLOAD_MAX_MB": "450",
        "RAR_VOLUME_SIZE_MB": "450",
    }

    original = {}
    for key, value in mock_values.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value

    yield mock_values

    # Restore original values
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def downloads_dir(temp_dir):
    """Create a downloads directory within the temp directory.

    Yields:
        Path: Path to the downloads directory.
    """
    d = temp_dir / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    yield d
