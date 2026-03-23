import hashlib
import json
from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from hive.cli.formatting import ok
from hive.cli.helpers import _api, _task_id, _json_out
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag

verify_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@verify_app.callback()
def verify_callback(task_opt: TaskOpt = None):
    """Training verification — request seeds, commit checkpoints, upload weights."""
    _set_task(task_opt)


def _seed_file() -> Path:
    return Path.cwd() / ".hive" / "seed"


def _read_seed_id() -> int:
    sf = _seed_file()
    if not sf.exists():
        raise click.ClickException("No active seed. Run `hive verify seed` first.")
    return int(sf.read_text().strip())


@verify_app.command("seed")
def verify_seed(as_json: JsonFlag = False, task_opt: TaskOpt = None):
    """Request a verification seed from the server."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("POST", f"/tasks/{task_id}/verify/seed")
    # Save seed_id locally
    sf = _seed_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(str(data["seed_id"]))
    if as_json:
        _json_out(data)
    else:
        ok(f"Seed: {data['seed']}  (seed_id={data['seed_id']})")
        click.echo(f"  Deadline: {data['deadline']}")
        click.echo(f"  Saved seed_id to {sf}")
        click.echo(f"\n  Use this seed to init your model:")
        click.echo(f"    torch.manual_seed({data['seed']})")


@verify_app.command("commit-checkpoints")
def verify_commit_checkpoints(
    loss_log: Annotated[str, typer.Option("--loss-log", help="Path to loss_log.json from training")] = "loss_log.json",
    checkpoints_dir: Annotated[str, typer.Option("--dir", help="Directory containing checkpoint .pt files")] = "checkpoints",
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Commit all checkpoint hashes + training losses to the server."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    seed_id = _read_seed_id()
    ckpt_dir = Path(checkpoints_dir)

    # Load loss log
    losses_by_step = {}
    loss_log_path = Path(loss_log)
    if loss_log_path.exists():
        with open(loss_log_path) as f:
            for entry in json.load(f):
                losses_by_step[entry.get("step")] = entry.get("train_loss")

    # Find and hash all checkpoint files
    ckpt_files = sorted(ckpt_dir.glob("ckpt_*.pt"))
    if not ckpt_files:
        raise click.ClickException(f"No checkpoint files found in {ckpt_dir}/")

    checkpoints = []
    for i, path in enumerate(ckpt_files):
        with open(path, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        # Try to extract sequence num from filename (ckpt_000s.pt → 0, ckpt_060s.pt → 1)
        name = path.stem  # e.g. "ckpt_060s" or "ckpt_final"
        if name == "ckpt_final":
            continue  # final is uploaded separately, not committed as a checkpoint
        checkpoints.append({
            "sequence_num": i,
            "weight_hash": h,
            "reported_train_loss": losses_by_step.get(i),
        })

    payload = {"seed_id": seed_id, "checkpoints": checkpoints}
    data = _api("POST", f"/tasks/{task_id}/verify/checkpoints", json=payload)
    if as_json:
        _json_out(data)
    else:
        ok(f"Committed {data['committed']} checkpoints for seed_id={seed_id}")


@verify_app.command("upload")
def verify_upload(
    path: Annotated[str, typer.Argument(help="Path to checkpoint .pt file")],
    checkpoint_type: Annotated[str, typer.Option("--type", help="init, intermediate, or final")],
    seq: Annotated[Optional[int], typer.Option("--seq", help="Checkpoint sequence number")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Upload checkpoint weights to the server for verification."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    seed_id = _read_seed_id()

    fpath = Path(path)
    if not fpath.exists():
        raise click.ClickException(f"File not found: {path}")

    files = {"weights": (fpath.name, open(fpath, "rb"), "application/octet-stream")}
    form_data = {"seed_id": str(seed_id), "checkpoint_type": checkpoint_type}
    if seq is not None:
        form_data["sequence_num"] = str(seq)

    data = _api("POST", f"/tasks/{task_id}/verify/upload", files=files, data=form_data)
    if as_json:
        _json_out(data)
    else:
        size_mb = data["file_size"] / 1024 / 1024
        ok(f"Uploaded {checkpoint_type} ({size_mb:.1f} MB)  hash={data['file_hash'][:16]}...")


@verify_app.command("status")
def verify_status(as_json: JsonFlag = False, task_opt: TaskOpt = None):
    """Check verification status for the current seed."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    seed_id = _read_seed_id()
    data = _api("GET", f"/tasks/{task_id}/verify/{seed_id}")
    if as_json:
        _json_out(data)
    else:
        click.echo(f"Seed {data['seed_id']}  status={data['status']}")
        click.echo(f"  Checkpoints committed: {data['checkpoints_committed']}")
        click.echo(f"  Uploads received: {', '.join(data['uploads_received']) or 'none'}")
        if data.get("uploads_needed"):
            click.echo(f"  Uploads needed: {', '.join(data['uploads_needed'])}")
        if data.get("challenged_checkpoints"):
            click.echo(f"  Challenged checkpoints: {data['challenged_checkpoints']}")
        if data.get("verification"):
            v = data["verification"]
            click.echo(f"  Verification: init={v.get('init_check')} hash={v.get('hash_check')} "
                       f"score={v.get('score_check')} checkpoint={v.get('checkpoint_score_check')}")
