"""Terminal sandbox endpoints for interactive Daytona-backed workspaces.

Users create one sandbox per task. The sandbox gets the task repo cloned,
env vars from the task config, and Claude Code installed. The frontend
connects via SSH using credentials returned by the Daytona SDK.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse as _BaseJSONResponse

from .db import get_db, now

try:
    try:
        _daytona = importlib.import_module("daytona_sdk")
    except ImportError:
        _daytona = importlib.import_module("daytona")
except ImportError:
    AsyncDaytona = Any  # type: ignore[assignment]
    CreateSandboxFromSnapshotParams = None  # type: ignore[assignment]
else:
    AsyncDaytona = _daytona.AsyncDaytona  # type: ignore[attr-defined]
    CreateSandboxFromSnapshotParams = getattr(_daytona, "CreateSandboxFromSnapshotParams", None)

log = logging.getLogger("hive.sandbox")

SANDBOX_SNAPSHOT = os.environ.get("SANDBOX_SNAPSHOT", "hive-verify-python")
SANDBOX_CREATE_TIMEOUT = int(os.environ.get("SANDBOX_CREATE_TIMEOUT", "120"))
SANDBOX_AUTO_STOP_INTERVAL = int(os.environ.get("SANDBOX_AUTO_STOP_INTERVAL", "30"))
SANDBOX_SSH_EXPIRES_MINUTES = int(os.environ.get("SANDBOX_SSH_EXPIRES_MINUTES", "480"))
SANDBOX_BOOTSTRAP_TIMEOUT = int(os.environ.get("SANDBOX_BOOTSTRAP_TIMEOUT", "300"))

router = APIRouter(prefix="/api")


class JSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            default=lambda o: o.isoformat() if isinstance(o, datetime) else (_ for _ in ()).throw(TypeError),
        ).encode("utf-8")


def _resolve_sandbox_env_vars(config_raw: str | None) -> dict[str, str]:
    """Build env vars from a task's verification config."""
    if not config_raw:
        return {}
    try:
        config = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
    except (json.JSONDecodeError, TypeError):
        return {}
    sandbox_cfg = config.get("sandbox", {})
    env_vars: dict[str, str] = {}
    if isinstance(sandbox_cfg.get("env"), (dict, list)):
        raw_env = sandbox_cfg["env"]
        if isinstance(raw_env, dict):
            env_vars.update(raw_env)
        elif isinstance(raw_env, list):
            for pair in raw_env:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    env_vars[pair[0]] = pair[1]
    if isinstance(sandbox_cfg.get("secret_env"), (dict, list)):
        raw_secret = sandbox_cfg["secret_env"]
        pairs = raw_secret.items() if isinstance(raw_secret, dict) else raw_secret
        for env_name, ref in pairs:
            secret_name = f"HIVE_VERIFY_SECRET_{ref.upper()}"
            secret_value = os.environ.get(secret_name)
            if secret_value:
                env_vars[env_name] = secret_value
    return env_vars


def _require_user():
    from .main import require_user
    return Depends(require_user)


async def _check_task_access(owner: str, slug: str, authorization: str):
    from .main import require_task_access
    await require_task_access(owner, slug, authorization)


async def _resolve_task(conn: Any, owner: str, slug: str) -> dict:
    """Look up a task by owner+slug. Returns the row dict; raises 404."""
    row = await (await conn.execute(
        "SELECT id, repo_url, config FROM tasks WHERE owner = %s AND slug = %s",
        (owner, slug),
    )).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    return dict(row)


def _encrypt(value: str | None) -> str | None:
    from .main import _encrypt
    return _encrypt(value)


def _decrypt(value: str | None) -> str | None:
    from .main import _decrypt
    return _decrypt(value)


def _sandbox_response(row: dict, status_code: int = 200) -> JSONResponse:
    data: dict[str, Any] = {
        "sandbox_id": row["id"],
        "status": row["status"],
        "daytona_sandbox_id": row.get("daytona_sandbox_id"),
        "created_at": row["created_at"],
        "last_accessed_at": row.get("last_accessed_at"),
    }
    if row["status"] == "ready" and row.get("ssh_command"):
        data["ssh_command"] = row["ssh_command"]
        data["ssh_token"] = _decrypt(row["ssh_token"])
        data["ssh_expires_at"] = row.get("ssh_expires_at")
    if row.get("error_message"):
        data["error_message"] = row["error_message"]
    return JSONResponse(data, status_code=status_code)


async def _bootstrap_sandbox(sandbox: Any, repo_url: str) -> None:
    """Install Claude Code, hive CLI, and hive skills. User runs /hive-setup to clone the task."""
    # Node + Claude Code
    await sandbox.process.exec(
        "rm -rf /usr/local/share/nvm/versions/node/v25* 2>/dev/null;"
        " export NVM_DIR=/usr/local/share/nvm && . $NVM_DIR/nvm.sh 2>/dev/null;"
        " nvm install 22 && nvm alias default 22 && nvm use 22"
        " && npm install -g @anthropic-ai/claude-code",
        cwd="/home/daytona",
        timeout=SANDBOX_BOOTSTRAP_TIMEOUT,
    )
    # opencode
    await sandbox.process.exec(
        "export NVM_DIR=/usr/local/share/nvm && . $NVM_DIR/nvm.sh 2>/dev/null;"
        " npm install -g opencode-ai",
        cwd="/home/daytona",
        timeout=SANDBOX_BOOTSTRAP_TIMEOUT,
    )
    # hive CLI + Claude skills
    _skills_base = "https://raw.githubusercontent.com/rllm-org/hive/staging/skills"
    await sandbox.process.exec(
        "pip install --break-system-packages git+https://github.com/rllm-org/hive.git@staging"
        f" && mkdir -p ~/.claude/skills/hive ~/.claude/skills/hive-setup ~/.claude/skills/hive-create-task"
        f" && curl -sfL {_skills_base}/hive/SKILL.md -o ~/.claude/skills/hive/SKILL.md"
        f" && curl -sfL {_skills_base}/hive-setup/SKILL.md -o ~/.claude/skills/hive-setup/SKILL.md"
        f" && curl -sfL {_skills_base}/hive-create-task/SKILL.md -o ~/.claude/skills/hive-create-task/SKILL.md",
        cwd="/home/daytona",
        timeout=SANDBOX_BOOTSTRAP_TIMEOUT,
    )


@router.post("/tasks/{owner}/{slug}/sandbox", status_code=201)
async def create_sandbox(
    owner: str,
    slug: str,
    authorization: str = Header(""),
):
    from .main import require_user as _require_user_fn
    user = await _require_user_fn(authorization)
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])

    async with get_db() as conn:
        task = await _resolve_task(conn, owner, slug)
        task_id = task["id"]

        # Check for existing sandbox
        existing = await (await conn.execute(
            "SELECT * FROM sandboxes WHERE task_id = %s AND user_id = %s",
            (task_id, user_id),
        )).fetchone()

        if existing:
            if existing["status"] == "creating":
                raise HTTPException(409, "sandbox is already being created")
            if existing["status"] in ("ready", "stopped"):
                return await _reconnect_sandbox(conn, existing)
            # error or deleted: remove old row and recreate
            await conn.execute("DELETE FROM sandboxes WHERE id = %s", (existing["id"],))

        # Insert placeholder row
        created_at = now()
        row = await (await conn.execute(
            "INSERT INTO sandboxes (task_id, user_id, status, created_at)"
            " VALUES (%s, %s, 'creating', %s) RETURNING id",
            (task_id, user_id, created_at),
        )).fetchone()
        sandbox_db_id = row["id"]

    # Create Daytona sandbox (outside DB transaction to avoid long-held connections)
    env_vars = _resolve_sandbox_env_vars(task["config"])
    try:
        async with AsyncDaytona() as daytona:
            if CreateSandboxFromSnapshotParams is None:
                raise RuntimeError("Daytona SDK does not expose CreateSandboxFromSnapshotParams")
            params = CreateSandboxFromSnapshotParams(
                snapshot=SANDBOX_SNAPSHOT,
                auto_stop_interval=SANDBOX_AUTO_STOP_INTERVAL,
                env_vars=env_vars or None,
            )
            sandbox = await daytona.create(params, timeout=SANDBOX_CREATE_TIMEOUT)

            await _bootstrap_sandbox(sandbox, task["repo_url"])

            ssh = await sandbox.create_ssh_access(expires_in_minutes=SANDBOX_SSH_EXPIRES_MINUTES)

            async with get_db() as conn:
                await conn.execute(
                    "UPDATE sandboxes SET status = 'ready',"
                    " daytona_sandbox_id = %s, ssh_command = %s,"
                    " ssh_token = %s, ssh_expires_at = %s,"
                    " last_accessed_at = %s"
                    " WHERE id = %s",
                    (sandbox.id, ssh.ssh_command, _encrypt(ssh.token),
                     ssh.expires_at, now(), sandbox_db_id),
                )
                result = await (await conn.execute(
                    "SELECT * FROM sandboxes WHERE id = %s", (sandbox_db_id,)
                )).fetchone()
            return _sandbox_response(dict(result), status_code=201)

    except Exception as exc:
        log.exception("Failed to create sandbox for task %s/%s user %s", owner, slug, user_id)
        async with get_db() as conn:
            await conn.execute(
                "UPDATE sandboxes SET status = 'error', error_message = %s WHERE id = %s",
                (str(exc)[:1000], sandbox_db_id),
            )
        raise HTTPException(502, f"sandbox creation failed: {exc}")


async def _reconnect_sandbox(conn: Any, row: dict) -> JSONResponse:
    """Reconnect to an existing sandbox: refresh SSH access, restart if stopped."""
    daytona_id = row.get("daytona_sandbox_id")
    if not daytona_id:
        raise HTTPException(502, "sandbox has no Daytona ID")

    try:
        async with AsyncDaytona() as daytona:
            sandbox = await daytona.get(daytona_id)

            if row["status"] == "stopped":
                await sandbox.start()

            ssh = await sandbox.create_ssh_access(expires_in_minutes=SANDBOX_SSH_EXPIRES_MINUTES)

            await conn.execute(
                "UPDATE sandboxes SET status = 'ready',"
                " ssh_command = %s, ssh_token = %s,"
                " ssh_expires_at = %s, last_accessed_at = %s,"
                " error_message = NULL"
                " WHERE id = %s",
                (ssh.ssh_command, _encrypt(ssh.token),
                 ssh.expires_at, now(), row["id"]),
            )
            updated = await (await conn.execute(
                "SELECT * FROM sandboxes WHERE id = %s", (row["id"],)
            )).fetchone()
        return _sandbox_response(dict(updated))
    except Exception as exc:
        log.exception("Failed to reconnect sandbox %s", daytona_id)
        await conn.execute(
            "UPDATE sandboxes SET status = 'error', error_message = %s WHERE id = %s",
            (str(exc)[:1000], row["id"]),
        )
        raise HTTPException(502, f"sandbox reconnection failed: {exc}")


@router.get("/tasks/{owner}/{slug}/sandbox")
async def get_sandbox(
    owner: str,
    slug: str,
    authorization: str = Header(""),
):
    from .main import require_user as _require_user_fn
    user = await _require_user_fn(authorization)
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])

    async with get_db() as conn:
        task = await _resolve_task(conn, owner, slug)
        task_id = task["id"]
        row = await (await conn.execute(
            "SELECT * FROM sandboxes WHERE task_id = %s AND user_id = %s",
            (task_id, user_id),
        )).fetchone()
        if not row:
            raise HTTPException(404, "no sandbox for this task")

        row = dict(row)

        # Refresh SSH token if expired
        if (
            row["status"] == "ready"
            and row.get("ssh_expires_at")
            and row["ssh_expires_at"] < now()
            and row.get("daytona_sandbox_id")
        ):
            try:
                async with AsyncDaytona() as daytona:
                    sandbox = await daytona.get(row["daytona_sandbox_id"])
                    ssh = await sandbox.create_ssh_access(expires_in_minutes=SANDBOX_SSH_EXPIRES_MINUTES)
                    await conn.execute(
                        "UPDATE sandboxes SET ssh_command = %s, ssh_token = %s,"
                        " ssh_expires_at = %s, last_accessed_at = %s"
                        " WHERE id = %s",
                        (ssh.ssh_command, _encrypt(ssh.token),
                         ssh.expires_at, now(), row["id"]),
                    )
                    row["ssh_command"] = ssh.ssh_command
                    row["ssh_token"] = _encrypt(ssh.token)
                    row["ssh_expires_at"] = ssh.expires_at
            except Exception as exc:
                log.warning("Failed to refresh SSH access for sandbox %s: %s", row["id"], exc)

        # Update last_accessed_at
        await conn.execute(
            "UPDATE sandboxes SET last_accessed_at = %s WHERE id = %s",
            (now(), row["id"]),
        )
        return _sandbox_response(row)


@router.delete("/tasks/{owner}/{slug}/sandbox")
async def delete_sandbox(
    owner: str,
    slug: str,
    authorization: str = Header(""),
):
    from .main import require_user as _require_user_fn
    user = await _require_user_fn(authorization)
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])

    async with get_db() as conn:
        task = await _resolve_task(conn, owner, slug)
        task_id = task["id"]
        row = await (await conn.execute(
            "SELECT * FROM sandboxes WHERE task_id = %s AND user_id = %s",
            (task_id, user_id),
        )).fetchone()
        if not row:
            raise HTTPException(404, "no sandbox for this task")

        from .sandbox_terminal import stop_all_terminal_sessions_for_sandbox
        await stop_all_terminal_sessions_for_sandbox(row["id"])

        daytona_id = row.get("daytona_sandbox_id")
        if daytona_id:
            try:
                async with AsyncDaytona() as daytona:
                    sandbox = await daytona.get(daytona_id)
                    try:
                        await sandbox.stop()
                    except Exception:
                        pass
                    await daytona.delete(sandbox, timeout=60)
            except Exception as exc:
                log.warning("Failed to delete Daytona sandbox %s: %s", daytona_id, exc)

        await conn.execute("DELETE FROM sandboxes WHERE id = %s", (row["id"],))
        return {"status": "deleted"}
