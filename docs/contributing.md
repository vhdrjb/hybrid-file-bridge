# Contributing Guide

Thank you for your interest in contributing to the Hybrid RAR File Bridge! This guide covers how to set up a development environment, follow coding standards, and submit changes.

---

## Prerequisites

- **Python 3.11+** (3.11 recommended for consistency with Docker)
- **Docker** (for running the full application)
- **Git** with your preferred email and name configured
- **pip** and **virtualenv** (or use Docker for development)

---

## Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/hybrid-file-bridge.git
cd hybrid-file-bridge
git remote add upstream https://github.com/vhdrjb/hybrid-file-bridge.git
```

### 2. Set Up a Development Environment

#### Option A: Local Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

You will also need `rar` and `aria2` installed:

```bash
# Ubuntu/Debian
sudo apt install rar aria2

# macOS
brew install rar
brew install aria2

# Fedora
sudo dnf install rar aria2
```

#### Option B: Docker Development

```bash
cp .env.example .env
# Edit .env with your development tokens
docker-compose up -d
docker-compose logs -f  # Watch logs
```

### 3. Verify Setup

```bash
python -m pytest tests/ -v
```

You should see tests passing (some RAR tests may be skipped if `rar` is not installed).

---

## Code Style

This project follows **PEP 8** conventions with the following tools:

### Formatting

```bash
# Auto-format code
black tools/ bot.py tests/
isort tools/ bot.py tests/
```

### Linting

```bash
flake8 tools/ bot.py tests/
```

### Configuration

- **black**: Default settings (88 character line length)
- **isort**: Default profile
- **flake8**: Max line length 100, ignore E501 for docstrings

---

## Running Tests

### All Tests

```bash
python -m pytest tests/ -v
```

### Specific Test Module

```bash
python -m pytest tests/test_downloader.py -v
python -m pytest tests/test_upload_manager.py -v
```

### With Coverage

```bash
pip install pytest-cov
python -m pytest tests/ -v --cov=tools --cov=bot --cov-report=term-missing
```

---

## Adding a New Provider

To add a new file-sharing provider, follow these steps:

### 1. Create the Uploader Module

Create `tools/<provider_name>_uploader.py`:

```python
"""
<Provider Name> uploader module.

Uploads files to <Provider Name> via its API.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROVIDER_MAX_SIZE = 2 * 1024 * 1024 * 1024  # Max upload size in bytes


async def upload(file_path: Path) -> str:
    """
    Upload a file to <Provider Name>.

    Args:
        file_path: Path to the file to upload.

    Returns:
        A download URL or reference string.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If the upload fails.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Implement your upload logic here
    # ...
    return "https://provider.com/file/123"
```

### 2. Register the Provider

Edit `tools/upload_manager.py` and add your provider:

1. Import the upload function.
2. Add it to `all_providers` dict in `get_providers()`.
3. Define the size limit and required env vars.

### 3. Add Environment Variables

Add to `.env.example`:

```ini
NEWPROVIDER_TOKEN=your_new_provider_token
NEWPROVIDER_CHAT_ID=@your_channel
```

### 4. Write Unit Tests

Create tests in `tests/test_uploaders.py`:

```python
class TestNewProviderUploader:
    @pytest.mark.asyncio
    async def test_upload_success(self, sample_file, mock_env):
        # Mock the API and verify success
        ...

    @pytest.mark.asyncio
    async def test_upload_missing_token(self, sample_file, monkeypatch):
        # Verify missing config raises RuntimeError
        ...
```

### 5. Update Documentation

- Add provider to `docs/providers.md` with setup instructions.
- Update `README.md` table of environment variables.

---

## Pull Request Process

1. **Create a feature branch**: `git checkout -b feature/my-feature`
2. **Make your changes** with proper commit messages.
3. **Run tests**: `python -m pytest tests/ -v`
4. **Run linting**: `flake8 tools/ bot.py tests/`
5. **Format code**: `black tools/ bot.py tests/ && isort tools/ bot.py tests/`
6. **Commit and push**: `git push origin feature/my-feature`
7. **Open a Pull Request** against the `main` branch.
8. **Describe your changes** clearly in the PR description.

### Commit Message Format

```
type(scope): brief description

Detailed description of the change, if needed.
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

Examples:
```
feat(uploader): add SibFile provider support
fix(downloader): handle connection timeout gracefully
test(manager): add fallback order tests
```

---

## Project Structure

```
hybrid-rar-bridge/
├── bot.py                    # Telegram bot — entry point, handlers, main loop
├── tools/                    # Core modules (each has single responsibility)
│   ├── __init__.py
│   ├── downloader.py         # aria2c async download wrapper
│   ├── rar_archiver.py       # RAR creation and volume splitting
│   ├── upload_manager.py     # Fallback orchestration and provider registry
│   ├── bale_uploader.py      # Bale Messenger upload
│   ├── eitaa_uploader.py     # Eitaa Messenger upload
│   └── parsaspace_uploader.py # ParsaSpace REST API upload
├── tests/                    # Test suite
│   ├── conftest.py           # Shared fixtures
│   ├── test_downloader.py
│   ├── test_rar_archiver.py
│   ├── test_uploaders.py
│   ├── test_upload_manager.py
│   └── test_bot_integration.py
├── docs/                     # Documentation
├── Dockerfile                # Production Docker image
├── docker-compose.yml        # Container orchestration
├── requirements.txt          # Python dependencies
├── pytest.ini                # Test configuration
├── .env.example              # Environment template
└── README.md                 # Main documentation
```

---

## Questions?

If you have questions, feel free to open an issue on GitHub for discussion before submitting a PR.
