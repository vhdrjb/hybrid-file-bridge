"""
Hybrid RAR File Bridge - Telegram Bot

This bot accepts direct download URLs from authorized Telegram users,
downloads the file on a VPS with free internet, archives it into
password-protected RAR volumes, and uploads to free Iranian file-sharing
services with automatic provider fallback.

Usage:
    1. Send a direct download URL to the bot.
    2. The bot downloads, archives, and uploads the file.
    3. You receive the download link(s) and extraction password.

Environment variables (see .env.example):
    TELEGRAM_BOT_TOKEN, AUTHORIZED_USERS, PROVIDER_PRIORITY,
    BALE_BOT_TOKEN, BALE_CHAT_ID, EITAA_BOT_TOKEN, EITAA_CHAT_ID,
    PARSASPACE_TOKEN, PARSASPACE_DOMAIN,
    SINGLE_UPLOAD_MAX_MB, RAR_VOLUME_SIZE_MB
"""

import logging
import os
import re
import secrets
import string
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tools.downloader import download_file, extract_filename_from_url
from tools.rar_archiver import create_rar_archive, split_rar_volumes
from tools.upload_manager import upload_with_fallback

# ---------------------------------------------------------------------------
# Configuration & Logging
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Per-environment configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USERS: list[int] = [
    int(uid.strip())
    for uid in os.getenv("AUTHORIZED_USERS", "").split(",")
    if uid.strip().isdigit()
]
SINGLE_UPLOAD_MAX_MB = float(os.getenv("SINGLE_UPLOAD_MAX_MB", "450"))
RAR_VOLUME_SIZE_MB = float(os.getenv("RAR_VOLUME_SIZE_MB", "450"))
DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", "downloads"))
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# URL detection regex (simple but covers most direct download links)
URL_PATTERN = re.compile(
    r"https?://"  # http:// or https://
    r"(?:www\.)?"  # optional www
    r"[^\s<>\"]+"  # domain and path
    r"\.[a-zA-Z]{2,}"  # TLD
    r"[^\s<>\"]*",  # rest of URL
    re.IGNORECASE,
)

MB = 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_password(length: int = 16) -> str:
    """Generate a cryptographically secure random password.

    The password contains a mix of uppercase, lowercase, digits, and
    special characters to ensure compatibility with RAR encryption and
    reasonable strength for temporary file sharing.

    Args:
        length: Password length (default 16 characters).

    Returns:
        A randomly generated password string.
    """
    alphabet = string.ascii_letters + string.digits + "@#$%&*!?+="
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure the password has at least one character from each category
        if (
            any(c.isupper() for c in password)
            and any(c.islower() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "@#$%&*!?+=" for c in password)
        ):
            return password


def extract_url(text: str) -> str | None:
    """Extract the first URL from a message text.

    Uses a regex pattern to find the first HTTP/HTTPS URL in the
    user's message. Returns None if no URL is found.

    Args:
        text: The message text to search.

    Returns:
        The first URL found, or None.
    """
    match = URL_PATTERN.search(text.strip())
    return match.group(0) if match else None


def is_authorized(user_id: int) -> bool:
    """Check if a Telegram user ID is in the authorized list.

    Reads the AUTHORIZED_USERS environment variable at call time
    so that tests can override it via monkeypatch.

    Args:
        user_id: The Telegram user ID to check.

    Returns:
        True if the user is authorized, False otherwise.
    """
    authorized_str = os.getenv("AUTHORIZED_USERS", "")
    authorized_users = [
        int(uid.strip())
        for uid in authorized_str.split(",")
        if uid.strip().isdigit()
    ]
    if not authorized_users:
        return False
    return user_id in authorized_users


def format_extraction_guide(password: str, is_multi: bool = False) -> str:
    """Format extraction instructions for the user.

    Provides clear instructions on how to extract the RAR archive
    on different platforms and tools.

    Args:
        password: The extraction password.
        is_multi: Whether this is a multi-part archive.

    Returns:
        Formatted extraction guide string.
    """
    guide = (
        f"🔐 Extraction Password: `{password}`\n\n"
        f"📖 How to extract:\n"
        f"• Windows: Open with WinRAR → Enter password when prompted\n"
        f"• macOS: Open with Keka or The Unarchiver → Enter password\n"
        f"• Linux: `unrar x -p{password} your_file.rar`\n"
        f"• Android: Use RAR app → Enter password\n"
    )

    if is_multi:
        guide += (
            f"\n⚠️ Multi-part archive: Download ALL parts into the same folder, "
            f"then extract the .part1.rar file. "
            f"All parts must be in the same directory for extraction to work.\n"
        )

    return guide


# ---------------------------------------------------------------------------
# Telegram Handlers
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command.

    Sends a welcome message to authorized users explaining how to use
    the bot. Unauthorized users receive a rejection message.

    Args:
        update: The incoming Telegram update.
        context: The context provided by the handler.
    """
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text(
            "⛔ Sorry, you are not authorized to use this bot."
        )
        logger.warning("Unauthorized /start from user %d (%s)", user.id, user.username)
        return

    welcome = (
        f"👋 Hello, {user.first_name}!\n\n"
        f"📦 **Hybrid RAR File Bridge**\n\n"
        f"Send me a direct download URL and I will:\n"
        f"1. Download the file\n"
        f"2. Archive it into a password-protected RAR\n"
        f"3. Upload to free Iranian file-sharing services\n"
        f"4. Send you the download link(s) and password\n\n"
        f"Simply paste a URL to get started."
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")
    logger.info("User %d (%s) started the bot", user.id, user.username)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming URL messages — the main workflow handler.

    This is the core handler that orchestrates the entire file processing
    pipeline: download → archive → upload → reply.

    The handler:
      1. Validates user authorization and URL.
      2. Downloads the file using aria2c.
      3. Generates a random password.
      4. Creates a single RAR or multi-part volumes depending on file size.
      5. Uploads to providers with automatic fallback.
      6. Replies with download link(s), password, and extraction guide.
      7. Cleans up temporary files.

    Args:
        update: The incoming Telegram update.
        context: The context provided by the handler.
    """
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text(
            "⛔ Sorry, you are not authorized to use this bot."
        )
        return

    text = update.message.text or ""
    url = extract_url(text)

    if not url:
        await update.message.reply_text(
            "❌ No valid URL detected. Please send a direct download link."
        )
        return

    # Notify user that processing has started
    status_msg = await update.message.reply_text(
        "⏳ Downloading file, please wait..."
    )
    logger.info(
        "User %d (%s) requested download: %s", user.id, user.username, url
    )

    # Create a temporary working directory for this job
    with tempfile.TemporaryDirectory(prefix="hrb_") as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # ---- Step 1: Download ----
            await status_msg.edit_text("⏳ Downloading file...")

            filename = extract_filename_from_url(url)
            downloaded_file = await download_file(
                url=url,
                dest_dir=DOWNLOADS_DIR,
                filename=filename,
            )

            file_size_mb = downloaded_file.stat().st_size / MB
            password = generate_password()

            logger.info(
                "Downloaded: %s (%.2f MB), password: %s***",
                downloaded_file.name, file_size_mb, password[:4],
            )

            # ---- Step 2: Archive & Upload ----
            if file_size_mb <= SINGLE_UPLOAD_MAX_MB:
                # Single file upload path
                await status_msg.edit_text(
                    f"📦 Creating archive ({file_size_mb:.1f} MB)..."
                )

                output_rar = temp_path / f"{downloaded_file.stem}.rar"
                await create_rar_archive(
                    input_path=downloaded_file,
                    output_rar=output_rar,
                    password=password,
                )

                await status_msg.edit_text("📤 Uploading to provider...")
                result = await upload_with_fallback(output_rar)

                reply = (
                    f"✅ **File Ready!**\n\n"
                    f"📄 File: `{downloaded_file.name}`\n"
                    f"📊 Size: {file_size_mb:.1f} MB\n"
                    f"🌐 Provider: {result.provider}\n"
                    f"🔗 Download: {result.url}\n\n"
                    f"{format_extraction_guide(password)}"
                )

                # Clean up original download
                try:
                    downloaded_file.unlink()
                except OSError:
                    pass

            else:
                # Multi-part upload path
                num_parts = int(file_size_mb / RAR_VOLUME_SIZE_MB) + 1
                await status_msg.edit_text(
                    f"📦 Creating {num_parts}-part archive "
                    f"({file_size_mb:.1f} MB, {RAR_VOLUME_SIZE_MB:.0f} MB/part)..."
                )

                parts_dir = temp_path / "parts"
                parts_dir.mkdir()

                part_files = await split_rar_volumes(
                    input_path=downloaded_file,
                    output_dir=parts_dir,
                    volume_mb=RAR_VOLUME_SIZE_MB,
                    password=password,
                )

                links = []
                for i, part_file in enumerate(part_files, 1):
                    await status_msg.edit_text(
                        f"📤 Uploading part {i}/{len(part_files)}..."
                    )
                    result = await upload_with_fallback(part_file)
                    links.append((result.url, result.provider, part_file.name))
                    logger.info(
                        "Part %d/%d uploaded via %s", i, len(part_files), result.provider
                    )

                    # Clean up each part after upload
                    try:
                        part_file.unlink()
                    except OSError:
                        pass

                # Clean up original download
                try:
                    downloaded_file.unlink()
                except OSError:
                    pass

                # Build multi-part reply
                links_text = "\n".join(
                    f"  {i+1}. [{p[2]}]({p[0]}) via {p[1]}"
                    for i, p in enumerate(links)
                )

                reply = (
                    f"✅ **File Ready (Multi-Part Archive)!**\n\n"
                    f"📄 File: `{downloaded_file.name}`\n"
                    f"📊 Size: {file_size_mb:.1f} MB\n"
                    f"📦 Parts: {len(links)} × {RAR_VOLUME_SIZE_MB:.0f} MB\n\n"
                    f"🔗 **Download Links:**\n{links_text}\n\n"
                    f"{format_extraction_guide(password, is_multi=True)}"
                )

            await status_msg.edit_text(reply, parse_mode="Markdown")
            logger.info(
                "Successfully processed %s (%.2f MB) for user %d",
                downloaded_file.name, file_size_mb, user.id,
            )

        except FileNotFoundError as e:
            error_reply = f"❌ File not found: {e}"
            await status_msg.edit_text(error_reply)
            logger.error("FileNotFound for user %d: %s", user.id, e)

        except RuntimeError as e:
            error_reply = f"❌ Error: {e}"
            await status_msg.edit_text(error_reply)
            logger.error("RuntimeError for user %d: %s", user.id, e)

        except asyncio.TimeoutError as e:
            error_reply = f"❌ Download timed out. The server may be slow or the link may be invalid."
            await status_msg.edit_text(error_reply)
            logger.error("TimeoutError for user %d: %s", user.id, e)

        except Exception as e:
            error_reply = f"❌ An unexpected error occurred. Please try again later."
            await status_msg.edit_text(error_reply)
            logger.exception(
                "Unexpected error for user %d processing %s: %s",
                user.id, url, e,
            )


# Need asyncio for TimeoutError handling
import asyncio


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the Telegram bot.

    Initializes the bot application, registers command and message
    handlers, and begins long-polling for updates. Exits if the
    TELEGRAM_BOT_TOKEN is not configured.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Please configure it in .env")
        raise SystemExit(1)

    if not AUTHORIZED_USERS:
        logger.warning(
            "No AUTHORIZED_USERS configured. "
            "No one will be able to use the bot!"
        )

    logger.info("Starting Hybrid RAR File Bridge...")
    logger.info("Authorized users: %s", AUTHORIZED_USERS)
    logger.info("Single upload max: %d MB", int(SINGLE_UPLOAD_MAX_MB))
    logger.info("RAR volume size: %d MB", int(RAR_VOLUME_SIZE_MB))

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )

    logger.info("Bot is running. Press Ctrl+C to stop.")

    # Start polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
