"""
RAR archiver module for creating and splitting password-protected archives.

This module wraps the `rar` command-line utility to create encrypted RAR
archives. It supports both single-file archives and multi-part (volume)
archives for splitting large files across upload size limits.

All archive operations run as async subprocesses to avoid blocking
the event loop during compression of large files.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def create_rar_archive(
    input_path: Path,
    output_rar: Path,
    password: str,
) -> Path:
    """Create a single password-protected RAR archive.

    Compresses the input file or directory into a single RAR archive
    encrypted with the given password. The `-ep` flag ensures that
    paths inside the archive are relative (no parent directories included).

    Args:
        input_path: Path to the file or directory to archive.
        output_rar: Desired output path for the .rar file.
        password: Encryption password for the archive.

    Returns:
        Path to the created RAR archive.

    Raises:
        FileNotFoundError: If the input_path does not exist.
        RuntimeError: If the rar command fails.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    output_rar = Path(output_rar)
    output_rar.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "rar",
        "a",  # Add files to archive
        f"-p{password}",  # Set password
        "-ep",  # Exclude paths from file names
        "-m3",  # Normal compression (balance of speed and ratio)
        str(output_rar),
        str(input_path),
    ]

    logger.info(
        "Creating RAR archive: %s -> %s (%s)", input_path.name, output_rar.name, len(password) * "*"
    )
    logger.debug("RAR command: %s", " ".join(cmd[:5]) + " ...")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(
            f"RAR archive creation failed (code {process.returncode}): {error_msg}"
        )

    if not output_rar.exists():
        raise FileNotFoundError(
            f"RAR command succeeded but output file not found: {output_rar}"
        )

    archive_size_mb = output_rar.stat().st_size / (1024 * 1024)
    logger.info(
        "Archive created: %s (%.2f MB)", output_rar.name, archive_size_mb
    )

    return output_rar


async def split_rar_volumes(
    input_path: Path,
    output_dir: Path,
    volume_mb: float,
    password: str,
    output_name: str | None = None,
) -> list[Path]:
    """Create a multi-part password-protected RAR archive.

    Splits the input file into multiple RAR volumes, each approximately
    `volume_mb` megabytes in size. This is essential for uploading large
    files to providers with size restrictions.

    The resulting parts follow the naming convention:
    `filename.part1.rar`, `filename.part2.rar`, etc.

    Args:
        input_path: Path to the file or directory to archive.
        output_dir: Directory where volume parts will be saved.
        volume_mb: Maximum size of each volume part in megabytes.
        password: Encryption password for the archive.
        output_name: Base name for the archive (without extension).
                   If None, uses the input filename.

    Returns:
        Sorted list of Path objects for each volume part.

    Raises:
        FileNotFoundError: If input_path does not exist.
        RuntimeError: If rar command fails or no parts are created.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_name is None:
        base_name = input_path.stem
    else:
        base_name = Path(output_name).stem

    output_base = output_dir / base_name
    volume_str = f"{int(volume_mb)}m"

    cmd = [
        "rar",
        "a",  # Add files to archive
        f"-v{volume_str}",  # Create volumes of specified size
        f"-p{password}",  # Set password
        "-ep",  # Exclude paths from file names
        "-m3",  # Normal compression
        str(output_base) + ".rar",
        str(input_path),
    ]

    logger.info(
        "Creating split RAR archive: %s -> %s/*.part*.rar (volumes of %s MB)",
        input_path.name, output_dir, volume_str,
    )
    logger.debug("RAR command: %s", " ".join(cmd[:5]) + " ...")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(
            f"RAR volume creation failed (code {process.returncode}): {error_msg}"
        )

    # Find all generated volume parts
    parts = sorted(output_dir.glob(f"{base_name}.part*.rar"))

    if not parts:
        # Also try the pattern without 'part' in case rar uses a different naming
        parts = sorted(output_dir.glob(f"{base_name}*.rar"))
        if not parts:
            raise RuntimeError(
                f"RAR volume command succeeded but no parts found in {output_dir}"
            )

    total_size_mb = sum(p.stat().st_size for p in parts) / (1024 * 1024)
    logger.info(
        "Created %d volume parts: %s (total %.2f MB)",
        len(parts), [p.name for p in parts], total_size_mb,
    )

    return parts
