"""Swarm state file management.

State files live at ~/.hive/swarms/{task_id}.json and track
all agents spawned for a given task.
"""

import json
import os
import signal
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SWARMS_DIR = Path.home() / ".hive" / "swarms"


def _atomic_write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _state_path(task_id: str) -> Path:
    return SWARMS_DIR / f"{task_id}.json"


def load_swarm(task_id: str) -> dict | None:
    p = _state_path(task_id)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def save_swarm(state: dict):
    _atomic_write(_state_path(state["task_id"]), state)


def delete_swarm(task_id: str):
    p = _state_path(task_id)
    if p.exists():
        p.unlink()


def list_swarms() -> list[dict]:
    if not SWARMS_DIR.exists():
        return []
    swarms = []
    for p in sorted(SWARMS_DIR.glob("*.json")):
        try:
            with open(p) as f:
                swarms.append(json.load(f))
        except (json.JSONDecodeError, ValueError):
            continue
    return swarms


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_matches_command(pid: int, expected_fragment: str) -> bool:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True,
        )
        return expected_fragment in result.stdout
    except Exception:
        return True  # assume alive if we can't check


def check_agent_alive(agent: dict) -> bool:
    pid = agent.get("pid")
    if not pid:
        return False
    if not _pid_alive(pid):
        return False
    return True


def refresh_statuses(state: dict) -> dict:
    for agent in state.get("agents", []):
        if agent.get("status") == "running" and not check_agent_alive(agent):
            agent["status"] = "stopped"
    return state


def new_swarm_state(task_id: str, base_dir: str, agent_command: str) -> dict:
    return {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agent_command": agent_command,
        "base_dir": base_dir,
        "agents": [],
    }


def add_agent_to_state(state: dict, agent_id: str, token: str,
                        pid: int, work_dir: str, log_file: str) -> dict:
    state["agents"].append({
        "agent_id": agent_id,
        "token": token,
        "pid": pid,
        "work_dir": work_dir,
        "log_file": log_file,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    return state


def stop_agent_process(agent: dict, timeout: int = 10):
    pid = agent.get("pid")
    if not pid or not _pid_alive(pid):
        agent["status"] = "stopped"
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        agent["status"] = "stopped"
        return
    # Wait for graceful shutdown
    import time
    for _ in range(timeout):
        if not _pid_alive(pid):
            break
        time.sleep(1)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    agent["status"] = "stopped"
