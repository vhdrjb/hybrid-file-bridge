# Provider Priority and Automatic Fallback

The bot supports 6 upload providers with automatic fallback. When a provider fails or the file exceeds its size limit, the next one in the priority list is tried automatically. This ensures maximum reliability — even if several providers are down, the user still receives their download link.

---

## Configuration

Set the `PROVIDER_PRIORITY` environment variable as a comma-separated list:

```ini
# Recommended: object storage first (direct links), messaging as fallback
PROVIDER_PRIORITY=ArvanCloud,Liara,ParsaSpace,Bale,Eitaa,PicoFile

# Only use specific providers
PROVIDER_PRIORITY=ArvanCloud,Liara

# Messaging platforms only
PROVIDER_PRIORITY=Bale,Eitaa
```

The default priority (when `PROVIDER_PRIORITY` is not set) is:
```
ArvanCloud,Liara,ParsaSpace,Bale,Eitaa,PicoFile
```

---

## How Fallback Works

```
User sends URL
    │
    ▼
Try Provider #1 (ArvanCloud)
    ├── Not configured? (missing env vars) → Skip, try next
    ├── File too large? (exceeds max_size_mb) → Skip, try next
    ├── Upload failed? (network error, API error) → Log error, try next
    └── Success! → Return download URL to user
         │
         ▼
Try Provider #2 (Liara)
    ├── Not configured? → Skip
    ├── File too large? → Skip
    ├── Upload failed? → Log error, try next
    └── Success! → Return download URL
         │
         ▼
... continues until all providers exhausted ...
         │
         ▼
All providers failed → Send error message with details
```

The upload manager (`tools/upload_manager.py`) orchestrates this fallback chain. For each provider, it checks:

1. **Configuration check** — Are all required environment variables set? If not, the provider is silently skipped.
2. **Size check** — Is the file within the provider's `max_size_mb` limit? If not, the provider is skipped and the reason is logged.
3. **Upload attempt** — The file is uploaded. On success, the `UploadResult` (URL, provider name, metadata) is returned immediately. On failure, the error is logged and the next provider is tried.

If all configured providers fail, an `UploadError` is raised with a summary of all attempted providers and their errors.

---

## 413 Auto-Retry (Entity Too Large)

If a single-file upload fails with HTTP 413 (Request Entity Too Large), the bot automatically enters a retry-with-splitting flow:

1. The upload manager returns an `UploadError` containing 413 error details.
2. The bot detects the 413 via `is_413_error()`.
3. The bot splits the file into RAR volumes matching the smallest configured provider limit.
4. Each volume is uploaded individually using the fallback chain.
5. All volume download links are returned to the user.

This handles cases where the configured `max_size_mb` is inaccurate (e.g., a provider's nginx has a hidden limit lower than the documented one).

---

## Volume Size Safety Margin

RAR's `-v` flag specifies a **target** volume size, not a hard cap. Due to compression block alignment, the actual volume can exceed the target. For example, `-v50m` might produce a 50.8 MB part.

To prevent these oversized volumes from triggering provider upload limits, the archiver applies a **90% safety margin**:

```
Configured limit: 50 MB (BALE_MAX_UPLOAD_MB)
     ↓
After safety margin: 45 MB
     ↓
RAR command: -v45m
     ↓
Actual part size: ~44-46 MB (safely under 50 MB)
```

If you still encounter 413 errors, lower the provider's `*_MAX_UPLOAD_MB` environment variable further.

---

## Per-Provider Size Limits

Each provider has a default `max_size_mb` that can be overridden via environment variables:

| Provider | Default `max_size_mb` | Env Variable | Notes |
|---|---|---|---|
| ArvanCloud | 5120 MB (5 GB) | `ARVAN_MAX_UPLOAD_MB` | S3 single-request practical limit |
| Liara | 5120 MB (5 GB) | `LIARA_MAX_UPLOAD_MB` | Presigned URL limit |
| PicoFile | 2048 MB (2 GB) | `PICOFILE_MAX_UPLOAD_MB` | PicoFile service limit |
| ParsaSpace | 51200 MB (50 GB) | `PARSASPACE_MAX_UPLOAD_MB` | Premium account limit |
| Bale | 45 MB | `BALE_MAX_UPLOAD_MB` | Bale nginx limit (~50 MB, with margin) |
| Eitaa | 50 MB | `EITAA_MAX_UPLOAD_MB` | Eitaa API limit |

The bot's `get_effective_max_upload_mb()` function returns the **smallest** limit across all configured providers. This value is used to decide whether to split a file into volumes.

---

## Recommended Configurations

### Best for Direct Links (Recommended)

```ini
PROVIDER_PRIORITY=ArvanCloud,Liara,ParsaSpace
```

All three provide direct download URLs. ArvanCloud has the best free tier (50 GB bandwidth/month). Liara is a good alternative. ParsaSpace supports very large files (50 GB).

### Maximum Reliability

```ini
PROVIDER_PRIORITY=ArvanCloud,Liara,ParsaSpace,Bale,Eitaa,PicoFile
```

Uses all 6 providers as a fallback chain. Even if 5 providers are down or misconfigured, the 6th will work.

### Messaging Only (No Object Storage Accounts)

```ini
PROVIDER_PRIORITY=Eitaa,Bale
```

For users who only have messaging platform accounts. Note the low size limits (~45-50 MB per file).

### Large File Priority

```ini
PROVIDER_PRIORITY=ParsaSpace,ArvanCloud,Liara
```

ParsaSpace supports up to 50 GB per file, making it ideal for large downloads. ArvanCloud and Liara serve as fallbacks with 5 GB limits.
