#!/usr/bin/env bash
# Download FineWeb dataset + tokenizer for Parameter Golf. Run once.
set -euo pipefail

cd "$(dirname "$0")"

echo "Installing pip dependencies..."
uv pip install -r requirements.txt

echo "Downloading FineWeb dataset (80 train shards + validation)..."
python3 data/cached_challenge_fineweb.py --variant sp1024 --train-shards 80

# Verify data and tokenizer exist
DATA_DIR="data/datasets/fineweb10B_sp1024"
TOKENIZER="data/tokenizers/fineweb_1024_bpe.model"

if [ ! -d "$DATA_DIR" ]; then
    echo "ERROR: Data directory $DATA_DIR not found after download." >&2
    exit 1
fi

TRAIN_COUNT=$(ls "$DATA_DIR"/fineweb_train_*.bin 2>/dev/null | wc -l)
VAL_COUNT=$(ls "$DATA_DIR"/fineweb_val_*.bin 2>/dev/null | wc -l)
echo "Dataset: $TRAIN_COUNT train shards, $VAL_COUNT val shards"

if [ ! -f "$TOKENIZER" ]; then
    echo "ERROR: Tokenizer $TOKENIZER not found after download." >&2
    exit 1
fi

echo "Done. Data and tokenizer ready."
