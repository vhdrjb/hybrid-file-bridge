# Telegram Bot Setup Guide

This guide walks you through obtaining all required data and credentials to set up the Telegram bot for the Hybrid RAR File Bridge. You will need to create a Telegram Bot, obtain its API token, find your User ID for authorization, and optionally set up a channel for file distribution.

---

## Table of Contents

1. [Create a Telegram Bot via BotFather](#1-create-a-telegram-bot-via-botfather)
2. [Get Your Telegram User ID](#2-get-your-telegram-user-id)
3. [Configure the Bot Token](#3-configure-the-bot-token)
4. [Set Authorized Users](#4-set-authorized-users)
5. [Optional — Create a Channel for File Distribution](#5-optional--create-a-channel-for-file-distribution)
6. [Test Your Bot](#6-test-your-bot)
7. [Security Best Practices](#7-security-best-practices)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Create a Telegram Bot via BotFather

BotFather is the official Telegram bot for creating and managing bots. Every Telegram bot must be registered through BotFather before it can function.

### Step-by-Step Instructions

1. **Open Telegram** and search for `@BotFather` in the search bar. The official BotFather has a blue verified checkmark next to its name.

2. **Start a conversation** by clicking the **Start** button or sending `/start`. BotFather will respond with a list of available commands.

3. **Create a new bot** by sending the following command:
   ```
   /newbot
   ```

4. **Choose a display name** for your bot. This is the human-readable name that users will see (e.g., `Hybrid File Bridge`). Send it as a message:
   ```
   Hybrid File Bridge
   ```

5. **Choose a username** for your bot. The username must be unique across all Telegram bots and must end with `bot` (e.g., `hybrid_file_bridge_bot`). Send it:
   ```
   hybrid_file_bridge_bot
   ```
   If the username is already taken, BotFather will ask you to try a different one.

6. **Save your API token.** BotFather will respond with a message containing your bot's HTTP API token. It looks like this:
   ```
   1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   **This token is required for your bot to work.** Store it securely — anyone with this token can control your bot.

7. **Optional configuration commands.** You can customize your bot further using these BotFather commands:
   - `/setdescription` — Set a description shown when users start the bot
   - `/setabouttext` — Set the "About" section text
   - `/setuserpic` — Set a profile picture for the bot
   - `/setcommands` — Register bot commands (e.g., `start`, `help`) so they appear as suggestions in the chat

### Important Notes About the Bot Token

- The token is a long string in the format `NUMBER:STRING` (e.g., `7123456789:AAF-AbcDefGhIjKlMnOpQrStUvWxYz`).
- **Never share your token publicly** or commit it to a Git repository. Always use environment variables or a `.env` file (which should be in `.gitignore`).
- If your token is compromised, use `/revoke` in BotFather to generate a new one immediately. The old token will stop working.
- There is no expiration date on bot tokens — they remain valid until you explicitly revoke them.

---

## 2. Get Your Telegram User ID

The bot uses a whitelist of authorized Telegram User IDs. Only users whose IDs are listed in the `AUTHORIZED_USERS` environment variable can use the bot. This prevents unauthorized access.

### Method 1: Using the @userinfobot

1. Open Telegram and search for `@userinfobot`.
2. Start the bot by clicking **Start** or sending any message.
3. The bot will reply with your User ID, first name, last name, and username.
4. **Copy the numeric User ID** (e.g., `123456789`). This is the number you need.

### Method 2: Using the @getmyid_bot

1. Open Telegram and search for `@getmyid_bot`.
2. Send the command `/start`.
3. The bot will respond with your User ID and other profile information.
4. **Copy the numeric User ID.**

### Method 3: Using Telegram Web (Manual Method)

1. Open [Telegram Web](https://web.telegram.org) and log in.
2. Navigate to any message you have sent.
3. Inspect the page source or use browser developer tools to find your `from_id` in the API response.
4. This method is more technical and is only recommended if the bot methods above are unavailable.

### Method 4: Using the Raw Data Bot API

1. After creating your bot and having its token, open this URL in your browser (replace `<BOT_TOKEN>` with your actual token):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
2. Send a message to your bot first, then refresh the page.
3. Look for `"from":{"id":123456789}` in the JSON response.
4. The number after `"id"` is your User ID.

### Adding Multiple Users

You can authorize multiple users by separating their IDs with commas in the `AUTHORIZED_USERS` environment variable:
```
AUTHORIZED_USERS=123456789,987654321,555666777
```

---

## 3. Configure the Bot Token

After obtaining your bot token, you need to configure it in your project's environment.

### Option A: Using a `.env` File (Recommended for Development)

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Open the `.env` file in a text editor and replace the placeholder:
   ```env
   TELEGRAM_BOT_TOKEN=1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

3. Make sure `.env` is listed in your `.gitignore` file. It should already be there by default in this project. **Never commit `.env` to version control.**

### Option B: Using Docker Environment Variables

If you are running the bot with Docker Compose, you can set the token directly in `docker-compose.yml` or pass it at runtime:

```bash
docker run -e TELEGRAM_BOT_TOKEN=1234567890:AAHxxx... hybrid-rar-bridge
```

Or in `docker-compose.yml`:
```yaml
services:
  bridge:
    environment:
      - TELEGRAM_BOT_TOKEN=1234567890:AAHxxx...
```

### Option C: Using System Environment Variables (Production VPS)

On your VPS, set the environment variable before running the bot:
```bash
export TELEGRAM_BOT_TOKEN="1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
python bot.py
```

For persistence across reboots, add the export line to your `~/.bashrc`, `~/.zshrc`, or `/etc/environment` file, or use a process manager like `systemd`.

---

## 4. Set Authorized Users

The `AUTHORIZED_USERS` variable is a comma-separated list of Telegram User IDs that are allowed to interact with the bot. Any user not in this list will receive a rejection message.

### Configuration

In your `.env` file:
```env
AUTHORIZED_USERS=123456789,987654321
```

### How It Works

When a user sends a message to the bot (a URL or `/start`), the bot reads the user's Telegram ID from the incoming `Update` object and checks it against the `AUTHORIZED_USERS` list. If the ID is not found, the bot replies with:

```
⛔ Sorry, you are not authorized to use this bot.
```

### Dynamic Updates

The authorized users list is read from the environment variable at each request, so you can update it without restarting the bot (depending on your `load_dotenv` configuration). For production Docker deployments, you will need to recreate the container after changing the environment variable.

---

## 5. Optional — Create a Channel for File Distribution

If you are using Bale or Eitaa as upload providers, you need a channel where the bot will send uploaded files for users to download from.

### Creating a Telegram-Style Channel (for Bale)

1. Open **Bale Messenger** (or use the Bale web version at [ble.ir](https://ble.ir)).
2. Tap the **menu** icon (three horizontal lines) and select **New Channel**.
3. Enter a channel name (e.g., `Hybrid File Bridge Downloads`).
4. Choose whether the channel is **public** or **private**.
   - **Public channel**: Gets a username like `@hybrid_files`. Users can find it via search.
   - **Private channel**: Gets an invite link. Only users with the link can access it.
5. After creation, note the **channel username** (e.g., `@hybrid_files`) or **channel ID** (a numeric ID like `-1001234567890`).

### Creating a Channel for Eitaa

1. Open **Eitaa Messenger** (or use the web version at [web.eitaa.com](https://web.eitaa.com)).
2. Navigate to the menu and select **New Channel**.
3. Enter a name and description for the channel.
4. Choose public or private visibility.
5. After creation, note the channel's **numeric ID**.

### Adding the Bot as an Admin to the Channel

**This is a critical step.** The bot must be added as an administrator to the channel with permission to post messages (send documents).

1. Open the channel in the respective messenger.
2. Tap the **channel name** at the top to open channel settings.
3. Select **Administrators**.
4. Tap **Add Admin** and search for your bot by its username.
5. Grant the bot at minimum the **Post Messages** (send documents) permission.

Without this step, the bot will fail to upload files to the channel and you will see API errors in the logs.

---

## 6. Test Your Bot

After completing all configuration steps, verify that everything works correctly.

### Step 1: Start the Bot

```bash
# Using Docker Compose
docker compose up --build

# Or directly with Python
python bot.py
```

### Step 2: Send /start

Open Telegram, find your bot by its username, and send `/start`. You should receive a welcome message like:

```
👋 Hello, [Your Name]!

📦 **Hybrid RAR File Bridge**

Send me one of the following:
1. 🔗 **Direct download URL** — I'll download, archive into RAR, and upload for you.
2. 🎬 **YouTube link** — I'll show available qualities, you pick one, then I download, archive, and upload.

Simply paste a link to get started!
```

### Step 3: Test with a Small File

Send a small direct download URL (e.g., a small PDF or image) to the bot. The bot should:

1. Reply with `⏳ Downloading file...`
2. Update to `📦 Creating archive...`
3. Update to `📤 Uploading to provider...`
4. Send a final message with `✅ **File Ready!**` containing a download link and password.

### Step 4: Test YouTube Support

Send a YouTube link (e.g., `https://www.youtube.com/watch?v=dQw4w9WgXcQ`). The bot should:

1. Reply with `🎬 Fetching available qualities...`
2. Display an inline keyboard with quality options (e.g., `▶ 1920x1080 (mp4) 30fps – 48 MB`)
3. After you tap a quality, proceed with download → archive → upload.

---

## 7. Security Best Practices

### Protect Your Bot Token

- **Never commit the token to Git.** Always use `.env` files or environment variables.
- **Add `.env` to `.gitignore`.** The project template already includes this, but double-check.
- **Rotate tokens regularly.** Use `/revoke` in BotFather if you suspect the token has been leaked.
- **Use GitHub Secrets** if deploying via CI/CD (e.g., GitHub Actions). Never store tokens in repository files.

### Restrict Bot Access

- Keep the `AUTHORIZED_USERS` list minimal. Only add people who genuinely need access.
- Consider using a **private channel** for file distribution so only invited users can access uploaded files.
- Monitor the bot's logs regularly for unauthorized access attempts.

### Secure Your VPS

- Use SSH key authentication (disable password login).
- Set up a firewall (UFW) to only allow necessary ports (SSH, HTTP/HTTPS if applicable).
- Keep your system packages updated with `apt update && apt upgrade`.
- Consider using a reverse proxy (nginx) with HTTPS if exposing any web interface.

### Sensitive Environment Variables

Treat all provider tokens (Bale, Eitaa, ParsaSpace) with the same level of security as your bot token. A compromised provider token could allow unauthorized file uploads to your accounts.

---

## 8. Troubleshooting

### Bot Not Responding

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| Bot does not respond to any message | `TELEGRAM_BOT_TOKEN` is incorrect or missing | Verify the token in `.env`. Check for trailing spaces. |
| Bot responds but says "not authorized" | Your User ID is not in `AUTHORIZED_USERS` | Use `@userinfobot` to get your ID, then add it to `AUTHORIZED_USERS`. |
| Bot crashes on startup | Missing Python dependencies | Run `pip install -r requirements.txt`. |
| No network connectivity on VPS | Firewall or DNS issue | Test with `curl https://api.telegram.org`. Check firewall rules. |

### Upload Failures

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| All providers fail | Provider tokens not configured | Verify `BALE_BOT_TOKEN`, `EITAA_BOT_TOKEN`, or `PARSASPACE_TOKEN` in `.env`. |
| File too large for provider | File exceeds provider's size limit | Reduce `RAR_VOLUME_SIZE_MB` or use ParsaSpace (50 GB limit). |
| "Bot is not a member of the channel" | Bot not added as channel admin | Add the bot as administrator in the target channel. |

### YouTube Feature Issues

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| "No downloadable formats found" | Video is private, age-restricted, or geo-blocked | Try a different video. Ensure `yt-dlp` is up to date. |
| Download times out | Video is very large or VPS has slow internet | Increase timeout in `tools/youtube_downloader.py` or use a VPS with better bandwidth. |
| `yt-dlp` command not found | `yt-dlp` not installed in Docker | Verify the Dockerfile includes `RUN pip install yt-dlp`. |

### Checking Logs

When running with Docker Compose, view logs in real-time:

```bash
docker compose logs -f
```

When running directly:

```bash
python bot.py
```

Logs are printed to stdout with the format:
```
2024-01-15 10:30:45 - __main__ - INFO - User 123456789 (testuser) started the bot
2024-01-15 10:31:02 - __main__ - INFO - User 123456789 (testuser) requested download: https://example.com/file.zip
```
