# Hybrid RAR File Bridge

A Dockerised Telegram bot that bridges direct download URLs to free Iranian file-sharing services. Designed for users behind internet restrictions who need to access files hosted on platforms with limited or no access from Iran.

## How It Works

1. **You send a download URL** to the Telegram bot.
2. The bot **downloads the file** on a VPS with free internet access.
3. The file is **archived into a password-protected RAR** (single or multi-part depending on size).
4. The archive is **uploaded to Iranian file-sharing services** (Bale, Eitaa, ParsaSpace) with automatic fallback.
5. You receive the **download link(s) and extraction password**.

```
User (Telegram) --> Bot --> Download (VPS) --> RAR Archive --> Upload --> Iranian Provider
                      |                                                |
                      +--- Download link + password -------------------+
```

## Features

- **Hybrid Fallback System**: Automatically tries multiple providers in priority order. If one fails, the next is used — maximizing reliability.
- **Password-Protected RAR**: Every archive is encrypted with a cryptographically secure 16-character password.
- **Multi-Part Archives**: Large files are split into configurable volume sizes to match provider upload limits.
- **Fast Downloads**: Uses `aria2c` with multi-connection support for high-speed downloads.
- **Free for Iranian Users**: Leverages free Iranian messaging and hosting services.
- **Dockerised**: Easy deployment with a single `docker-compose up -d`.
- **Authorization**: Only approved Telegram users can use the bot.

## Prerequisites

- **Docker** and **Docker Compose** installed on your VPS.
- A **Telegram Bot Token** from [@BotFather](https://t.me/BotFather).
- At least one provider configured (see [Provider Setup](docs/providers.md)).
- Your VPS should have free/uncensored internet access.

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/vhdrjb/hybrid-file-bridge.git
cd hybrid-file-bridge
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Edit `.env` and fill in your credentials:

```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
AUTHORIZED_USERS=123456789,987654321
PROVIDER_PRIORITY=Bale,Eitaa,ParsaSpace
```

### 3. Set Up Providers

See the detailed [Provider Setup Guide](docs/providers.md) for instructions on obtaining tokens for each service.

### 4. Run

```bash
docker-compose up -d
```

### 5. Verify

Check logs:

```bash
docker-compose logs -f bridge
```

You should see: `Bot is running. Press Ctrl+C to stop.`

### 6. Use

Send your Telegram bot a direct download URL. It will process the file and reply with download links.

## Environment Variables

| Variable | Description | Required | Default |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token from @BotFather | Yes | — |
| `AUTHORIZED_USERS` | Comma-separated list of authorized Telegram user IDs | Yes | — |
| `PROVIDER_PRIORITY` | Upload providers in priority order (comma-separated) | No | `Bale,Eitaa,ParsaSpace` |
| `BALE_BOT_TOKEN` | Bale Bot API token | No* | — |
| `BALE_CHAT_ID` | Bale channel username or ID | No* | — |
| `EITAA_BOT_TOKEN` | Eitaa Bot API token | No* | — |
| `EITAA_CHAT_ID` | Eitaa chat or channel ID | No* | — |
| `PARSASPACE_TOKEN` | ParsaSpace API token | No* | — |
| `PARSASPACE_DOMAIN` | Your ParsaSpace subdomain | No* | — |
| `SINGLE_UPLOAD_MAX_MB` | Max file size (MB) for single-part archive | No | `450` |
| `RAR_VOLUME_SIZE_MB` | Volume size (MB) for multi-part archives | No | `450` |
| `TZ` | Timezone for logging | No | `Asia/Tehran` |

*At least one provider must be fully configured.

## Usage

1. Start a conversation with your bot on Telegram.
2. Send `/start` to verify you are authorized.
3. Paste a direct download URL (e.g., `https://example.com/file.zip`).
4. Wait for the bot to process the file (status updates provided).
5. Receive the download link(s) and password.

### Single File Response

```
✅ File Ready!

📄 File: example.zip
📊 Size: 120.5 MB
🌐 Provider: Bale
🔗 Download: https://eitaa.com/file/abc123

🔐 Extraction Password: `xK9#mP2$vL5nQ8wR`

📖 How to extract:
• Windows: Open with WinRAR → Enter password when prompted
• Linux: `unrar x -p{password} your_file.rar`
```

### Multi-Part Response

For files exceeding `SINGLE_UPLOAD_MAX_MB`, the response includes multiple download links — one for each volume part.

## How to Extract

### Windows
Download and install [WinRAR](https://www.win-rar.com/) or [7-Zip](https://www.7-zip.org/). Open the `.rar` or `.part1.rar` file and enter the password when prompted.

### macOS
Use [Keka](https://www.keka.io/) or [The Unarchiver](https://theunarchiver.com/). Open the file and enter the password.

### Linux
```bash
# Install unrar
sudo apt install unrar

# Extract with password
unrar x -pYOUR_PASSWORD your_file.rar

# For multi-part:
unrar x -pYOUR_PASSWORD your_file.part1.rar
```

### Android
Use the [RAR app](https://play.google.com/store/apps/details?id=com.rarlab.rar) from Google Play. Open the archive and enter the password.

**Important for multi-part archives**: Download ALL parts into the same folder, then extract the `.part1.rar` file. All parts must be present in the same directory for extraction to succeed.

## Provider Setup

See [docs/providers.md](docs/providers.md) for detailed instructions on setting up each provider.

## Development

See [docs/development.md](docs/development.md) for architecture overview and development guide.

## Contributing

See [docs/contributing.md](docs/contributing.md) for contribution guidelines.

## Project Structure

```
hybrid-rar-bridge/
├── bot.py                    # Telegram bot entry point and handlers
├── tools/
│   ├── downloader.py         # aria2c-based file downloader
│   ├── rar_archiver.py       # RAR archive creation and splitting
│   ├── upload_manager.py     # Provider fallback orchestration
│   ├── bale_uploader.py      # Bale Messenger upload
│   ├── eitaa_uploader.py     # Eitaa Messenger upload
│   └── parsaspace_uploader.py # ParsaSpace upload
├── tests/                    # Unit and integration tests
├── docs/                     # Documentation
├── Dockerfile                # Docker configuration
├── docker-compose.yml        # Container orchestration
├── requirements.txt          # Python dependencies
└── .env.example              # Environment variable template
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
