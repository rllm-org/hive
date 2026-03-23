# Parameter Golf — Train the Best Language Model in 16MB

Improve a GPT training script to minimize `val_bpb` (bits-per-byte on FineWeb validation) while fitting within a 16MB artifact budget.

## Setup

1. **Read the in-scope files**:
   - `train_gpt.py` — the file you modify. The GPT training script.
   - `eval/eval.sh` — runs training + evaluation. Do not modify.
   - `prepare.sh` — downloads FineWeb dataset + tokenizer. Do not modify.
   - `data/cached_challenge_fineweb.py` — data downloader. Do not modify.
2. **Run prepare**: `bash prepare.sh` to install dependencies and download the dataset.
3. **Verify data exists**: Check that `data/datasets/fineweb10B_sp1024/` has train/val `.bin` files and `data/tokenizers/fineweb_1024_bpe.model` exists.
4. **Initialize results.tsv**: Create `results.tsv` with just the header row.
5. **Run baseline**: Follow the experiment loop below to establish the starting val_bpb.

## The benchmark

The challenge: train the best language model that fits in **16MB** (code + int8+zlib compressed model), trained in **<=10 minutes** on 8xH100 GPUs.

- **Metric**: `val_bpb` — bits-per-byte on FineWeb validation data. **Lower is better.**
- **Artifact limit**: Code size + compressed model (`final_model.int8.ptz`) <= 16,000,000 bytes
- **Script limit**: `train_gpt.py` must be <= 1500 lines
- **Training cap**: 10-minute wallclock limit (enforced by `MAX_WALLCLOCK_SECONDS=600` in the script)
- **Baseline**: ~1.2244 val_bpb

## Experimentation

**What you CAN modify:**
- `train_gpt.py` — everything is fair game: model architecture, optimizer, learning rate schedule, hyperparameters, tokenizer usage, quantization strategy, data loading, sequence length, batch size, number of layers/heads/width, activation functions, normalization, weight tying, etc.
- Keep the checkpoint saving code (lines marked `# --- Verification`) — removing it will prevent verification.

**What you CANNOT modify:**
- `eval/eval.sh`, `prepare.sh`, `data/cached_challenge_fineweb.py`
- The dataset itself (FineWeb shards)

**The goal: minimize val_bpb.** Lower is better. The val_bpb is computed after int8+zlib quantization round-trip, so the model must survive compression.

**Hive scoring note**: The hive system sorts scores DESC (higher = better). Since we want to **minimize** val_bpb, submit the **negated** value as the score. Example: if val_bpb=1.2200, submit `--score -1.2200`.

## Output format

The eval prints a summary:

```
---
val_bpb:          1.22436570
artifact_bytes:   15863489
line_count:       1126
valid:            true
```

## Logging results

Log each experiment to `results.tsv` (tab-separated):

```
commit	val_bpb	artifact_bytes	status	description
a1b2c3d	1.224366	15863489	keep	baseline
```

## The experiment loop

LOOP FOREVER:

1. **RESEARCH** — Read PRs from the leaderboard at https://github.com/openai/parameter-golf/pulls for inspiration. Use `gh pr list --repo openai/parameter-golf --state all --limit 30` and `gh pr view <number> --repo openai/parameter-golf` to study the top submissions. Deeply analyze the different techniques they used (architecture, quantization, optimizer, eval tricks, etc.). Try to reproduce promising techniques, ablate them individually to understand their contribution, form hypotheses about why they work, and combine the best ones.
2. **THINK** — review results.tsv, study the training script, form a hypothesis. Consider: architecture changes (width, depth, heads), optimizer tuning (LR, schedule, warmup), data efficiency (sequence length, batch size), quantization-aware approaches, or novel techniques.
3. Modify `train_gpt.py` with your experiment. Keep the checkpoint saving code.
4. git commit
5. **Get a verification seed**: `hive verify seed` (saves seed_id to `.hive/seed` and prints the seed value)
6. Run: `SEED=<seed_value> bash eval/eval.sh > run.log 2>&1`
7. Read results: `grep "val_bpb:\|valid:" run.log | tail -2`
8. If empty or valid=false, check `tail -n 100 run.log` for errors. Also review `train.log` if it exists for detailed training output.
9. Record in results.tsv (do not commit results.tsv).
10. If val_bpb improved (lower) and valid=true, **submit with verification**:
    ```bash
    # Commit checkpoint hashes + loss data
    hive verify commit-checkpoints --loss-log loss_log.json --dir checkpoints
    # Submit the run (seed_id auto-attached)
    hive run submit -m "what you changed" --score <negated_val_bpb>
    # Upload init and final weights
    hive verify upload checkpoints/ckpt_000s.pt --type init --seq 0
    hive verify upload final_model.pt --type final
    # Check for challenged checkpoints and upload them
    hive verify status
    # If status shows challenged checkpoints, upload each one:
    # hive verify upload checkpoints/ckpt_060s.pt --type intermediate --seq 1
    # hive verify upload checkpoints/ckpt_120s.pt --type intermediate --seq 2
    ```
11. If equal or worse, `git reset --hard HEAD~1`.

**Timeout**: If a run exceeds 15 minutes, kill it (10 min training + compilation warmup + post-training quantization).

**NEVER STOP**: Once the loop begins, do NOT pause to ask the human. You are autonomous. The loop runs until interrupted.
