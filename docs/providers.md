# Provider Setup Guide

This guide explains how to obtain API tokens and configure each supported file-sharing provider.

---

## Bale Messenger

[Bale](https://ble.ir) is a popular Iranian messaging platform with bot support similar to Telegram.

### Step 1: Create a Bot

1. Open Bale on your phone or visit the web version.
2. Search for **@BotFather** and start a conversation.
3. Send `/newbot` and follow the prompts to name your bot.
4. You will receive a **Bot Token** (e.g., `123456:ABC-DEF1234...`).

### Step 2: Create a Channel

1. In Bale, tap the menu and select **New Channel**.
2. Give your channel a name and description.
3. Set the channel type to **Public**.
4. Note the **channel username** (e.g., `@my_file_channel`).

### Step 3: Add Bot as Admin

1. Open the channel settings.
2. Go to **Administrators** → **Add Admin**.
3. Search for your bot by username and add it.
4. Grant the bot **posting permissions**.

### Step 4: Configure Environment Variables

```ini
BALE_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
BALE_CHAT_ID=@my_file_channel
```

### Size Limits

- Bale supports file uploads up to approximately **2 GB**.
- For files larger than 2 GB, the system will automatically split them into volumes.

### Notes

- Bale Bot API does not provide direct download URLs by default. Users find the file in the channel.
- For large channels, ensure your bot has the necessary posting rate limits.

---

## Eitaa Messenger

[Eitaa](https://eitaa.com) is another Iranian messaging platform with a Telegram-compatible bot API.

### Step 1: Register on EitaaYar

1. Visit [EitaaYar](https://web.eitaayar.com).
2. Register or log in with your Eitaa account.

### Step 2: Create a Bot

1. In EitaaYar, navigate to **Bot Management**.
2. Click **Create New Bot**.
3. Set the bot's name, username, and description.
4. You will receive a **Bot Token**.

### Step 3: Create a Channel or Group

1. In the Eitaa app, create a **channel** or **group** where files will be posted.
2. Note the **numeric channel/group ID** (visible in the channel info).

### Step 4: Add Bot to Channel

1. Open the channel settings.
2. Add your bot as an administrator.
3. Ensure the bot has permission to post messages.

### Step 5: Configure Environment Variables

```ini
EITAA_BOT_TOKEN=your_eitaa_bot_token
EITAA_CHAT_ID=123456789
```

### Size Limits

- Eitaa supports file uploads up to approximately **2 GB**.
- The Eitaa Bot API returns file IDs that can be used to construct direct download URLs.

### Notes

- Eitaa's Bot API is largely compatible with Telegram's Bot API format.
- The bot constructs download URLs as `https://eitaa.com/file/{file_id}`.

---

## ParsaSpace

[ParsaSpace](https://parsaspace.com) is an Iranian cloud storage service that provides direct download links through a REST API.

### Step 1: Create an Account

1. Visit [parsaspace.com](https://parsaspace.com).
2. Register for a free account.
3. Verify your email address.

### Step 2: Get API Token

1. Log in to your ParsaSpace dashboard.
2. Navigate to **API Settings** or **Developer Settings**.
3. Generate a new API token.
4. Copy and save the token securely.

### Step 3: Set Up a Domain

1. In the dashboard, go to **Domain Settings**.
2. Add or select a subdomain (e.g., `myfiles.parsaspace.com`).
3. Note your domain name.

### Step 4: Configure Environment Variables

```ini
PARSASPACE_TOKEN=your_parsaspace_api_token
PARSASPACE_DOMAIN=myfiles.parsaspace.com
```

### Size Limits

- ParsaSpace supports very large file uploads (up to **50 GB** for premium accounts).
- Free accounts may have lower limits — check your plan details.
- Direct download links are provided for each uploaded file.

### Notes

- ParsaSpace is the recommended provider for large files due to its high size limits and direct URL support.
- The upload uses streaming to handle large files efficiently.

---

## Provider Priority and Fallback

The `PROVIDER_PRIORITY` environment variable controls the order in which providers are tried.

### Configuration

```ini
# Try Bale first, then Eitaa, then ParsaSpace
PROVIDER_PRIORITY=Bale,Eitaa,ParsaSpace

# Only use ParsaSpace
PROVIDER_PRIORITY=ParsaSpace

# Try Eitaa first for direct URLs, fallback to messaging platforms
PROVIDER_PRIORITY=Eitaa,ParsaSpace,Bale
```

### How Fallback Works

1. The system tries the **first provider** in the priority list.
2. If the provider is **not configured** (missing env vars), it is **skipped**.
3. If the **file exceeds** the provider's size limit, it is **skipped**.
4. If the upload **fails** (network error, API error), the **next provider** is tried.
5. If **all providers fail**, the user receives an error message with details.

### Choosing the Right Priority

| Priority Recommendation | Reason |
|---|---|
| `ParsaSpace` first | Best for large files — high size limit, direct URLs |
| `Eitaa` first | Provides direct download URLs via messenger |
| `Bale` first | Popular platform, users already have accounts |
| `ParsaSpace` last | Acts as a reliable fallback with large capacity |

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|---|---|
| "BALE_BOT_TOKEN not set" | Add your token to `.env` and restart the container |
| "Storage quota exceeded" | Free up space on your provider or upgrade your plan |
| "File too large" | Reduce `RAR_VOLUME_SIZE_MB` or use a provider with higher limits |
| "bot was blocked by the user" | Ensure the bot is added as admin to the channel |
| Upload timeout | Check your VPS internet connection and increase `SINGLE_UPLOAD_MAX_MB` |
