#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
cd "$ROOT"

echo "=== CI: Import smoke test ==="
python ci/check_imports.py

echo ""
echo "=== CI: File size limits ==="
python ci/check_filesize.py

echo ""
echo "=== CI: Test coverage ==="
python ci/check_test_coverage.py

echo ""
echo "=== CI: Unit tests ==="
python -m pytest tests/ -v

echo ""
echo "All CI checks passed."
