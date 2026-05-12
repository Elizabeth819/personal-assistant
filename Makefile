.PHONY: help install dev fmt lint type test cov run clean hooks

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime deps
	uv sync

dev:  ## Install dev deps + pre-commit
	uv sync --extra dev
	uv run pre-commit install

fmt:  ## Format code
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint:  ## Lint
	uv run ruff check src tests
	uv run ruff format --check src tests

type:  ## Type-check
	uv run mypy src

test:  ## Run tests
	uv run pytest

cov:  ## Run tests with coverage report
	uv run pytest --cov-report=html

run:  ## Run API server
	uv run uvicorn pa.api.app:app --reload --host $${PA_HOST:-127.0.0.1} --port $${PA_PORT:-8765}

cli:  ## Run CLI (use ARGS="...")
	uv run pa $(ARGS)

hooks:  ## Run pre-commit on all files
	uv run pre-commit run --all-files

clean:  ## Clean caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage dist build
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
