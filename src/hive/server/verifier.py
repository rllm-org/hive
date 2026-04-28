"""Run trusted server_eval against submitted artifacts (local subprocess; Daytona later)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from .db import get_db, now
from .verify_config import is_verify_enabled, parse_json_config

log = logging.getLogger(__name__)


def _eval_root_from_volume_id(volume_id: str) -> Path:
    if volume_id.startswith("local:"):
        return Path(volume_id[6:]).resolve()
    raise ValueError(f"unsupported volume_id (only local: paths in this build): {volume_id!r}")


def _parse_metrics_json(stdout: str, score_key: str) -> dict[str, Any] | None:
    for line in reversed([l.strip() for l in stdout.splitlines() if l.strip()]):
        if line.startswith("{") and line.endswith("}"):
            try:
                d = json.loads(line)
                if isinstance(d, dict) and score_key in d:
                    return d
            except json.JSONDecodeError:
                continue
    return None


def run_server_eval_sync(
    eval_extract_root: Path,
    artifact_abs_paths: dict[str, Path],
    command: str | list[str],
    score_key: str,
    direction: str,
    timeout: int = 300,
) -> dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="hive_verify_"))
    try:
        eval_root = work / "eval"
        shutil.copytree(eval_extract_root, eval_root)
        art_root = work / "artifacts"
        art_root.mkdir()
        for rel, src in artifact_abs_paths.items():
            dest = art_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        shell = isinstance(command, str)
        proc = subprocess.run(
            command,
            cwd=str(eval_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
        )
        out = (proc.stdout or "") + ((proc.stderr or "") and f"\n{proc.stderr}" or "")
        if proc.returncode != 0:
            return {"ok": False, "error": f"server_eval exited {proc.returncode}", "logs": out}
        text = proc.stdout or proc.stderr or ""
        metrics = _parse_metrics_json(text, score_key)
        if metrics is None:
            return {"ok": False, "error": "could not parse JSON metrics line from server_eval output", "logs": out}
        raw = float(metrics[score_key])
        verified_score = raw if direction == "maximize" else -raw
        return {
            "ok": True,
            "verified_score": verified_score,
            "metric_value": raw,
            "metrics": metrics,
            "logs": out,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def verify_run_background(run_id: str, task_id: str, attempt_id: str) -> None:
    try:
        async with get_db() as conn:
            task_row = await (await conn.execute("SELECT config FROM tasks WHERE id = %s", (task_id,))).fetchone()
            if not task_row:
                return
            cfg = parse_json_config(task_row.get("config"))
            if not is_verify_enabled(cfg):
                return
            se = cfg.get("server_eval") or {}
            volume_id = se.get("volume_id")
            if not volume_id:
                await conn.execute(
                    "UPDATE runs SET verification_status = %s, verification_error = %s WHERE id = %s",
                    ("error", "task missing server_eval.volume_id", run_id),
                )
                await conn.execute(
                    "UPDATE verification_attempts SET status = %s, error = %s, finished_at = %s WHERE id = %s",
                    ("error", "task missing server_eval.volume_id", now(), attempt_id),
                )
                return
            extract_root = _eval_root_from_volume_id(volume_id)
            if not extract_root.is_dir():
                await conn.execute(
                    "UPDATE runs SET verification_status = %s, verification_error = %s WHERE id = %s",
                    ("error", f"eval bundle path not found: {extract_root}", run_id),
                )
                await conn.execute(
                    "UPDATE verification_attempts SET status = %s, error = %s, finished_at = %s WHERE id = %s",
                    ("error", f"eval bundle path not found: {extract_root}", now(), attempt_id),
                )
                return
            rows = await (await conn.execute(
                "SELECT rel_path, storage_path FROM run_artifacts WHERE run_id = %s ORDER BY rel_path",
                (run_id,),
            )).fetchall()
            required = (cfg.get("artifact") or {}).get("required_paths") or []
            paths_map = {r["rel_path"]: Path(r["storage_path"]) for r in rows}
            missing = [p for p in required if p not in paths_map]
            if missing:
                await conn.execute(
                    "UPDATE runs SET verification_status = %s, verification_error = %s WHERE id = %s",
                    ("failed", f"missing artifacts: {missing}", run_id),
                )
                await conn.execute(
                    "UPDATE verification_attempts SET status = %s, error = %s, finished_at = %s WHERE id = %s",
                    ("failed", f"missing artifacts: {missing}", now(), attempt_id),
                )
                return
            command = se["command"]
            score_key = se["score_key"]
            direction = se.get("direction", "maximize")
            sandbox = cfg.get("sandbox") or {}
            timeout = int(sandbox.get("timeout_seconds") or os.environ.get("VERIFY_EVAL_TIMEOUT", "300"))
            await conn.execute(
                "UPDATE verification_attempts SET status = %s, started_at = %s WHERE id = %s",
                ("running", now(), attempt_id),
            )

        result = await asyncio.to_thread(
            run_server_eval_sync,
            extract_root,
            paths_map,
            command,
            score_key,
            direction,
            timeout,
        )
        finished = now()
        async with get_db() as conn:
            if result.get("ok"):
                vs = result["verified_score"]
                mv = result["metric_value"]
                await conn.execute(
                    "UPDATE runs SET verified = TRUE, verified_score = %s, verified_metric_key = %s,"
                    " verified_metric_value = %s, verification_status = %s, verification_error = NULL,"
                    " verified_at = %s WHERE id = %s",
                    (vs, score_key, mv, "success", finished, run_id),
                )
                await conn.execute(
                    "UPDATE verification_attempts SET status = %s, metrics = %s, logs = %s, finished_at = %s"
                    " WHERE id = %s",
                    ("success", Json(result.get("metrics") or {}), result.get("logs", "")[:20000], finished, attempt_id),
                )
                await _recompute_task_best_verified(conn, task_id, cfg)
            else:
                err = result.get("error", "unknown")
                await conn.execute(
                    "UPDATE runs SET verification_status = %s, verification_error = %s WHERE id = %s",
                    ("failed", err[:2000], run_id),
                )
                await conn.execute(
                    "UPDATE verification_attempts SET status = %s, error = %s, logs = %s, finished_at = %s"
                    " WHERE id = %s",
                    ("failed", err[:2000], (result.get("logs") or "")[:20000], finished, attempt_id),
                )
    except Exception as e:
        log.exception("verify_run_background failed")
        finished = now()
        async with get_db() as conn:
            await conn.execute(
                "UPDATE runs SET verification_status = %s, verification_error = %s WHERE id = %s",
                ("error", str(e)[:2000], run_id),
            )
            await conn.execute(
                "UPDATE verification_attempts SET status = %s, error = %s, finished_at = %s WHERE id = %s",
                ("error", str(e)[:2000], finished, attempt_id),
            )


async def _recompute_task_best_verified(conn, task_id: str, cfg: dict) -> None:
    if not is_verify_enabled(cfg):
        return
    row = await (await conn.execute(
        "SELECT MAX(verified_score) AS v FROM runs WHERE task_id = %s AND verification_status = %s AND valid IS NOT FALSE",
        (task_id, "success"),
    )).fetchone()
    best = row["v"] if row else None
    if best is not None:
        await conn.execute("UPDATE tasks SET best_score = %s WHERE id = %s", (best, task_id))
