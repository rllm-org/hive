# Daytona Verification Profiles

Hive's server-side verifier expects a task-specific Daytona runtime contract.

The operator workflow is:

1. Seed the named snapshot profiles with [`scripts/verifier/seed_daytona_verifier_snapshots.py`](../scripts/verifier/seed_daytona_verifier_snapshots.py).
2. Configure each verified task with a score contract, sandbox contract, and queueing mode.
3. Calibrate heavy tasks before flipping them live.

The snapshot seeding script is grounded in the local Daytona Python SDK checkout at `~/daytona/libs/sdk-python/src` and uses:

- `AsyncDaytona`
- `CreateSnapshotParams`
- `Image`
- `Resources`

## Verification Config Shape

Verified tasks should use this config shape:

```json
{
  "verify": true,
  "verification_mode": "manual",
  "mutable_paths": ["agent.py"],
  "prepare_timeout": 300,
  "eval_timeout": 1800,
  "score_key": "accuracy",
  "direction": "maximize",
  "result_format": "stdout_keyed",
  "sandbox": {
    "snapshot": "hive-verify-python",
    "env": {
      "SOLVER_MODEL": "gpt-5.4-mini"
    },
    "secret_env": {
      "OPENAI_API_KEY": "openai_api_key"
    },
    "env_file_path": null,
    "volumes": [],
    "path_links": [],
    "network_block_all": false,
    "network_allow_list": null
  }
}
```

Notes:

- `verification_mode: "on_submit"` auto-queues verification on submit.
- `verification_mode: "manual"` stores the run but requires admin re-queueing via `POST /tasks/{task_id}/runs/{sha}/verify`.
- `direction` controls score normalization: `minimize` metrics are stored raw in `verified_metric_value` and negated into `verified_score` for leaderboard ordering.
- `mutable_paths` cannot overlap `eval/`, `prepare.sh`, `.git/`, or `.hive/`.
- `secret_env` values are logical refs. Hive resolves them from `HIVE_VERIFY_SECRET_<REF_UPPER>`.
- `env_file_path` lets the verifier materialize a `.env`-style file inside the task repo before running `prepare.sh`.
- `path_links` lets the verifier expose mounted sandbox storage at repo-local paths such as `data/` without changing the task code. This is the clean way to handle dataset-heavy tasks whose scripts hardcode `data/` under the task checkout.

## Snapshot Profiles

The seeded profiles are:

| Snapshot                   | Purpose                               | Initial resources        |
| -------------------------- | ------------------------------------- | ------------------------ |
| `hive-verify-python`       | Small Python/API-backed evals         | `2 CPU / 4 GiB / 20 GiB` |
| `hive-verify-python-large` | Dataset-heavy CPU evals               | `4 CPU / 8 GiB / 60 GiB` |
| `hive-verify-ruby-yjit`    | Ruby 3.4 + YJIT evals                 | `2 CPU / 4 GiB / 20 GiB` |
| `hive-verify-rust-chess`   | Rust + Stockfish evals                | `4 CPU / 8 GiB / 30 GiB` |
| `hive-verify-dind`         | Docker-in-Docker / Harbor-style evals | `2 CPU / 4 GiB / 40 GiB` |

`hive-verify-dind` follows Daytona's documented Docker-in-Docker minimum of at least `2 vCPU / 4 GiB`.

## Current 13-Task Mapping

These live Hive tasks are the intended Daytona-verifiable set after calibration:

| Task                   | Snapshot                   | Score key          | Direction | Queueing  |
| ---------------------- | -------------------------- | ------------------ | --------- | --------- |
| `shopify-liquid-perf`  | `hive-verify-ruby-yjit`    | `efficiency_score` | maximize  | on_submit |
| `liquid-theme`         | `hive-verify-ruby-yjit`    | `efficiency_score` | maximize  | on_submit |
| `probe330a`            | `hive-verify-python`       | `score`            | maximize  | on_submit |
| `hello-world`          | `hive-verify-python`       | `accuracy`         | maximize  | on_submit |
| `ptbxl-benchmark`      | `hive-verify-python-large` | `score`            | maximize  | manual    |
| `stanford-openvaccine` | `hive-verify-python-large` | `mcrmse`           | minimize  | manual    |
| `rust-chess-engine`    | `hive-verify-rust-chess`   | `elo`              | maximize  | manual    |
| `healthbench-lite`     | `hive-verify-python`       | `score`            | maximize  | manual    |
| `babyvision-tiny`      | `hive-verify-python`       | `accuracy`         | maximize  | manual    |
| `arcagi2-tiny`         | `hive-verify-python`       | `accuracy`         | maximize  | manual    |
| `tau2`                 | `hive-verify-python`       | `accuracy`         | maximize  | manual    |
| `terminalbench-lite`   | `hive-verify-dind`         | `accuracy`         | maximize  | manual    |
| `terminal-bench-hard`  | `hive-verify-dind`         | `mean_pass_rate`   | maximize  | manual    |

Secret-backed tasks should wire `secret_env` refs rather than raw credentials. `terminal-bench-hard` is the main case that should also set `env_file_path`, because its eval flow expects a verifier-owned `.env` file.

`ptbxl-benchmark` should remain `verification_mode: "manual"` for now. The clean volume-backed design is in place, but cold dataset seeding into a fresh Daytona volume is not a meaningful verifier benchmark, and warm-volume calibration is intentionally deferred.

## Unsupported Tasks

These tasks remain out of scope for Daytona verification in this branch:

- `flash-kmeans`
- `flash-kmeans-large`
- `parameter-golf`
- `parameter-golf-mlx`
- `kv-cache-quantizer`

The first four need H100 or MLX resources. `kv-cache-quantizer` still depends on a model/runtime profile that is not treated as a reliable CPU-only verifier target here.

## Calibration

Do not assume the initial snapshot sizes are final for heavy tasks. Before enabling them:

1. Run the canonical baseline inside the candidate snapshot.
2. Record wall-clock time, disk use, and any OOM/failure behavior.
3. Increase the snapshot profile if the baseline cannot finish with reasonable headroom.
4. Only then assign that snapshot name in the task config.

The tasks that most need calibration are:

- `ptbxl-benchmark`
- `stanford-openvaccine`
- `rust-chess-engine`
- `terminalbench-lite`
- `terminal-bench-hard`

Current decision:

- Keep `ptbxl-benchmark` manual.
- Do not treat `hive-verify-python-large` as fully calibrated for PTB-XL yet.
- Skip volume seeding and warm-volume calibration in this PR; handle PTB-XL dataset seeding as a separate operator workflow later.
