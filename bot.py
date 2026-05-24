"""
Hybrid RAR File Bridge - Telegram Bot

This bot accepts direct download URLs and YouTube links from authorized
Telegram users, downloads the file on a VPS with free internet, archives
it into password-protected RAR volumes, and uploads to free Iranian
file-sharing services with automatic provider fallback.

Usage:
    - Send a direct download URL to get it archived and uploaded.
    - Send a YouTube link to choose quality, then download and upload.

Environment variables (see .env.example):
    TELEGRAM_BOT_TOKEN, AUTHORIZED_USERS, PROVIDER_PRIORITY,
    BALE_BOT_TOKEN, BALE_CHAT_ID, EITAA_BOT_TOKEN, EITAA_CHAT_ID,
    PARSASPACE_TOKEN, PARSASPACE_DOMAIN,
    SINGLE_UPLOAD_MAX_MB, RAR_VOLUME_SIZE_MB
"""

import asyncio
import logging
import os
import re
import secrets
import string
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tools.downloader import download_file, extract_filename_from_url
from tools.rar_archiver import create_rar_archive, split_rar_volumes
from tools.upload_manager import upload_with_fallback
from tools.youtube_downloader import (
    VideoFormat,
    download_video,
    format_quality_button_label,
    get_video_info,
    is_youtube_url,
    parse_formats,
)

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
    r"https?://"
    r"(?:www\.)?"
    r"[^\s<>\"]+"
    r"\.[a-zA-Z]{2,}"
    r"[^\s<>\"]*",
    re.IGNORECASE,
)

# Maximum formats to show on the inline keyboard (Telegram limit: 100 buttons)
MAX_FORMAT_BUTTONS = 20

MB = 1024 * 1024

# Callback data prefix for YouTube quality selection
CALLBACK_PREFIX = "yt_quality:"


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
        if (
            any(c.isupper() for c in password)
            and any(c.islower() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "@#$%&*!?+=" for c in password)
        ):
            return password


def extract_url(text: str) -> str | None:
    """Extract the first URL from a message text.

    Args:
        text: The message text to search.

    Returns:
        The first URL found, or None.
    """
    match = URL_PATTERN.search(text.strip())
    return match.group(0) if match else None


def is_authorized(user_id: int) -> bool:
    """Check if a Telegram user ID is in the authorized list.

    Reads AUTHORIZED_USERS at call time so tests can override via monkeypatch.

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
# Archive & Upload Pipeline (shared between link and YouTube handlers)
# ---------------------------------------------------------------------------


async def process_downloaded_file(
    downloaded_file: Path,
    status_msg,
    password: str,
    temp_path: Path,
) -> None:
    """Run the archive → upload → reply pipeline on a downloaded file.

    This is the shared pipeline used by both the direct download handler
    and the YouTube download handler. It creates a RAR archive (single or
    multi-part), uploads it to a provider with fallback, and sends the
    user the download link(s) and password.

    Args:
        downloaded_file: Path to the file that was downloaded.
        status_msg: The Telegram message to edit with status updates.
        password: The RAR encryption password.
        temp_path: Temporary working directory for this job.
    """
    file_size_mb = downloaded_file.stat().st_size / MB

    logger.info(
        "Processing: %s (%.2f MB)", downloaded_file.name, file_size_mb
    )

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
                "Part %d/%d uploaded via %s",
                i, len(part_files), result.provider,
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
        "Successfully processed %s (%.2f MB)",
        downloaded_file.name, file_size_mb,
    )


# ---------------------------------------------------------------------------
# Telegram Handlers
# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command.

    Sends a welcome message to authorized users explaining how to use
    the bot. Unauthorized users receive a rejection message.
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
        f"Send me one of the following:\n"
        f"1. 🔗 **Direct download URL** — I'll download, archive into RAR, "
        f"and upload for you.\n"
        f"2. 🎬 **YouTube link** — I'll show available qualities, "
        f"you pick one, then I download, archive, and upload.\n\n"
        f"Simply paste a link to get started!"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")
    logger.info("User %d (%s) started the bot", user.id, user.username)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming URL messages — routes to YouTube or direct download.

    Detects whether the URL is a YouTube link. If so, delegates to the
    YouTube quality selection flow. Otherwise, runs the standard
    download → archive → upload pipeline.
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
            "❌ No valid URL detected. Please send a direct download link "
            "or a YouTube link."
        )
        return

    # Route YouTube URLs to the quality-selection handler
    if is_youtube_url(url):
        await _handle_youtube_url(update, context, url)
        return

    # Standard direct download flow
    status_msg = await update.message.reply_text(
        "⏳ Downloading file, please wait..."
    )
    logger.info(
        "User %d (%s) requested download: %s", user.id, user.username, url
    )

    with tempfile.TemporaryDirectory(prefix="hrb_") as temp_dir:
        temp_path = Path(temp_dir)

        try:
            await status_msg.edit_text("⏳ Downloading file...")

            filename = extract_filename_from_url(url)
            downloaded_file = await download_file(
                url=url,
                dest_dir=DOWNLOADS_DIR,
                filename=filename,
            )

            password = generate_password()

            await process_downloaded_file(
                downloaded_file, status_msg, password, temp_path
            )

        except FileNotFoundError as e:
            await status_msg.edit_text(f"❌ File not found: {e}")
            logger.error("FileNotFound for user %d: %s", user.id, e)

        except RuntimeError as e:
            await status_msg.edit_text(f"❌ Error: {e}")
            logger.error("RuntimeError for user %d: %s", user.id, e)

        except asyncio.TimeoutError:
            await status_msg.edit_text(
                "❌ Download timed out. The server may be slow "
                "or the link may be invalid."
            )
            logger.error("TimeoutError for user %d", user.id)

        except Exception as e:
            await status_msg.edit_text(
                "❌ An unexpected error occurred. Please try again later."
            )
            logger.exception(
                "Unexpected error for user %d processing %s: %s",
                user.id, url, e,
            )


# ---------------------------------------------------------------------------
# YouTube-Specific Handlers
# ---------------------------------------------------------------------------


async def _handle_youtube_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
) -> None:
    """Handle a YouTube URL — fetch formats and show quality picker.

    Fetches the available video formats from yt-dlp, builds an inline
    keyboard with quality options, and sends it to the user. The user's
    choice is handled by the callback query handler.

    Args:
        update: The incoming Telegram update.
        context: The context for storing pending job data.
        url: The YouTube URL to process.
    """
    user = update.effective_user
    status_msg = await update.message.reply_text(
        "🎬 Detecting YouTube video..."
    )
    logger.info(
        "User %d (%s) sent YouTube link: %s",
        user.id, user.username, url,
    )

    try:
        await status_msg.edit_text(
            "🎬 Fetching available qualities..."
        )

        info = await get_video_info(url)
        formats = parse_formats(info)

        if not formats:
            await status_msg.edit_text(
                "❌ No downloadable formats found for this video. "
                "It may be private, age-restricted, or region-locked."
            )
            return

        # Trim to max buttons (pick best video + audio formats)
        if len(formats) > MAX_FORMAT_BUTTONS:
            formats = formats[:MAX_FORMAT_BUTTONS]

        # Build inline keyboard
        buttons = []
        for i, fmt in enumerate(formats):
            label = format_quality_button_label(fmt, i + 1)
            callback_data = f"{CALLBACK_PREFIX}{fmt.format_id}"
            buttons.append([InlineKeyboardButton(label, callback_data=callback_data)])

        keyboard = InlineKeyboardMarkup(buttons)

        video_title = info.get("title", "Unknown Title")
        duration = info.get("duration", 0)
        duration_str = ""
        if duration:
            hours, remainder = divmod(int(duration), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                duration_str = f" ({hours}h {minutes}m)"
            else:
                duration_str = f" ({minutes}m {seconds}s)"

        # Truncate long titles
        display_title = video_title[:100] + "..." if len(video_title) > 100 else video_title

        message_text = (
            f"🎬 **{display_title}**{duration_str}\n\n"
            f"Select a quality to download:\n"
            f"_The file will be archived into a password-protected RAR "
            f"and uploaded to a file-sharing service._"
        )

        await status_msg.edit_text(
            message_text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

        # Store job context for the callback handler
        context.user_data["yt_url"] = url
        context.user_data["yt_title"] = video_title
        context.user_data["yt_formats"] = formats

        logger.info(
            "Sent %d format options to user %d for: %s",
            len(formats), user.id, display_title,
        )

    except RuntimeError as e:
        await status_msg.edit_text(f"❌ YouTube error: {e}")
        logger.error("YouTube info error for user %d: %s", user.id, e)

    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "❌ Timed out while fetching video info. "
            "The video may not exist or YouTube may be blocked."
        )
        logger.error("YouTube info timeout for user %d", user.id)

    except Exception as e:
        await status_msg.edit_text(
            "❌ An unexpected error occurred while fetching video info."
        )
        logger.exception(
            "Unexpected error for user %d fetching YouTube info: %s",
            user.id, e,
        )


async def handle_youtube_quality_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle the user's quality selection from the inline keyboard.

    This callback query handler is triggered when the user taps a quality
    button. It downloads the video in the selected format, then runs the
    standard RAR archive → upload pipeline.

    Args:
        update: The callback query update.
        context: The context containing stored YouTube job data.
    """
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not is_authorized(user.id):
        await query.edit_message_text(
            "⛔ Sorry, you are not authorized to use this bot."
        )
        return

    callback_data = query.data or ""

    if not callback_data.startswith(CALLBACK_PREFIX):
        return

    format_id = callback_data[len(CALLBACK_PREFIX):]

    # Retrieve stored job data
    url = context.user_data.get("yt_url")
    video_title = context.user_data.get("yt_title", "Unknown")
    formats: list[VideoFormat] | None = context.user_data.get("yt_formats")

    if not url:
        await query.edit_message_text(
            "❌ Session expired. Please send the YouTube link again."
        )
        return

    # Find the selected format for display
    selected_format = None
    if formats:
        for fmt in formats:
            if fmt.format_id == format_id:
                selected_format = fmt
                break

    quality_desc = ""
    if selected_format:
        size_str = (
            f"{selected_format.filesize_mb:.0f} MB"
            if selected_format.filesize_mb else "unknown size"
        )
        quality_desc = f" ({selected_format.resolution} {selected_format.extension}, {size_str})"

    display_title = video_title[:80] + "..." if len(video_title) > 80 else video_title

    logger.info(
        "User %d selected format %s for: %s",
        user.id, format_id, video_title,
    )

    # Update the message to show processing state
    await query.edit_message_text(
        f"⏳ Downloading YouTube video{quality_desc}...\n\n"
        f"📄 {display_title}\n\n"
        f"_This may take a while depending on video size. "
        f"Please be patient._",
        parse_mode="Markdown",
    )

    # Create a temporary working directory for this job
    with tempfile.TemporaryDirectory(prefix="hrb_yt_") as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # ---- Step 1: Download YouTube video ----
            # Use a dedicated download subdirectory so we can find the file
            yt_download_dir = temp_path / "yt_download"
            yt_download_dir.mkdir()

            downloaded_file = await download_video(
                url=url,
                format_id=format_id,
                output_dir=yt_download_dir,
            )

            password = generate_password()

            # ---- Step 2: Archive & Upload (shared pipeline) ----
            # Reuse the same message (query.message) for status updates
            # by creating a wrapper that mimics edit_text
            class StatusMessageWrapper:
                """Wraps a callback query message for edit_text compatibility."""
                def __init__(self, msg):
                    self._msg = msg

                async def edit_text(self, text, **kwargs):
                    return await self._msg.edit_text(text, **kwargs)

            status_wrapper = StatusMessageWrapper(query.message)

            await process_downloaded_file(
                downloaded_file, status_wrapper, password, temp_path
            )

            # Clean up stored job data
            context.user_data.pop("yt_url", None)
            context.user_data.pop("yt_title", None)
            context.user_data.pop("yt_formats", None)

        except FileNotFoundError as e:
            await query.edit_message_text(f"❌ File not found: {e}")
            logger.error("FileNotFound for user %d: %s", user.id, e)

        except RuntimeError as e:
            await query.edit_message_text(f"❌ Error: {e}")
            logger.error("RuntimeError for user %d: %s", user.id, e)

        except asyncio.TimeoutError:
            await query.edit_message_text(
                "❌ YouTube download timed out. The video may be too large "
                "or your VPS connection may be slow."
            )
            logger.error("YouTube download timeout for user %d", user.id)

        except Exception as e:
            await query.edit_message_text(
                "❌ An unexpected error occurred. Please try again later."
            )
            logger.exception(
                "Unexpected error for user %d YouTube download: %s",
                user.id, e,
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the Telegram bot.

    Initializes the bot application, registers command, message, and
    callback query handlers, and begins long-polling for updates.
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
    application.add_handler(
        CallbackQueryHandler(handle_youtube_quality_callback)
    )

    logger.info("Bot is running. Press Ctrl+C to stop.")

    # Start polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
