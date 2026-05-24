"""
Unit tests for the RAR archiver module.

Tests cover single archive creation, multi-part volume splitting,
password encryption, and error handling. Tests use the real `rar`
command if available, otherwise skip gracefully.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tools.rar_archiver import create_rar_archive, split_rar_volumes

# Check if rar is available on the system
RAR_AVAILABLE = False
try:
    import subprocess

    result = subprocess.run(["rar", "--version"], capture_output=True, text=True)
    RAR_AVAILABLE = result.returncode == 0
except FileNotFoundError:
    pass


@pytest.mark.skipif(not RAR_AVAILABLE, reason="rar command not available")
class TestCreateRarArchive:
    """Tests for the create_rar_archive function."""

    @pytest.mark.asyncio
    async def test_create_single_archive(self, temp_dir, sample_file):
        """Test creating a single password-protected RAR archive."""
        output_rar = temp_dir / "archive.rar"

        result = await create_rar_archive(
            input_path=sample_file,
            output_rar=output_rar,
            password="TestPass123!",
        )

        assert result.exists()
        assert result.stat().st_size > 0
        assert result.suffix == ".rar"

    @pytest.mark.asyncio
    async def test_archive_missing_input(self, temp_dir):
        """Test that missing input file raises FileNotFoundError."""
        output_rar = temp_dir / "archive.rar"
        missing_file = temp_dir / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            await create_rar_archive(
                input_path=missing_file,
                output_rar=output_rar,
                password="TestPass123!",
            )

    @pytest.mark.asyncio
    async def test_archive_creates_parent_dir(self, temp_dir, sample_file):
        """Test that output parent directory is created if missing."""
        output_rar = temp_dir / "subdir" / "nested" / "archive.rar"

        result = await create_rar_archive(
            input_path=sample_file,
            output_rar=output_rar,
            password="TestPass123!",
        )

        assert result.exists()
        assert result.parent.exists()

    @pytest.mark.asyncio
    async def test_archive_with_directory(self, temp_dir):
        """Test archiving a directory."""
        src_dir = temp_dir / "source"
        src_dir.mkdir()
        (src_dir / "file1.txt").write_text("content1")
        (src_dir / "file2.txt").write_text("content2")

        output_rar = temp_dir / "dir_archive.rar"

        result = await create_rar_archive(
            input_path=src_dir,
            output_rar=output_rar,
            password="DirPass456!",
        )

        assert result.exists()
        assert result.stat().st_size > 0


@pytest.mark.skipif(not RAR_AVAILABLE, reason="rar command not available")
class TestSplitRarVolumes:
    """Tests for the split_rar_volumes function."""

    @pytest.mark.asyncio
    async def test_split_into_volumes(self, temp_dir, large_sample_file):
        """Test splitting a file into multiple RAR volumes."""
        parts_dir = temp_dir / "parts"

        result = await split_rar_volumes(
            input_path=large_sample_file,
            output_dir=parts_dir,
            volume_mb=0.1,  # 100KB volumes to force splitting
            password="SplitPass789!",
        )

        assert len(result) >= 1
        for part in result:
            assert part.exists()
            assert part.stat().st_size > 0
            assert ".rar" in part.name

    @pytest.mark.asyncio
    async def test_split_missing_input(self, temp_dir):
        """Test that missing input file raises FileNotFoundError."""
        missing_file = temp_dir / "nonexistent.bin"
        parts_dir = temp_dir / "parts"

        with pytest.raises(FileNotFoundError):
            await split_rar_volumes(
                input_path=missing_file,
                output_dir=parts_dir,
                volume_mb=1.0,
                password="TestPass123!",
            )

    @pytest.mark.asyncio
    async def test_split_custom_output_name(self, temp_dir, sample_file):
        """Test splitting with a custom base output name."""
        parts_dir = temp_dir / "custom_parts"

        result = await split_rar_volumes(
            input_path=sample_file,
            output_dir=parts_dir,
            volume_mb=0.001,  # Very small to force at least one part
            password="CustomPass!",
            output_name="my_custom_archive",
        )

        assert len(result) >= 1
        # All parts should contain the custom name
        for part in result:
            assert "my_custom_archive" in part.name


class TestRarArchiverMocked:
    """Tests using mocked rar subprocess (works without rar installed)."""

    @pytest.mark.asyncio
    async def test_create_archive_mocked_success(self, temp_dir, sample_file):
        """Test successful archive creation with mocked subprocess."""
        # Simulate rar creating the output file
        output_rar = temp_dir / "mocked.rar"
        output_rar.write_bytes(b"fake rar content")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await create_rar_archive(
                input_path=sample_file,
                output_rar=output_rar,
                password="MockPass!",
            )

        assert result == output_rar
        assert result.exists()

    @pytest.mark.asyncio
    async def test_create_archive_mocked_failure(self, temp_dir, sample_file):
        """Test archive creation failure with mocked subprocess."""
        output_rar = temp_dir / "failed.rar"

        mock_process = AsyncMock()
        mock_process.returncode = 10
        mock_process.communicate = AsyncMock(return_value=(b"", b"Cannot create archive"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError, match="RAR archive creation failed"):
                await create_rar_archive(
                    input_path=sample_file,
                    output_rar=output_rar,
                    password="MockPass!",
                )

    @pytest.mark.asyncio
    async def test_split_volumes_mocked_success(self, temp_dir, sample_file):
        """Test volume splitting with mocked subprocess."""
        parts_dir = temp_dir / "mock_parts"
        parts_dir.mkdir()

        # Create fake part files
        (parts_dir / "sample.part1.rar").write_bytes(b"part1")
        (parts_dir / "sample.part2.rar").write_bytes(b"part2")
        (parts_dir / "sample.part3.rar").write_bytes(b"part3")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await split_rar_volumes(
                input_path=sample_file,
                output_dir=parts_dir,
                volume_mb=0.001,
                password="MockPass!",
            )

        assert len(result) == 3
        assert all(p.exists() for p in result)
