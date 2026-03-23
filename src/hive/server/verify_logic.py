"""Pure verification functions for the training verification system.

These functions perform the actual checks: hash comparison, init weight
reconstruction via sandboxed subprocess, and CPU inference for score
verification with 99% confidence intervals.
"""

import asyncio
import hashlib
import json
import math
import os
import subprocess
import tempfile


def compute_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_checkpoint_hash(uploaded_bytes: bytes, committed_hash: str) -> bool:
    return compute_file_hash(uploaded_bytes) == committed_hash


# ---------------------------------------------------------------------------
# Init weight verification (sandboxed subprocess)
# ---------------------------------------------------------------------------

_INIT_SCRIPT_TEMPLATE = """
import sys, hashlib, io, torch
sys.path.insert(0, "{script_dir}")
import train_gpt as tg

torch.manual_seed({seed})
import random, numpy as np
random.seed({seed})
np.random.seed({seed})
torch.cuda.manual_seed_all({seed})

args = tg.Hyperparameters()
model = tg.GPT(
    vocab_size=args.vocab_size, num_layers=args.num_layers,
    model_dim=args.model_dim, num_heads=args.num_heads,
    num_kv_heads=args.num_kv_heads, mlp_mult=args.mlp_mult,
    tie_embeddings=args.tie_embeddings,
    tied_embed_init_std=args.tied_embed_init_std,
    logit_softcap=args.logit_softcap, rope_base=args.rope_base,
    qk_gain_init=args.qk_gain_init,
)

buf = io.BytesIO()
torch.save(model.state_dict(), buf)
h = hashlib.sha256(buf.getvalue()).hexdigest()
print(h)
"""


async def verify_init_weights(
    fork_url: str | None, seed: int, uploaded_init_path: str
) -> tuple[bool, str]:
    """Fetch agent's script from GitHub, reconstruct init weights, compare hash."""
    if not fork_url:
        return False, "no fork URL available"

    with open(uploaded_init_path, "rb") as f:
        uploaded_hash = compute_file_hash(f.read())

    with tempfile.TemporaryDirectory() as tmpdir:
        # Clone just the script from the fork (shallow, single file)
        clone_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "clone", "--depth=1", fork_url, tmpdir + "/repo"],
            capture_output=True, text=True, timeout=30,
        )
        script_path = os.path.join(tmpdir, "repo", "train_gpt.py")
        if not os.path.exists(script_path):
            return False, "train_gpt.py not found in agent's fork"

        script_dir = os.path.join(tmpdir, "repo")
        init_script = _INIT_SCRIPT_TEMPLATE.format(script_dir=script_dir, seed=seed)
        script_file = os.path.join(tmpdir, "init_check.py")
        with open(script_file, "w") as f:
            f.write(init_script)

        result = await asyncio.to_thread(
            subprocess.run,
            ["python", script_file],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
        )

        if result.returncode != 0:
            return False, f"init subprocess failed: {result.stderr[:500]}"

        expected_hash = result.stdout.strip()
        if uploaded_hash == expected_hash:
            return True, "init weights match seed"
        return False, f"init hash mismatch: uploaded={uploaded_hash[:16]}..., expected={expected_hash[:16]}..."


# ---------------------------------------------------------------------------
# Score verification via CPU inference (99% CI)
# ---------------------------------------------------------------------------

_INFERENCE_SCRIPT_TEMPLATE = """
import sys, json, torch
sys.path.insert(0, "{script_dir}")
import train_gpt as tg

args = tg.Hyperparameters()
model = tg.GPT(
    vocab_size=args.vocab_size, num_layers=args.num_layers,
    model_dim=args.model_dim, num_heads=args.num_heads,
    num_kv_heads=args.num_kv_heads, mlp_mult=args.mlp_mult,
    tie_embeddings=args.tie_embeddings,
    tied_embed_init_std=args.tied_embed_init_std,
    logit_softcap=args.logit_softcap, rope_base=args.rope_base,
    qk_gain_init=args.qk_gain_init,
)
state = torch.load("{weights_path}", map_location="cpu", weights_only=True)
model.load_state_dict(state)
model.eval().float()

import numpy as np, glob
from pathlib import Path

data_path = "{data_path}"
seq_len = args.train_seq_len

# Load data shards
files = sorted(glob.glob(data_path + "/{data_pattern}"))
tokens = []
for f in files[:3]:
    header_bytes = 256 * np.dtype("<i4").itemsize
    t = np.fromfile(f, dtype="<u2", offset=header_bytes)
    tokens.append(torch.from_numpy(t.astype(np.uint16, copy=False)))
    if sum(x.numel() for x in tokens) > {n_samples} * seq_len * 2:
        break
tokens = torch.cat(tokens)

losses = []
with torch.no_grad():
    for i in range({n_samples}):
        start = i * seq_len
        if start + seq_len + 1 > tokens.numel():
            break
        chunk = tokens[start:start + seq_len + 1].to(torch.int64)
        x, y = chunk[:-1].unsqueeze(0), chunk[1:].unsqueeze(0)
        loss = model(x, y).item()
        losses.append(loss)

print(json.dumps({{"losses": losses}}))
"""


async def verify_score(
    weights_path: str, fork_url: str | None, task_config: str | None,
    claimed_score: float, n_samples: int = 50,
) -> tuple[bool, float, float, str]:
    """Verify final score via CPU inference on val data. Returns (passed, mean, ci_halfwidth, notes)."""
    return await _run_inference_check(
        weights_path, fork_url, task_config, claimed_score, n_samples,
        data_pattern="fineweb_val_*.bin",
    )


async def verify_checkpoint_score(
    weights_path: str, fork_url: str | None, task_config: str | None,
    claimed_loss: float, n_samples: int = 50,
) -> tuple[bool, float, float, str]:
    """Verify intermediate checkpoint via CPU inference on train data."""
    return await _run_inference_check(
        weights_path, fork_url, task_config, claimed_loss, n_samples,
        data_pattern="fineweb_train_*.bin",
    )


async def _run_inference_check(
    weights_path: str, fork_url: str | None, task_config: str | None,
    claimed: float, n_samples: int, data_pattern: str,
) -> tuple[bool, float, float, str]:
    if not fork_url:
        return False, 0.0, 0.0, "no fork URL"

    # Parse data path from task config
    data_path = "./data/datasets/fineweb10B_sp1024"
    if task_config:
        try:
            cfg = json.loads(task_config)
            data_path = cfg.get("verification", {}).get("data_path", data_path)
        except (json.JSONDecodeError, AttributeError):
            pass

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_result = await asyncio.to_thread(
            subprocess.run,
            ["git", "clone", "--depth=1", fork_url, tmpdir + "/repo"],
            capture_output=True, text=True, timeout=30,
        )
        script_dir = os.path.join(tmpdir, "repo")
        if not os.path.exists(os.path.join(script_dir, "train_gpt.py")):
            return False, 0.0, 0.0, "train_gpt.py not found in fork"

        script = _INFERENCE_SCRIPT_TEMPLATE.format(
            script_dir=script_dir,
            weights_path=os.path.abspath(weights_path),
            data_path=data_path,
            data_pattern=data_pattern,
            n_samples=n_samples,
        )
        script_file = os.path.join(tmpdir, "infer.py")
        with open(script_file, "w") as f:
            f.write(script)

        result = await asyncio.to_thread(
            subprocess.run,
            ["python", script_file],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": ""},
        )

        if result.returncode != 0:
            return False, 0.0, 0.0, f"inference failed: {result.stderr[:500]}"

        try:
            output = json.loads(result.stdout.strip())
            losses = output["losses"]
        except (json.JSONDecodeError, KeyError):
            return False, 0.0, 0.0, f"bad output: {result.stdout[:200]}"

        if len(losses) < 2:
            return False, 0.0, 0.0, f"only {len(losses)} samples computed"

        mean = sum(losses) / len(losses)
        variance = sum((x - mean) ** 2 for x in losses) / (len(losses) - 1)
        se = math.sqrt(variance / len(losses))
        ci_hw = 2.576 * se  # 99% CI

        passed = abs(claimed - mean) <= ci_hw
        notes = (
            f"claimed={claimed:.6f}, measured={mean:.6f}, "
            f"CI=[{mean - ci_hw:.6f}, {mean + ci_hw:.6f}], "
            f"{'PASS' if passed else 'FAIL'}"
        )
        return passed, round(mean, 6), round(ci_hw, 6), notes
