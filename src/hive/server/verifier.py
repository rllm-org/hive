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
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

try:
    try:
        _daytona = importlib.import_module("daytona_sdk")
    except ImportError:
        _daytona = importlib.import_module("daytona")
except ImportError:  # pragma: no cover - exercised only when Daytona is unavailable.
    AsyncDaytona = Any  # type: ignore[assignment]
    CreateSandboxFromSnapshotParams = None  # type: ignore[assignment]
    VolumeMount = None  # type: ignore[assignment]
else:  # pragma: no branch
    AsyncDaytona = _daytona.AsyncDaytona  # type: ignore[attr-defined]
    CreateSandboxFromSnapshotParams = getattr(_daytona, "CreateSandboxFromSnapshotParams", None)
    VolumeMount = getattr(_daytona, "VolumeMount", None)

from .db import close_pool, get_db, init_db, init_pool, now
from .verification import (
    DEFAULT_STALE_AFTER,
    LOG_LIMIT,
    STATUS_ERROR,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    VerificationConfig,
    normalize_verified_score,
    recompute_task_stats,
    verification_config_from_raw,
)

log = logging.getLogger("hive.verifier")

POLL_INTERVAL = int(os.environ.get("VERIFY_POLL_INTERVAL", "5"))
SANDBOX_TIMEOUT = int(os.environ.get("VERIFY_SANDBOX_TIMEOUT", "120"))
VOLUME_TIMEOUT = int(os.environ.get("VERIFY_VOLUME_TIMEOUT", "120"))
AUTO_ARCHIVE_INTERVAL = int(os.environ.get("VERIFY_AUTO_ARCHIVE_INTERVAL", "60"))
AUTO_DELETE_INTERVAL = int(os.environ.get("VERIFY_AUTO_DELETE_INTERVAL", "120"))
MAX_CONCURRENT_JOBS = max(1, int(os.environ.get("VERIFY_MAX_CONCURRENT_JOBS", "3")))
DB_POOL_MIN = int(os.environ.get("VERIFY_DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.environ.get("VERIFY_DB_POOL_MAX", "0"))  # 0 = auto-size
SANDBOX_MAX_RETRIES = int(os.environ.get("VERIFY_SANDBOX_MAX_RETRIES", "3"))
SANDBOX_RETRY_BACKOFF = int(os.environ.get("VERIFY_SANDBOX_RETRY_BACKOFF", "30"))

TASK_DIR = "/home/daytona/task"
AGENT_DIR = "/home/daytona/agent"


@dataclass(slots=True)
class VerificationJob:
    """All metadata needed to verify a queued run."""

    id: str
    task_id: str
    repo_url: str
    task_repo_sha: str | None
    fork_url: str | None
    config: VerificationConfig | None


FLOAT_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def parse_score(
    output: str,
    *,
    score_key: str | None = None,
    result_format: str = "stdout_keyed",
) -> float | None:
    """Extract a raw metric from eval output using the configured contract."""

    if result_format == "stdout_last_float":
        return _parse_last_float(output)

    return _parse_keyed_score(output, score_key)


async def claim_next_job() -> VerificationJob | None:
    """Atomically claim the oldest pending verification job."""

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
            "  RETURNING r.id, r.task_id, r.fork_id, r.task_repo_sha, r.verification_config"
            ")"
            " SELECT c.id, c.task_id, t.repo_url,"
            "        c.task_repo_sha, c.verification_config,"
            "        f.fork_url"
            " FROM claimed c"
            " JOIN tasks t ON t.id = c.task_id"
            " LEFT JOIN forks f ON f.id = c.fork_id",
            (STATUS_RUNNING, started_at, STATUS_PENDING),
        )).fetchone()
    if not row:
        return None
    config = None
    if row["verification_config"] is not None:
        config = verification_config_from_raw(row["verification_config"])
    return VerificationJob(
        id=row["id"],
        task_id=row["task_id"],
        repo_url=row["repo_url"],
        task_repo_sha=row["task_repo_sha"],
        fork_url=row["fork_url"],
        config=config,
    )


async def requeue_stale_jobs() -> int:
    """Move stuck running jobs back to pending so another worker can retry them."""

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


async def record_result(
    job: VerificationJob,
    status: str,
    metric_value: float | None,
    verified_score: float | None,
    log_text: str,
) -> None:
    """Persist the verifier outcome and recompute task stats."""

    async with get_db() as conn:
        await conn.execute(
            "UPDATE runs SET verification_status = %s, verified_score = %s,"
            " verified_metric_key = %s, verified_metric_value = %s,"
            " verification_log = %s, verified = %s, verified_at = %s,"
            " verification_started_at = NULL"
            " WHERE id = %s",
            (
                status,
                verified_score,
                job.config.score_key if status == STATUS_SUCCESS and job.config is not None else None,
                metric_value,
                log_text[:LOG_LIMIT],
                status == STATUS_SUCCESS,
                now() if status == STATUS_SUCCESS else None,
                job.id,
            ),
        )
        if job.config is not None:
            await recompute_task_stats(conn, job.task_id, job.config)


async def verify_run(daytona: AsyncDaytona, job: VerificationJob) -> None:
    """Run canonical prepare/eval in Daytona and store the verification result."""

    sandbox = None
    try:
        if job.config is None:
            await record_result(job, STATUS_ERROR, None, None, "No pinned verification config found for this run")
            return

        if not job.config.enabled:
            await record_result(job, STATUS_ERROR, None, None, "Task verification is not enabled")
            return
        if not job.fork_url:
            await record_result(job, STATUS_ERROR, None, None, "No fork found for this run")
            return
        if not job.task_repo_sha:
            await record_result(job, STATUS_ERROR, None, None, "No pinned task repo SHA found for this run")
            return

        sandbox = await _create_sandbox_with_retry(daytona, job)
        logs: list[str] = []

        # Clone the trusted task repo, then overlay only the agent-owned paths before running scripts.
        await sandbox.git.clone(url=job.repo_url, path=TASK_DIR, commit_id=job.task_repo_sha)
        # Clone agent fork: fetch all refs so non-default-branch commits are available.
        await sandbox.git.clone(url=job.fork_url, path=AGENT_DIR)
        await _run_checked(
            sandbox,
            f"git fetch origin '+refs/heads/*:refs/remotes/origin/*' && git checkout {shlex.quote(job.id)}",
            logs,
            cwd=AGENT_DIR,
            timeout=job.config.prepare_timeout,
            section="checkout agent commit",
        )

        for rel_path in job.config.mutable_paths:
            await _run_checked(
                sandbox,
                _overlay_command(rel_path),
                logs,
                cwd=TASK_DIR,
                timeout=job.config.prepare_timeout,
                section=f"overlay {rel_path}",
            )

        await _materialize_path_links(sandbox, job.config, logs)
        await _write_env_file_if_needed(sandbox, job.config, logs)

        # Run optional sandbox setup commands (e.g. install runtime dependencies).
        setup_cmds = job.config.sandbox.env and dict(job.config.sandbox.env).get("HIVE_SETUP_CMD")
        if setup_cmds:
            await _run_checked(
                sandbox,
                setup_cmds,
                logs,
                cwd=TASK_DIR,
                timeout=job.config.eval_timeout,
                section="sandbox setup",
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
        metric_value = parse_score(
            result.result or "",
            score_key=job.config.score_key,
            result_format=job.config.result_format,
        )
        if metric_value is None:
            await record_result(job, STATUS_FAILED, None, None, _format_logs(logs, "Could not parse score from eval output"))
            return

        verified_score = normalize_verified_score(metric_value, job.config)
        await record_result(job, STATUS_SUCCESS, metric_value, verified_score, _format_logs(logs))
    except VerificationFailed as exc:
        await record_result(job, STATUS_FAILED, None, None, _format_logs(exc.logs, exc.message))
    except Exception as exc:
        log.exception("Verification error for run %s", job.id)
        await record_result(job, STATUS_ERROR, None, None, str(exc))
    finally:
        if sandbox is not None:
            try:
                await daytona.delete(sandbox, timeout=60)
            except Exception:
                try:
                    await daytona.stop(sandbox, timeout=30)
                except Exception:
                    pass
                log.warning("Failed to delete sandbox for run %s (stopped instead)", job.id)


class VerificationFailed(Exception):
    """Raised when a sandbox command fails and logs should be preserved."""

    def __init__(self, message: str, logs: list[str]):
        super().__init__(message)
        self.message = message
        self.logs = logs


async def _create_sandbox_with_retry(daytona: AsyncDaytona, job: VerificationJob) -> Any:
    """Create a sandbox, retrying indefinitely with capped backoff on transient failures."""

    attempt = 0
    while True:
        attempt += 1
        try:
            return await _create_sandbox(daytona, job.config)
        except Exception as exc:
            delay = min(SANDBOX_RETRY_BACKOFF * attempt, SANDBOX_RETRY_BACKOFF * SANDBOX_MAX_RETRIES)
            log.warning(
                "sandbox creation failed for run %s (attempt %d), retrying in %ds: %s",
                job.id, attempt, delay, exc,
            )
            await asyncio.sleep(delay)


async def _create_sandbox(daytona: AsyncDaytona, config: VerificationConfig) -> Any:
    """Create a Daytona sandbox using the task's pinned runtime contract."""

    if CreateSandboxFromSnapshotParams is None:
        raise RuntimeError("Installed Daytona SDK does not expose CreateSandboxFromSnapshotParams")

    env_vars = _resolve_env_vars(config)
    volumes = await _resolve_volume_mounts(daytona, config)
    params = CreateSandboxFromSnapshotParams(
        snapshot=config.sandbox.snapshot,
        auto_stop_interval=0,
        auto_archive_interval=AUTO_ARCHIVE_INTERVAL,
        auto_delete_interval=AUTO_DELETE_INTERVAL,
        env_vars=env_vars or None,
        volumes=volumes or None,
        network_block_all=config.sandbox.network_block_all,
        network_allow_list=config.sandbox.network_allow_list,
    )
    return await daytona.create(params, timeout=SANDBOX_TIMEOUT)


def _resolve_env_vars(config: VerificationConfig) -> dict[str, str]:
    """Resolve plain and secret-backed env vars for the Daytona sandbox."""

    env_vars = dict(config.sandbox.env)
    for env_name, ref in config.sandbox.secret_env:
        secret_name = f"HIVE_VERIFY_SECRET_{ref.upper()}"
        secret_value = os.environ.get(secret_name)
        if secret_value is None:
            raise RuntimeError(f"Missing verifier secret env {secret_name}")
        env_vars[env_name] = secret_value
    return env_vars


async def _resolve_volume_mounts(daytona: AsyncDaytona, config: VerificationConfig) -> list[Any]:
    """Resolve named Daytona volumes into sandbox mounts."""

    if not config.sandbox.volumes:
        return []
    if VolumeMount is None:
        raise RuntimeError("Installed Daytona SDK does not expose VolumeMount")

    mounts: list[Any] = []
    for volume_config in config.sandbox.volumes:
        await daytona.volume.get(volume_config.name, create=True)
        volume = await _wait_for_volume_ready(daytona, volume_config.name, timeout=VOLUME_TIMEOUT)
        mounts.append(
            VolumeMount(
                volume_id=volume.id,
                mount_path=volume_config.mount_path,
                subpath=volume_config.subpath,
            )
        )
    return mounts


async def _wait_for_volume_ready(daytona: AsyncDaytona, volume_name: str, *, timeout: int) -> Any:
    """Wait until a Daytona volume becomes mountable."""

    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        volume = await daytona.volume.get(volume_name)
        if str(volume.state).endswith("READY"):
            return volume
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError(f"Timed out waiting for Daytona volume {volume_name} to become ready")
        await asyncio.sleep(1)


async def _materialize_path_links(
    sandbox: Any,
    config: VerificationConfig,
    logs: list[str],
) -> None:
    """Expose mounted sandbox paths at task-local locations via symlinks."""

    for path_link in config.sandbox.path_links:
        target = f"{TASK_DIR}/{path_link.target_path}"
        parent = os.path.dirname(target)

        if await _path_exists(sandbox, target):
            raise VerificationFailed(f"Runtime link target already exists: {path_link.target_path}", logs)

        if parent and parent != TASK_DIR:
            await _run_checked(
                sandbox,
                f"mkdir -p {shlex.quote(parent)}",
                logs,
                cwd=TASK_DIR,
                timeout=config.prepare_timeout,
                section=f"mkdir {os.path.dirname(path_link.target_path)}",
            )

        await _run_checked(
            sandbox,
            f"ln -s {shlex.quote(path_link.source_path)} {shlex.quote(target)}",
            logs,
            cwd=TASK_DIR,
            timeout=config.prepare_timeout,
            section=f"link {path_link.target_path}",
        )


async def _write_env_file_if_needed(
    sandbox: Any,
    config: VerificationConfig,
    logs: list[str],
) -> None:
    """Materialize a verifier-owned env file inside the canonical task checkout."""

    if not config.sandbox.env_file_path:
        return

    env_vars = _resolve_env_vars(config)
    env_lines = "\n".join(f"{key}={value}" for key, value in env_vars.items()) + "\n"
    path = f"{TASK_DIR}/{config.sandbox.env_file_path}"
    parent = os.path.dirname(path)

    # Create the parent directory in-band so the verifier log still shows the
    # filesystem setup step, but keep secret values out of the shell command.
    if parent and parent != TASK_DIR:
        await _run_checked(
            sandbox,
            f"mkdir -p {shlex.quote(parent)}",
            logs,
            cwd=TASK_DIR,
            timeout=config.prepare_timeout,
            section=f"mkdir {os.path.dirname(config.sandbox.env_file_path)}",
        )

    try:
        await sandbox.fs.upload_file(env_lines.encode("utf-8"), path, timeout=config.prepare_timeout)
    except Exception as exc:
        logs.append(_format_section(f"write {config.sandbox.env_file_path}", "[daytona.fs.upload_file]", 1, str(exc)))
        raise VerificationFailed(f"write {config.sandbox.env_file_path} failed", logs) from exc

    logs.append(_format_section(f"write {config.sandbox.env_file_path}", "[daytona.fs.upload_file]", 0, "uploaded"))
    await _run_checked(
        sandbox,
        f"chmod 600 {shlex.quote(path)}",
        logs,
        cwd=TASK_DIR,
        timeout=config.prepare_timeout,
        section=f"chmod {config.sandbox.env_file_path}",
    )


async def _path_exists(sandbox: Any, path: str) -> bool:
    """Check whether a file exists inside the sandbox."""

    result = await sandbox.process.exec(
        f"test -f {shlex.quote(path)}",
        timeout=10,
    )
    return result.exit_code == 0


async def _run_checked(
    sandbox: Any,
    command: str,
    logs: list[str],
    *,
    cwd: str,
    timeout: int,
    section: str,
) -> Any:
    """Execute a sandbox command, appending logs and raising on non-zero exit."""

    result = await sandbox.process.exec(command, cwd=cwd, timeout=timeout)
    logs.append(_format_section(section, command, result.exit_code, result.result or ""))
    if result.exit_code != 0:
        raise VerificationFailed(f"{section} failed (exit {result.exit_code})", logs)
    return result


def _overlay_command(rel_path: str) -> str:
    """Build the shell command that copies one mutable path into the canonical repo."""

    src = f"{AGENT_DIR}/{rel_path}"
    dest = f"{TASK_DIR}/{rel_path}"
    parent = os.path.dirname(dest) or TASK_DIR
    return (
        f"mkdir -p {shlex.quote(parent)}"
        f" && rm -rf {shlex.quote(dest)}"
        f" && cp -R {shlex.quote(src)} {shlex.quote(dest)}"
    )


def _format_section(section: str, command: str, exit_code: int, output: str) -> str:
    """Format one command's output for the stored verification log."""

    return (
        f"## {section}\n"
        f"$ {command}\n"
        f"exit_code={exit_code}\n"
        f"{output.strip()}\n"
    )


def _format_logs(logs: list[str], prefix: str | None = None) -> str:
    """Join verifier log sections with an optional summary prefix."""

    parts = [part for part in [prefix, *logs] if part]
    return "\n\n".join(parts)


def _parse_keyed_score(output: str, score_key: str | None) -> float | None:
    """Parse `key: value` or `key=value` output from the canonical eval."""

    keys = [score_key.lower()] if score_key else ["score", "accuracy", "result"]
    key_pattern = "|".join(re.escape(key) for key in keys)
    regex = re.compile(rf"(?:{key_pattern})\s*[:=]\s*({FLOAT_RE})", re.IGNORECASE)

    for line in reversed(output.strip().splitlines()):
        match = regex.search(line)
        if match:
            return float(match.group(1))
    return None


def _parse_last_float(output: str) -> float | None:
    """Parse a trailing bare float from eval output."""

    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(FLOAT_RE, line):
            return float(line)
    return None


async def _run_one_job(worker_id: int) -> bool:
    """Claim and verify one job.  Returns True if a job was processed."""

    job = await claim_next_job()
    if job is None:
        return False

    t0 = time.monotonic()
    log.info("[w%d] verifying run %s (task=%s)", worker_id, job.id, job.task_id)

    # Each job gets its own AsyncDaytona client to avoid shared-state issues
    # under concurrency.  The SDK uses internal connection pools that are not
    # documented as safe to share across concurrent coroutines.
    try:
        async with AsyncDaytona() as daytona:
            await verify_run(daytona, job)
    except Exception:
        log.exception("[w%d] daytona client error for run %s", worker_id, job.id)
        await record_result(job, STATUS_ERROR, None, None, "Daytona client error")

    elapsed = time.monotonic() - t0
    log.info("[w%d] finished run %s (%.1fs)", worker_id, job.id, elapsed)
    return True


async def _worker(worker_id: int, sem: asyncio.Semaphore) -> None:
    """One worker coroutine: claim jobs until cancelled."""

    while True:
        async with sem:
            processed = await _run_one_job(worker_id)
        if not processed:
            await asyncio.sleep(POLL_INTERVAL)


async def _coordinator() -> None:
    """Periodically reclaim stale jobs."""

    while True:
        try:
            reclaimed = await requeue_stale_jobs()
            if reclaimed:
                log.warning("re-queued %d stale verification jobs", reclaimed)
        except Exception:
            log.exception("stale-job recovery failed")
        await asyncio.sleep(POLL_INTERVAL * 6)


async def poll_loop(daytona: AsyncDaytona) -> None:
    """Legacy single-worker loop (MAX_CONCURRENT_JOBS=1).

    Kept for backward compatibility and readability.  The daytona client
    passed in is reused across sequential jobs.
    """

    while True:
        reclaimed = await requeue_stale_jobs()
        if reclaimed:
            log.warning("re-queued %d stale verification jobs", reclaimed)

        job = await claim_next_job()
        if job is None:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        t0 = time.monotonic()
        log.info("verifying run %s (task=%s)", job.id, job.task_id)
        await verify_run(daytona, job)
        log.info("finished run %s (%.1fs)", job.id, time.monotonic() - t0)


def _effective_pool_max() -> int:   
    """Compute DB pool max based on concurrency config."""

    if DB_POOL_MAX > 0:
        return DB_POOL_MAX
    # Each concurrent job may hold 1-2 connections (claim + record_result).
    # Add a small buffer.
    return max(4, MAX_CONCURRENT_JOBS * 2 + 2)


async def main() -> None:
    """Entry point for the standalone verification worker."""

    pool_max = _effective_pool_max()
    pool_min = min(DB_POOL_MIN, pool_max)
    init_db()
    await init_pool(min_size=pool_min, max_size=pool_max)

    log.info(
        "verification worker started: concurrency=%d, poll=%ds, db_pool=%d-%d",
        MAX_CONCURRENT_JOBS, POLL_INTERVAL, pool_min, pool_max,
    )

    try:
        if MAX_CONCURRENT_JOBS <= 1:
            # Single-worker fast path: share one Daytona client, no overhead.
            async with AsyncDaytona() as daytona:
                await poll_loop(daytona)
        else:
            # Concurrent workers: each job creates its own Daytona client.
            sem = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
            workers = [
                asyncio.create_task(_worker(i, sem), name=f"verifier-w{i}")
                for i in range(MAX_CONCURRENT_JOBS)
            ]
            coordinator = asyncio.create_task(_coordinator(), name="verifier-coordinator")
            # Wait until any task raises (should run forever).
            done, pending = await asyncio.wait(
                [*workers, coordinator], return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in done:
                if task.exception():
                    log.error("worker crashed: %s", task.exception())
            for task in pending:
                task.cancel()
    finally:
        await close_pool()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main())
