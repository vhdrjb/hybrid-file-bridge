"""
Unit tests for the ArvanCloud uploader module.

Tests cover upload configuration checks, S3 upload flow, and the
cleanup (age-based deletion) logic.  All S3 calls are mocked.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.arvan_uploader import cleanup_old_files, upload


class TestArvanUpload:
    """Tests for the ArvanCloud upload function."""

    @pytest.mark.asyncio
    async def test_upload_missing_access_key(self, sample_file):
        """Test that upload fails when ARVAN_ACCESS_KEY is not set."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("ARVAN_ACCESS_KEY", None)
            with pytest.raises(RuntimeError, match="ARVAN_ACCESS_KEY"):
                await upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_missing_bucket(self, sample_file, mock_env):
        """Test that upload fails when ARVAN_BUCKET is not set."""
        with patch.dict("os.environ", {"ARVAN_ACCESS_KEY": "key", "ARVAN_SECRET_KEY": "secret"}, clear=False):
            import os

            os.environ.pop("ARVAN_BUCKET", None)
            with pytest.raises(RuntimeError, match="ARVAN_BUCKET"):
                await upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_missing_secret_key(self, sample_file, mock_env):
        """Test that upload fails when ARVAN_SECRET_KEY is not set."""
        with patch.dict("os.environ", {"ARVAN_ACCESS_KEY": "key"}, clear=False):
            import os

            os.environ.pop("ARVAN_SECRET_KEY", None)
            with pytest.raises(RuntimeError, match="ARVAN_SECRET_KEY"):
                await upload(sample_file)

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_env):
        """Test that FileNotFoundError is raised for missing file."""
        with pytest.raises(FileNotFoundError):
            await upload(Path("/tmp/nonexistent_arvan_test.bin"))

    @pytest.mark.asyncio
    async def test_upload_success(self, sample_file):
        """Test successful upload via mocked boto3."""
        env = {
            "ARVAN_ACCESS_KEY": "test_key",
            "ARVAN_SECRET_KEY": "test_secret",
            "ARVAN_BUCKET": "test-bucket",
        }
        with patch.dict("os.environ", env, clear=False):
            mock_boto3 = MagicMock()
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3

            with patch.dict("sys.modules", {"boto3": mock_boto3}):
                url = await upload(sample_file)

        assert "test-bucket" in url
        assert sample_file.name in url
        mock_s3.upload_fileobj.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_uses_custom_endpoint(self, sample_file):
        """Test that custom ARVAN_ENDPOINT is respected."""
        env = {
            "ARVAN_ACCESS_KEY": "key",
            "ARVAN_SECRET_KEY": "secret",
            "ARVAN_BUCKET": "bucket",
            "ARVAN_ENDPOINT": "s3.custom.arvan.ir",
        }
        with patch.dict("os.environ", env, clear=False):
            mock_boto3 = MagicMock()
            with patch.dict("sys.modules", {"boto3": mock_boto3}):
                await upload(sample_file)

            call_kwargs = mock_boto3.client.call_args[1]
            assert call_kwargs["endpoint_url"] == "https://s3.custom.arvan.ir"


class TestArvanCleanup:
    """Tests for the ArvanCloud cleanup_old_files function."""

    @pytest.mark.asyncio
    async def test_cleanup_disabled_when_zero_days(self):
        """Test that cleanup returns 0 when valid_days is 0."""
        assert await cleanup_old_files(0) == 0
        assert await cleanup_old_files(-1) == 0

    @pytest.mark.asyncio
    async def test_cleanup_skips_when_not_configured(self):
        """Test that cleanup returns 0 when env vars are missing."""
        with patch.dict("os.environ", {}, clear=False):
            import os

            for k in ("ARVAN_ACCESS_KEY", "ARVAN_SECRET_KEY", "ARVAN_BUCKET"):
                os.environ.pop(k, None)
            assert await cleanup_old_files(7) == 0

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_objects(self):
        """Test that old objects are deleted."""
        env = {
            "ARVAN_ACCESS_KEY": "key",
            "ARVAN_SECRET_KEY": "secret",
            "ARVAN_BUCKET": "bucket",
        }
        with patch.dict("os.environ", env, clear=False):
            mock_boto3 = MagicMock()
            mock_s3 = MagicMock()

            # Simulate paginator with one old and one new object
            from datetime import datetime, timezone

            old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
            new_time = datetime.now(timezone.utc)

            mock_s3.get_paginator.return_value.paginate.return_value = [
                {
                    "Contents": [
                        {"Key": "hybrid-rar-bridge/old.rar", "LastModified": old_time},
                        {"Key": "hybrid-rar-bridge/new.rar", "LastModified": new_time},
                    ]
                }
            ]

            mock_boto3.client.return_value = mock_s3

            with patch.dict("sys.modules", {"boto3": mock_boto3}):
                deleted = await cleanup_old_files(7)

            assert deleted == 1
            mock_s3.delete_objects.assert_called_once()
