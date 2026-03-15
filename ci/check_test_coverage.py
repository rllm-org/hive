"""Ensure every source module has a corresponding test file."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "hive"
TESTS = ROOT / "tests"

EXEMPT = {"__init__.py"}

missing = []
for py in sorted(SRC.rglob("*.py")):
    if py.name in EXEMPT:
        continue
    rel = py.relative_to(SRC)
    test_path = TESTS / rel.parent / f"test_{rel.name}"
    if not test_path.exists():
        missing.append(f"  {rel} -> tests/{rel.parent}/test_{rel.name}")

if missing:
    print("FAIL: missing test files")
    print("\n".join(missing))
    print("FIX: create the missing test files")
    sys.exit(1)

print("OK: all source files have test coverage")
