"""Standalone verification worker for Daytona-backed eval.

Runs as a separate process from the web server:
    python -m hive.server.verifier
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import re
import shlex
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

try:
    _daytona = importlib.import_module("daytona")
except ImportError:  # pragma: no cover - exercised only when Daytona is unavailable.
    AsyncDaytona = Any  # type: ignore[assignment]
    CreateSandboxFromSnapshotParams = None  # type: ignore[assignment]
else:  # pragma: no branch
    AsyncDaytona = _daytona.AsyncDaytona  # type: ignore[attr-defined]
    CreateSandboxFromSnapshotParams = getattr(_daytona, "CreateSandboxFromSnapshotParams", None)

from .db import close_pool, get_db, init_db, init_pool, now
from .verification import (
    DEFAULT_STALE_AFTER,
    LOG_LIMIT,
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    recompute_task_stats,
    verification_config_from_raw,
)

log = logging.getLogger("hive.verifier")

POLL_INTERVAL = int(os.environ.get("VERIFY_POLL_INTERVAL", "5"))
SANDBOX_TIMEOUT = int(os.environ.get("VERIFY_SANDBOX_TIMEOUT", "120"))
AUTO_ARCHIVE_INTERVAL = int(os.environ.get("VERIFY_AUTO_ARCHIVE_INTERVAL", "60"))
AUTO_DELETE_INTERVAL = int(os.environ.get("VERIFY_AUTO_DELETE_INTERVAL", "120"))

TASK_DIR = "/home/daytona/task"
AGENT_DIR = "/home/daytona/agent"


@dataclass(slots=True)
class VerificationJob:
    id: str
    task_id: str
    repo_url: str
    fork_url: str | None
    config: Any


def parse_score(output: str) -> float | None:
    for line in reversed(output.strip().splitlines()):
        match = re.search(r"(?:score|accuracy|result)\s*[:=]\s*([\d.]+)", line, re.IGNORECASE)
        if match:
            return float(match.group(1))

    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return float(line)
        except ValueError:
            continue
    return None


async def claim_next_job() -> VerificationJob | None:
    started_at = now()
    async with get_db() as conn:
        row = await (await conn.execute(
            "WITH claimed AS ("
            "  UPDATE runs r"
            "  SET verification_status = %s, verification_started_at = %s"
            "  WHERE r.id = ("
            "    SELECT runs.id FROM runs"
            "    WHERE runs.verification_status = %s"
            "    ORDER BY runs.created_at"
            "    LIMIT 1"
            "    FOR UPDATE SKIP LOCKED"
            "  )"
            "  RETURNING r.id, r.task_id, r.fork_id"
            ")"
            " SELECT c.id, c.task_id, t.repo_url, t.config, f.fork_url"
            " FROM claimed c"
            " JOIN tasks t ON t.id = c.task_id"
            " LEFT JOIN forks f ON f.id = c.fork_id",
            (STATUS_RUNNING, started_at, STATUS_PENDING),
        )).fetchone()
    if not row:
        return None
    config = verification_config_from_raw(row["config"])
    return VerificationJob(
        id=row["id"],
        task_id=row["task_id"],
        repo_url=row["repo_url"],
        fork_url=row["fork_url"],
        config=config,
    )


async def requeue_stale_jobs() -> int:
    cutoff = now() - timedelta(seconds=DEFAULT_STALE_AFTER)
    async with get_db() as conn:
        result = await conn.execute(
            "UPDATE runs"
            " SET verification_status = %s, verification_started_at = NULL"
            " WHERE verification_status = %s"
            " AND (verification_started_at IS NULL OR verification_started_at < %s)",
            (STATUS_PENDING, STATUS_RUNNING, cutoff),
        )
        return result.rowcount or 0


async def record_result(job: VerificationJob, status: str, score: float | None, log_text: str) -> None:
    async with get_db() as conn:
        await conn.execute(
            "UPDATE runs SET verification_status = %s, verified_score = %s,"
            " verification_log = %s, verified = %s, verified_at = %s,"
            " verification_started_at = NULL"
            " WHERE id = %s",
            (
                status,
                score,
                log_text[:LOG_LIMIT],
                status == STATUS_SUCCESS,
                now() if status == STATUS_SUCCESS else None,
                job.id,
            ),
        )
        await recompute_task_stats(conn, job.task_id, job.config)


async def verify_run(daytona: AsyncDaytona, job: VerificationJob) -> None:
    sandbox = None
    try:
        if not job.config.enabled:
            await record_result(job, STATUS_ERROR, None, "Task verification is not enabled")
            return
        if not job.fork_url:
            await record_result(job, STATUS_ERROR, None, "No fork found for this run")
            return

        sandbox = await _create_sandbox(daytona)
        logs: list[str] = []

        await sandbox.git.clone(url=job.repo_url, path=TASK_DIR)
        await sandbox.git.clone(url=job.fork_url, path=AGENT_DIR, commit_id=job.id)

        for rel_path in job.config.mutable_paths:
            await _run_checked(
                sandbox,
                _overlay_command(rel_path),
                logs,
                cwd=TASK_DIR,
                timeout=job.config.prepare_timeout,
                section=f"overlay {rel_path}",
            )

        if await _path_exists(sandbox, f"{TASK_DIR}/prepare.sh"):
            await _run_checked(
                sandbox,
                "bash prepare.sh",
                logs,
                cwd=TASK_DIR,
                timeout=job.config.prepare_timeout,
                section="prepare.sh",
            )

        result = await _run_checked(
            sandbox,
            "bash eval/eval.sh",
            logs,
            cwd=TASK_DIR,
            timeout=job.config.eval_timeout,
            section="eval/eval.sh",
        )
        verified_score = parse_score(result.result or "")
        if verified_score is None:
            await record_result(job, STATUS_FAILED, None, _format_logs(logs, "Could not parse score from eval output"))
            return

        await record_result(job, STATUS_SUCCESS, verified_score, _format_logs(logs))
    except VerificationFailed as exc:
        await record_result(job, STATUS_FAILED, None, _format_logs(exc.logs, exc.message))
    except Exception as exc:
        log.exception("Verification error for run %s", job.id)
        await record_result(job, STATUS_ERROR, None, str(exc))
    finally:
        if sandbox is not None:
            try:
                await daytona.delete(sandbox, timeout=60)
            except Exception:
                log.warning("Failed to delete sandbox for run %s", job.id)


class VerificationFailed(Exception):
    def __init__(self, message: str, logs: list[str]):
        super().__init__(message)
        self.message = message
        self.logs = logs


async def _create_sandbox(daytona: AsyncDaytona):
    if CreateSandboxFromSnapshotParams is None:
        return await daytona.create(timeout=SANDBOX_TIMEOUT)
    params = CreateSandboxFromSnapshotParams(
        language="python",
        auto_stop_interval=0,
        auto_archive_interval=AUTO_ARCHIVE_INTERVAL,
        auto_delete_interval=AUTO_DELETE_INTERVAL,
    )
    return await daytona.create(params, timeout=SANDBOX_TIMEOUT)


async def _path_exists(sandbox, path: str) -> bool:
    result = await sandbox.process.exec(
        f"test -f {shlex.quote(path)}",
        timeout=10,
    )
    return result.exit_code == 0


async def _run_checked(sandbox, command: str, logs: list[str], *, cwd: str, timeout: int, section: str):
    result = await sandbox.process.exec(command, cwd=cwd, timeout=timeout)
    logs.append(_format_section(section, command, result.exit_code, result.result or ""))
    if result.exit_code != 0:
        raise VerificationFailed(f"{section} failed (exit {result.exit_code})", logs)
    return result


def _overlay_command(rel_path: str) -> str:
    src = f"{AGENT_DIR}/{rel_path}"
    dest = f"{TASK_DIR}/{rel_path}"
    parent = os.path.dirname(dest) or TASK_DIR
    return (
        f"mkdir -p {shlex.quote(parent)}"
        f" && rm -rf {shlex.quote(dest)}"
        f" && cp -R {shlex.quote(src)} {shlex.quote(dest)}"
    )


def _format_section(section: str, command: str, exit_code: int, output: str) -> str:
    return (
        f"## {section}\n"
        f"$ {command}\n"
        f"exit_code={exit_code}\n"
        f"{output.strip()}\n"
    )


def _format_logs(logs: list[str], prefix: str | None = None) -> str:
    parts = [part for part in [prefix, *logs] if part]
    return "\n\n".join(parts)


async def poll_loop(daytona: AsyncDaytona) -> None:
    while True:
        reclaimed = await requeue_stale_jobs()
        if reclaimed:
            log.warning("Re-queued %d stale verification jobs", reclaimed)

        job = await claim_next_job()
        if job is None:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        log.info("Verifying run %s (task=%s)", job.id, job.task_id)
        await verify_run(daytona, job)
        log.info("Finished run %s", job.id)


async def main() -> None:
    init_db()
    await init_pool(min_size=1, max_size=2)

    log.info("Verification worker started, polling every %ds", POLL_INTERVAL)
    try:
        async with AsyncDaytona() as daytona:
            await poll_loop(daytona)
    finally:
        await close_pool()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main())
