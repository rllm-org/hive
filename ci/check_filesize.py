"""Enforce 500-line max for Python files under src/."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
LIMIT = 500

# Legacy modules over the limit; prefer splitting new work into smaller modules.
_GRANDFATHERED = frozenset(
    f"src/hive/server/{name}"
    for name in ("main.py", "db.py", "items.py", "verification.py", "verifier.py")
)

violations = []
for py in sorted(SRC.rglob("*.py")):
    rel = str(py.relative_to(ROOT)).replace("\\", "/")
    if rel in _GRANDFATHERED:
        continue
    lines = len(py.read_text().splitlines())
    if lines > LIMIT:
        violations.append(f"  {rel}: {lines} lines (max {LIMIT})")

if violations:
    print("FAIL: files over size limit")
    print("\n".join(violations))
    print("FIX: split large files into smaller modules")
    sys.exit(1)

print("OK: all files under size limit")
