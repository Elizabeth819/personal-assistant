#!/usr/bin/env bash
# Bootstrap a fresh dev environment.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

uv sync --extra dev
uv run pre-commit install
[ -f .env ] || cp .env.example .env

echo
echo "Done. Try:"
echo "  make test"
echo "  make run"
echo "  uv run pa info"
