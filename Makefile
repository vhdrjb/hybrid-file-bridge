.PHONY: test lint format clean help

# Default target
help:
	@echo "Hybrid RAR File Bridge - Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  test    - Run all tests with pytest"
	@echo "  lint    - Run black, isort, and flake8 checks"
	@echo "  format  - Auto-format code with black and isort"
	@echo "  clean   - Remove cached and temporary files"

# Run all tests
test:
	python -m pytest tests/ -v --tb=short

# Run tests with coverage
test-cov:
	python -m pytest tests/ -v --tb=short --cov=tools --cov=bot --cov-report=term-missing

# Check code quality
lint:
	python -m black --check tools/ bot.py tests/
	python -m isort --check-only tools/ bot.py tests/
	python -m flake8 tools/ bot.py tests/ --max-line-length=100 --ignore=E501,W503

# Auto-format code
format:
	python -m black tools/ bot.py tests/
	python -m isort tools/ bot.py tests/

# Clean temporary and cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .coverage *.egg-info dist build 2>/dev/null || true
