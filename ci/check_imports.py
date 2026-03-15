"""Smoke-import every module under src/hive/."""

import importlib
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

errors = []
count = 0

for py in sorted(SRC.rglob("*.py")):
    rel = py.relative_to(SRC)
    if rel.name == "__init__.py":
        mod = str(rel.parent).replace("/", ".")
    elif rel.name == "__main__.py":
        continue
    else:
        mod = str(rel.with_suffix("")).replace("/", ".")
    try:
        importlib.import_module(mod)
        count += 1
    except Exception as e:
        errors.append(f"  {mod}: {e}")

if errors:
    print("FAIL: import errors")
    print("\n".join(errors))
    sys.exit(1)

print(f"OK: imported {count} modules")
