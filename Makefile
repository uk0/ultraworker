.PHONY: install dev format lint typecheck check test test-cov clean run setup

# Install production dependencies
install:
	uv sync --no-dev

# Install with dev dependencies
dev:
	uv sync

# Format code with ruff
format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

# Lint code
lint:
	uv run ruff check src tests

# Type check
typecheck:
	uv run mypy src

# Run all checks (lint + typecheck)
check: lint typecheck

# Run tests
test:
	uv run pytest -v

# Run tests with coverage
test-cov:
	uv run pytest --cov=ultrawork --cov-report=term-missing

# Clean build artifacts
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Run the CLI
run:
	uv run ultrawork

# Launch setup wizard
setup:
	uv run ultrawork setup

# Initialize data directories
init-data:
	mkdir -p data/threads data/tasks data/specs data/index
