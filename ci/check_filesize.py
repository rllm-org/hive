"""Enforce 500-line max for Python files under src/."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
LIMIT = 500

# Legacy modules over the limit; new code should stay under LIMIT (split instead of adding here).
_GRANDFATHERED = frozenset(
    {
        "src/hive/server/db.py",
        "src/hive/server/items.py",
        "src/hive/server/main.py",
        "src/hive/server/verification.py",
        "src/hive/server/verifier.py",
    }
)

violations = []
for py in sorted(SRC.rglob("*.py")):
    lines = len(py.read_text().splitlines())
    rel = py.relative_to(SRC.parent).as_posix()
    if lines > LIMIT and rel not in _GRANDFATHERED:
        violations.append(f"  {py.relative_to(SRC.parent)}: {lines} lines (max {LIMIT})")

if violations:
    print("FAIL: files over size limit")
    print("\n".join(violations))
    print("FIX: split large files into smaller modules")
    sys.exit(1)

print("OK: all files under size limit")
