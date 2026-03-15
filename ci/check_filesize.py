"""Enforce 500-line max for Python files under src/."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
LIMIT = 500

violations = []
for py in sorted(SRC.rglob("*.py")):
    lines = len(py.read_text().splitlines())
    if lines > LIMIT:
        violations.append(f"  {py.relative_to(SRC.parent)}: {lines} lines (max {LIMIT})")

if violations:
    print("FAIL: files over size limit")
    print("\n".join(violations))
    print("FIX: split large files into smaller modules")
    sys.exit(1)

print("OK: all files under size limit")
