#!/usr/bin/env bash
# Stop hook: runs ALL CI checks before Claude completes.
# Exit 2 + stderr = block completion and surface errors to the agent.
set -uo pipefail

INPUT=$(cat)

if [ "$(echo "$INPUT" | jq -r '.stop_hook_active')" = "true" ]; then
  exit 0
fi

DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$DIR"

out=$(bash ci/run_all.sh 2>&1)
rc=$?

if [ $rc -ne 0 ]; then
  echo "CI checks failed. Fix these before completing:" >&2
  echo "$out" >&2
  exit 0
fi

exit 0
