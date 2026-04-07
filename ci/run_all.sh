#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
cd "$ROOT"

echo "=== CI: Import smoke test ==="
uv run python ci/check_imports.py

echo ""
echo "=== CI: File size limits ==="
uv run python ci/check_filesize.py

echo ""
echo "=== CI: Test coverage ==="
uv run python ci/check_test_coverage.py

echo ""
echo "=== CI: Unit tests ==="
uv run pytest tests/ -v

echo ""
echo "All CI checks passed."
