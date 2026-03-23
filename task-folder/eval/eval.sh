#!/usr/bin/env bash
# Evaluate train_gpt.py: run training, parse metrics, output summary.
# Always outputs a parseable summary block, even on failure.
set -uo pipefail

cd "$(dirname "$0")/.."

# --- Helper: output summary and exit ---
summary() {
    local val_bpb="${1:-ERROR}"
    local artifact_bytes="${2:-0}"
    local line_count="${3:-0}"
    local valid="${4:-false}"
    echo "---"
    printf "val_bpb:          %s\n" "$val_bpb"
    printf "artifact_bytes:   %s\n" "$artifact_bytes"
    printf "line_count:       %s\n" "$line_count"
    printf "valid:            %s\n" "$valid"
}

# --- Pre-flight checks ---

# 1. Check train_gpt.py exists
if [ ! -f "train_gpt.py" ]; then
    echo "ERROR: train_gpt.py not found." >&2
    summary "ERROR" "0" "0" "false"
    exit 0
fi

# 2. Check line count
LINE_COUNT=$(wc -l < train_gpt.py)
if [ "$LINE_COUNT" -gt 1500 ]; then
    echo "ERROR: train_gpt.py has $LINE_COUNT lines (limit: 1500)." >&2
    summary "ERROR" "0" "$LINE_COUNT" "false"
    exit 0
fi

# 3. Check CUDA available
if ! python3 -c "import torch; assert torch.cuda.is_available(), 'No CUDA'" 2>/dev/null; then
    echo "ERROR: CUDA not available." >&2
    summary "ERROR" "0" "$LINE_COUNT" "false"
    exit 0
fi

# 4. Check data and tokenizer exist
DATA_DIR="data/datasets/fineweb10B_sp1024"
TOKENIZER="data/tokenizers/fineweb_1024_bpe.model"

if [ ! -d "$DATA_DIR" ]; then
    echo "ERROR: Data directory $DATA_DIR not found. Run: bash prepare.sh" >&2
    summary "ERROR" "0" "$LINE_COUNT" "false"
    exit 0
fi

if [ ! -f "$TOKENIZER" ]; then
    echo "ERROR: Tokenizer $TOKENIZER not found. Run: bash prepare.sh" >&2
    summary "ERROR" "0" "$LINE_COUNT" "false"
    exit 0
fi

# --- Run training ---

TMPLOG=$(mktemp)
trap 'rm -f "$TMPLOG"' EXIT

NUM_GPUS=8
echo "Running: torchrun --standalone --nproc_per_node=$NUM_GPUS train_gpt.py" >&2

TRAIN_EXIT=0
torchrun --standalone --nproc_per_node="$NUM_GPUS" train_gpt.py 2>&1 | tee "$TMPLOG" >&2 || TRAIN_EXIT=$?

if [ "$TRAIN_EXIT" -ne 0 ]; then
    echo "ERROR: Training exited with code $TRAIN_EXIT." >&2
    summary "ERROR" "0" "$LINE_COUNT" "false"
    exit 0
fi

# --- Parse results ---

# Extract val_bpb from final_int8_zlib_roundtrip_exact line
VAL_BPB=$(grep -oP 'final_int8_zlib_roundtrip_exact.*val_bpb:\K[0-9]+\.[0-9]+' "$TMPLOG" | tail -1)
if [ -z "$VAL_BPB" ]; then
    echo "ERROR: Could not parse val_bpb from training output." >&2
    summary "ERROR" "0" "$LINE_COUNT" "false"
    exit 0
fi

# Extract artifact bytes from "Total submission size int8+zlib:" line
ARTIFACT_BYTES=$(grep -oP 'Total submission size int8\+zlib: \K[0-9]+' "$TMPLOG" | tail -1)
if [ -z "$ARTIFACT_BYTES" ]; then
    echo "ERROR: Could not parse artifact size from training output." >&2
    summary "$VAL_BPB" "0" "$LINE_COUNT" "false"
    exit 0
fi

# Check artifact size limit
VALID="true"
if [ "$ARTIFACT_BYTES" -gt 16000000 ]; then
    echo "WARNING: Artifact size $ARTIFACT_BYTES exceeds 16,000,000 byte limit." >&2
    VALID="false"
fi

summary "$VAL_BPB" "$ARTIFACT_BYTES" "$LINE_COUNT" "$VALID"
