# Automatic File Cleanup (VALID_DAYS)

Providers that support object or file deletion can automatically clean up old files before each new upload. This prevents storage from filling up over time and keeps your provider accounts within free-tier limits.

---

## How It Works

Cleanup runs **inline** before each upload attempt — there is no background polling, cron job, or scheduler. When the upload manager selects a provider for uploading, it first checks whether that provider has cleanup configured. If enabled, old files are deleted before the new upload begins.

The flow:

```
User sends URL → Bot downloads file → Bot creates RAR archive
    │
    ▼
Upload manager selects provider (e.g., ArvanCloud)
    │
    ▼
Check ARVAN_VALID_DAYS → If > 0, run cleanup
    │
    ├── List objects under hybrid-rar-bridge/ prefix
    ├── Delete objects older than N days
    └── Log number of deleted objects
    │
    ▼
Upload new file → Return download link
```

Only files uploaded by the bot are affected. Each provider stores files under a `hybrid-rar-bridge/` prefix, so cleanup only targets files in that directory.

---

## Supported Providers

| Provider | Env Variable | Default | Mechanism |
|---|---|---|---|
| ArvanCloud | `ARVAN_VALID_DAYS` | `0` (off) | S3 `list_objects_v2` + `delete_objects` by `LastModified` |
| Liara | `LIARA_VALID_DAYS` | `0` (off) | REST API `GET /v1/objects/{bucket}` + `DELETE` by `updatedAt` |
| PicoFile | `PICOFILE_VALID_DAYS` | `0` (off) | Reverse-engineered `GET /api/files` + `DELETE /api/file/{id}` |

Bale, Eitaa, and ParsaSpace do **not** support automatic cleanup — messaging platforms don't expose a file deletion API, and ParsaSpace's API doesn't include a list-and-delete workflow.

---

## Configuration

Add the `*_VALID_DAYS` variable to your `.env` file:

```ini
# Delete files older than 2 days before each upload
ARVAN_VALID_DAYS=2
LIARA_VALID_DAYS=2
PICOFILE_VALID_DAYS=2

# Disable cleanup for a specific provider
ARVAN_VALID_DAYS=0
```

A value of `0` (the default) means cleanup is disabled. Any positive integer enables cleanup.

---

## Choosing the Right Value

| Value | Use Case |
|---|---|
| `1` | Aggressive cleanup — only keeps today's files. Best for high-frequency bots with limited bandwidth. |
| `2` | Balanced — keeps yesterday's and today's files. Recommended for most setups. |
| `3-7` | Conservative — files stay available for several days. Good for bots shared among multiple users. |
| `0` | Disabled — no automatic cleanup. Use this if you manage storage manually. |

Consider your provider's free tier limits:

- **ArvanCloud**: 50 GB free bandwidth/month. If you upload ~5 GB/day, set `VALID_DAYS=2` to stay within limits.
- **Liara**: Check Liara's pricing page for storage and bandwidth costs.
- **PicoFile**: 20 GB total storage. Set `VALID_DAYS` based on your average daily upload volume.

---

## Implementation Details

### Cleanup Coordinator (`tools/file_cleaner.py`)

The `file_cleaner` module is the central coordinator. The upload manager calls `maybe_cleanup(provider_name)` before each upload. This function:

1. Reads the `*_VALID_DAYS` environment variable for the provider.
2. If `> 0`, dynamically imports the provider's module and calls `cleanup_old_files(valid_days)`.
3. Returns the number of deleted objects (0 if disabled or on error).

The cleanup is **best-effort**: if it fails (network error, API change, authentication issue), the error is logged but the upload still proceeds. This ensures that a broken cleanup never blocks file uploads.

### Per-Provider Cleanup Logic

Each provider implements its own `cleanup_old_files(valid_days)` async function:

**ArvanCloud** — Uses `boto3` S3 pagination to list all objects under `hybrid-rar-bridge/`. Compares each object's `LastModified` timestamp against the cutoff. Deletes in batches using `delete_objects()`.

**Liara** — Lists objects via `GET /v1/objects/{bucket}?prefix=hybrid-rar-bridge/`. Parses ISO timestamps from the `updatedAt` field. Deletes each old object individually via `DELETE /v1/objects/{bucket}/{key}`.

**PicoFile** — Fetches the file list via `GET /api/files` (or `/api/file/list`). Parses upload dates. Deletes old files via `DELETE /api/file/{id}`. Since PicoFile has no official API, this may break if the website changes.

---

## Log Output

When cleanup runs, you'll see entries like these in the Docker logs:

```
tools.file_cleaner - INFO - Cleaned up 5 old objects from ArvanCloud (valid_days=2)
tools.arvan_uploader - INFO - ArvanCloud cleanup: deleted 5 objects older than 2 days
```

When cleanup is disabled or no old files are found, no log entries are produced (silent).

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Cleanup not running | Verify `*_VALID_DAYS` is set to a positive integer in `.env` |
| "boto3 not installed" warning | Rebuild the Docker image: `docker-compose up -d --build` |
| Files not being deleted | Check provider credentials — cleanup uses the same credentials as upload |
| PicoFile cleanup failing | PicoFile's website may have changed. Check logs for details. |
| Cleanup slowing down uploads | Reduce `VALID_DAYS` or set to `0` if cleanup isn't needed |
