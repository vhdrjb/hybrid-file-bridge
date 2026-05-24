# Development Guide

This document covers the architecture, design decisions, and technical details of the Hybrid RAR File Bridge.

---

## Architecture Overview

```
┌──────────────┐     URL      ┌─────────────────────────────────────────────┐
│  Telegram    │ ──────────>  │              Bot (bot.py)                  │
│  User        │              │  ┌─────────┐  ┌────────┐  ┌─────────────┐  │
└──────────────┘              │  │  Auth   │→ │Download│→ │RAR Archiver │  │
                              │  └─────────┘  └────────┘  └──────┬──────┘  │
┌──────────────┐              │                                    │         │
│  Download    │ ←──────────── │                                    ▼         │
│  Link + Pass │ ──────────>  │  ┌─────────────────────────────────────┐    │
└──────────────┘              │  │        Upload Manager               │    │
                              │  │  ┌──────┐ ┌────┐ ┌────┐        │    │
                              │  │  │Arvan │ │Liara│ │Pico│...   │    │
                              │  │  └──┬───┘ └──┬─┘ └─┬──┘        │    │
                              │  │     └───────┴──────┘          │    │
                              │  └─────────────────────────────────────┘    │
                              └─────────────────────────────────────────────┘
                                        │
                                        ▼
                              ┌──────────────────────┐
                              │  Upload Providers     │
                              │  ArvanCloud | Liara   │
                              │  PicoFile | ParsaSpace│
                              │  Bale | Eitaa        │
                              └──────────────────────┘
```

### Data Flow

1. **User sends URL** → Telegram delivers update to bot
2. **Auth check** → Verify user is in AUTHORIZED_USERS list
3. **Download** → `aria2c` subprocess downloads file to `downloads/` directory
4. **Password generation** → `secrets` module generates 16-char password
5. **Size check** → If file ≤ SINGLE_UPLOAD_MAX_MB, single RAR; otherwise split
6. **Archive** → `rar` subprocess creates encrypted archive(s)
7. **Upload** → Upload manager tries providers in priority order with fallback
8. **Reply** → Bot sends download link(s) and password to user
9. **Cleanup** → Temporary files and archives are deleted

---

## Module Responsibilities

### `bot.py` — Main Application

The entry point that:
- Loads environment configuration via `python-dotenv`
- Registers Telegram command and message handlers
- Orchestrates the download → archive → upload pipeline
- Manages user communication (status updates, error messages)
- Handles cleanup of temporary files

Key design decisions:
- Each user request runs independently (concurrent updates enabled)
- Status messages keep the user informed during long operations
- All errors are caught and sent to the user (no silent failures)

### `tools/downloader.py` — File Download

Wraps `aria2c` as an async subprocess:
- Multi-connection downloads (16 connections, 1MB split size)
- Configurable retry (5 attempts, 3-second wait)
- Timeout protection (1 hour maximum per file)
- Filename extraction from URL with fallback

### `tools/rar_archiver.py` — Archive Operations

Wraps the `rar` command-line utility:
- Single archive creation with `-p` password flag
- Multi-part volume splitting with `-v` flag
- The `-ep` flag ensures relative paths in archives
- Uses `-m3` compression for balanced speed/ratio

### `tools/upload_manager.py` — Provider Orchestration

The central upload coordinator:
- Reads `PROVIDER_PRIORITY` from environment
- Maintains a registry of all providers with size limits
- Checks environment variable availability before attempting upload
- Implements sequential fallback: try next provider on failure
- Returns rich `UploadResult` with metadata

### Uploaders

Each uploader follows a consistent interface: `async upload(file_path: Path) -> str`

All uploaders:
- Validate the file exists before upload
- Check for required environment variables
- Provide HTTP API fallbacks when SDK packages are not installed
- Raise descriptive exceptions on failure

| Module | Provider | Method | Max Size | Direct URLs | Cleanup |
|---|---|---|---|---|---|
| `arvan_uploader.py` | ArvanCloud | S3 (boto3) | 5 GB | Yes | Yes |
| `liara_uploader.py` | Liara | Presigned URL | 5 GB | Yes | Yes |
| `picofile_uploader.py` | PicoFile | Web API (reverse-engineered) | 2 GB | Yes | Yes |
| `parsaspace_uploader.py` | ParsaSpace | REST API | 50 GB | Yes | No |
| `bale_uploader.py` | Bale | Bot HTTP API | ~45 MB | No (channel) | No |
| `eitaa_uploader.py` | Eitaa | Bot HTTP API | ~50 MB | Yes (file ID) | No |

### `tools/file_cleaner.py` — Automatic File Cleanup

Coordinates age-based cleanup for providers that support it (ArvanCloud, Liara, PicoFile). Before each upload, the upload manager calls `maybe_cleanup(provider_name)` which checks the `*_VALID_DAYS` environment variable. When the value is greater than zero, files older than that many days are deleted from the provider's storage.

---

## Error Handling Strategy

The project uses a layered error handling approach:

### Layer 1: Module Level
Each module validates its inputs and raises specific exceptions:
- `FileNotFoundError` for missing files
- `RuntimeError` for operational failures (API errors, subprocess failures)

### Layer 2: Upload Manager
The upload manager catches exceptions from individual providers and:
- Logs the error with context
- Continues to the next provider
- Aggregates all errors if all providers fail

### Layer 3: Bot Handler
The bot handler catches all exceptions and:
- Sends a user-friendly error message
- Logs the full traceback for debugging
- Ensures temporary files are cleaned up (via `tempfile.TemporaryDirectory`)

### Timeout Protection
- Download: 1 hour maximum per file
- Upload: 30 minutes per file (ParsaSpace), 10 minutes (messaging APIs)
- Connection: 30-second connect timeout, 60-second read timeout

---

## Logging Guidelines

The project uses Python's `logging` module with consistent formatting:

```python
import logging
logger = logging.getLogger(__name__)
```

### Log Levels

| Level | Usage |
|---|---|
| `DEBUG` | Command construction, API request details |
| `INFO` | Operation start/completion, file sizes, provider selection |
| `WARNING` | Skipped providers, fallback triggers, missing packages |
| `ERROR` | Upload failures, subprocess errors, API errors |
| `EXCEPTION` | Unexpected errors with full traceback |

### Log Format

```
2024-01-15 10:30:45,123 - tools.downloader - INFO - Download complete: file.zip (120.50 MB)
```

---

## Testing Strategy

### Unit Tests
Test individual modules in isolation with mocked dependencies:
- **Downloader tests**: Mock `asyncio.create_subprocess_exec` for aria2c
- **RAR archiver tests**: Mock subprocess calls; real tests when `rar` is available
- **Uploader tests**: Mock HTTP requests and SDK packages
- **Upload manager tests**: Mock individual uploaders to test fallback logic

### Integration Tests
Test the bot handler end-to-end with all dependencies mocked:
- Simulate Telegram updates with mock user/message objects
- Verify the full pipeline: download → archive → upload → reply
- Test error handling paths

### Test Conventions
- All async tests use `@pytest.mark.asyncio`
- Fixtures in `conftest.py` provide temp directories and mock environments
- Tests that require external tools (rar) are conditionally skipped
- No actual network calls in any test

---

## Docker Details

### Why `rar` and `aria2c` from apt?

- `rar` is the official RAR compression tool — needed for creating password-protected RAR archives (the free `unrar` only extracts)
- `aria2c` provides superior download performance compared to Python HTTP libraries, especially for large files with multi-connection support
- Both are lightweight CLI tools ideal for subprocess execution

### Build Optimizations

- Uses `python:3.11-slim` as base for minimal image size
- Multi-verse repository enabled for `rar` package
- `--no-install-recommends` to reduce image bloat
- Cleanup of apt lists after installation

### Runtime

- `restart: unless-stopped` ensures the bot recovers from crashes
- Volume mounts for `downloads/` (persistent) and `tools/` (hot-reload during development)
- Environment variables loaded from `.env` file

---

## Debugging

### Check Logs

```bash
# Real-time logs
docker-compose logs -f bridge

# Last 100 lines
docker-compose logs --tail=100 bridge
```

### Attach to Container

```bash
# Interactive shell
docker exec -it hybrid-rar-bridge bash

# Test rar installation
rar --version

# Test aria2c
aria2c --version

# Check downloads directory
ls -la /app/downloads/
```

### Common Issues

| Symptom | Cause | Solution |
|---|---|---|
| Bot doesn't start | Missing token | Check `.env` file |
| Downloads fail | No internet access | Check VPS network |
| RAR creation fails | `rar` not installed | Rebuild Docker image |
| Upload fails | Provider down | Check `PROVIDER_PRIORITY` order |
| Memory issues | Large files | Increase Docker memory limit |
