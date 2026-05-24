# Provider Setup Guide

This guide explains how to obtain API tokens and configure each of the six supported upload providers. Each section includes step-by-step setup instructions, required environment variables, size limits, and provider-specific notes.

---

## ArvanCloud Object Storage

[ArvanCloud Object Storage](https://www.arvancloud.com/en/products/object-storage) is an S3-compatible cloud storage service hosted in Iran. It provides **50 GB free bandwidth per month**, **1 million free API requests**, and **unlimited upload**. Files are accessible via direct public URLs when the bucket is configured for public access.

ArvanCloud is the **recommended first-choice provider** because it offers direct download links, generous free bandwidth, and a reliable S3-compatible API.

### Step 1: Create an Account

1. Visit [ArvanCloud](https://console.arvancloud.com) and sign up.
2. Verify your email address and phone number.
3. Log in to the ArvanCloud console.

### Step 2: Create a Bucket

1. Navigate to **Object Storage** in the console sidebar.
2. Click **Create Bucket**.
3. Choose a bucket name (e.g., `my-bridge-files`). This name will appear in the download URL.
4. Select the **Tehran** region (`ir-thr-at1`).
5. Set the bucket **access policy to Public** so that uploaded files can be downloaded without authentication.

### Step 3: Create Machine User Access Keys

1. Go to **Settings** (or Account Settings).
2. Find **Machine Users** (or API Users) and click **Create**.
3. Give the user a descriptive name (e.g., `hybrid-bridge`).
4. After creation, copy the **Access Key** and **Secret Key**. These are shown only once.
5. Grant the machine user **read/write** permissions on your bucket.

### Step 4: Configure Environment Variables

```ini
ARVAN_ACCESS_KEY=your_access_key_here
ARVAN_SECRET_KEY=your_secret_key_here
ARVAN_BUCKET=my-bridge-files
# Optional: override the default S3 endpoint
# ARVAN_ENDPOINT=s3.ir-thr-at1.arvanstorage.ir
# Optional: auto-delete files older than N days (0 = disabled)
ARVAN_VALID_DAYS=2
```

### Size Limits

- **Default max upload**: 5 GB per file (practical single-request limit).
- Customizable via `ARVAN_MAX_UPLOAD_MB` (default: 5120).
- Bandwidth: 50 GB/month on the free tier.
- No per-file cost on the free tier.

### Download URL Format

```
https://{bucket-name}.s3.ir-thr-at1.arvanstorage.ir/hybrid-rar-bridge/{filename}
```

### Notes

- Requires the `boto3` package (included in `requirements.txt`).
- Uploaded files are placed under the `hybrid-rar-bridge/` prefix to keep them organized.
- The `ARVAN_VALID_DAYS` setting automatically deletes old files before each new upload (no polling or cron needed). Set to `0` to disable.
- Make sure your bucket is publicly accessible, otherwise download links will return 403.

---

## Liara Object Storage

[Liara.ir](https://liara.ir) is an Iranian cloud platform offering object storage with presigned-URL uploads. It has a limited free tier and then charges pay-as-you-go. Liara provides **direct download links** for uploaded files.

### Step 1: Create an Account

1. Visit [Liara Console](https://console.liara.ir) and register.
2. Verify your email address.
3. Log in to the dashboard.

### Step 2: Create a Bucket

1. Navigate to **Object Storage** in the sidebar.
2. Click **Create Bucket** (or "Create Storage").
3. Choose a bucket name (e.g., `bridge-downloads`).
4. Select the **Iran** region for best connectivity.
5. Note the bucket name for the environment variable.

### Step 3: Get Your API Key

1. Go to **Account Settings** or **API Keys**.
2. Generate a new API key.
3. Copy and save the key securely.

### Step 4: Configure Environment Variables

```ini
LIARA_API_KEY=your_liara_api_key
LIARA_BUCKET=bridge-downloads
# Optional: override the default endpoint
# LIARA_ENDPOINT=https://storage.iran.liara.ir
# Optional: auto-delete files older than N days (0 = disabled)
LIARA_VALID_DAYS=2
```

### Size Limits

- **Default max upload**: 5 GB per file.
- Customizable via `LIARA_MAX_UPLOAD_MB` (default: 5120).
- Free tier has limited storage; check Liara's pricing page for details.

### Download URL Format

```
https://{bucket-name}.storage.iran.liara.ir/hybrid-rar-bridge/{filename}
```

### Notes

- Uses a two-step upload: first requests a presigned PUT URL from Liara's API, then uploads the file directly to that URL. This avoids proxying large files through Liara's servers.
- Uploaded files are placed under the `hybrid-rar-bridge/` prefix.
- The `LIARA_VALID_DAYS` setting automatically deletes old files before each new upload.

---

## PicoFile

[PicoFile](https://www.picofile.com) is a free Iranian file-sharing service offering **20 GB storage** and **2 GB per file** with public download links.

> **WARNING**: PicoFile does **not** have an official public API. This module reverse-engineers the web upload flow (login + CSRF + multipart POST). If PicoFile changes its website structure, the uploader may break without notice.

### Step 1: Create an Account

1. Visit [picofile.com](https://www.picofile.com).
2. Click **Register** and create an account with your email and password.
3. Verify your email address.

### Step 2: Configure Environment Variables

```ini
PICOFILE_EMAIL=your_email@example.com
PICOFILE_PASSWORD=your_account_password
# Optional: auto-delete files older than N days (0 = disabled)
PICOFILE_VALID_DAYS=2
```

### Size Limits

- **Default max upload**: 2 GB per file.
- Customizable via `PICOFILE_MAX_UPLOAD_MB` (default: 2048).
- Total storage: 20 GB on free accounts.

### Notes

- Because there is no official API, this module simulates a browser session (CSRF token, cookies, multipart upload). If uploads start failing, check the logs for detailed error messages and the PicoFile website for any structural changes.
- The `PICOFILE_VALID_DAYS` setting attempts to delete old files via the same reverse-engineered API. It fetches the file list and deletes entries older than the configured number of days.
- For reliability, prefer ArvanCloud or Liara over PicoFile when possible.

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
2. Go to **Administrators** -> **Add Admin**.
3. Search for your bot by username and add it.
4. Grant the bot **posting permissions**.

### Step 4: Configure Environment Variables

```ini
BALE_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
BALE_CHAT_ID=@my_file_channel
# Optional: override the default upload limit (default: 45 MB)
# BALE_MAX_UPLOAD_MB=45
```

### Size Limits

- Bale's HTTP API (tapi.bale.ai) has an **nginx limit of ~50 MB** per request.
- The bot defaults to **45 MB** to account for RAR volume overhead (the archiver applies an additional 90% safety margin, so actual RAR parts will be ~40 MB).
- Files exceeding the limit are automatically split into volumes.

### Notes

- Bale Bot API does not provide direct download URLs by default. Users find the file in the channel.
- If the `balebot` Python package is installed, it will be used; otherwise, the bot falls back to direct HTTP API calls.
- Bale is best used as a **fallback** provider rather than the primary choice, due to the low upload size limit.

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
# Optional: override the default upload limit (default: 50 MB)
# EITAA_MAX_UPLOAD_MB=50
```

### Size Limits

- Eitaa supports file uploads up to approximately **2 GB** via the bot API.
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
# Optional: override the default upload limit (default: 50 GB)
# PARSASPACE_MAX_UPLOAD_MB=51200
```

### Size Limits

- ParsaSpace supports very large file uploads (up to **50 GB** for premium accounts).
- Free accounts may have lower limits. Check your plan details.
- Direct download links are provided for each uploaded file.

### Notes

- ParsaSpace is a solid choice for large files due to its high size limits and direct URL support.
- The upload uses streaming to handle large files efficiently.

---

## Provider Priority and Fallback

The `PROVIDER_PRIORITY` environment variable controls the order in which providers are tried. When a provider fails or the file exceeds its size limit, the next provider in the list is automatically tried.

### Configuration

```ini
# Recommended: Object storage first (direct links), messaging as fallback
PROVIDER_PRIORITY=ArvanCloud,Liara,ParsaSpace,Bale,Eitaa,PicoFile

# Only use ArvanCloud
PROVIDER_PRIORITY=ArvanCloud

# Messaging platforms only
PROVIDER_PRIORITY=Bale,Eitaa

# Object storage with ParsaSpace as reliable fallback
PROVIDER_PRIORITY=ArvanCloud,Liara,ParsaSpace
```

### How Fallback Works

1. The system tries the **first provider** in the priority list.
2. If the provider is **not configured** (missing env vars), it is **skipped**.
3. If the **file exceeds** the provider's size limit, it is **skipped**.
4. If the upload **fails** (network error, API error, 413), the **next provider** is tried.
5. If **all providers fail**, the user receives an error message with details.

### Choosing the Right Priority

| Priority Recommendation | Reason |
|---|---|
| `ArvanCloud` first | Best overall — direct URLs, 50 GB free bandwidth, S3 API |
| `Liara` second | Good alternative — direct URLs, presigned uploads |
| `ParsaSpace` third | High size limit (50 GB), direct URLs |
| `Bale` / `Eitaa` last | Messaging platforms — no direct URLs, low size limits |
| `PicoFile` last | No official API, may break without notice |

### File Cleanup (VALID_DAYS)

Providers that support object/file deletion (ArvanCloud, Liara, PicoFile) have a `*_VALID_DAYS` environment variable. When set to a value greater than 0, the bot automatically deletes files older than that many days **before each new upload**. There is no background polling or cron job.

```ini
# Delete files older than 2 days before each upload
ARVAN_VALID_DAYS=2
LIARA_VALID_DAYS=2
PICOFILE_VALID_DAYS=2
```

Set to `0` (the default) to disable automatic cleanup.

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|---|---|
| "BALE_BOT_TOKEN not set" | Add your token to `.env` and restart the container |
| "ARVAN_ACCESS_KEY not set" | Configure your ArvanCloud credentials in `.env` |
| "PicoFile login failed" | Check PICOFILE_EMAIL and PICOFILE_PASSWORD; PicoFile may have changed its login flow |
| "Storage quota exceeded" | Free up space on your provider or upgrade your plan |
| "File too large" | Reduce `RAR_VOLUME_SIZE_MB` or use a provider with higher limits |
| "bot was blocked by the user" | Ensure the bot is added as admin to the channel |
| Upload timeout | Check your VPS internet connection and increase `SINGLE_UPLOAD_MAX_MB` |
| Bale 413 error even with small files | The bot applies a 90% safety margin on volume sizes. If you still get 413, lower `BALE_MAX_UPLOAD_MB` further (e.g., to 40) |
| "boto3 not installed" | Run `pip install boto3` or rebuild the Docker image |
