import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import httpx

CONFIG_PATH = Path.home() / ".hive" / "config.json"


def _config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


DEFAULT_SERVER_URL = "https://hive.rllm-project.com/"


def _server_url() -> str:
    cfg = _config()
    url = os.environ.get("HIVE_SERVER") or cfg.get("server_url") or DEFAULT_SERVER_URL
    return url


def _token() -> str:
    token = _config().get("token")
    if not token:
        raise click.ClickException("Not registered. Run: hive auth register --name <name>")
    return token


def _api(method: str, path: str, **kwargs):
    url = _server_url().rstrip("/") + "/api" + path
    cfg = _config()
    params = kwargs.pop("params", {}) or {}
    params["token"] = cfg.get("token", "")
    try:
        headers = kwargs.pop("headers", {})
        headers["ngrok-skip-browser-warning"] = "1"
        resp = httpx.request(method, url, params=params, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise click.ClickException(f"Server error {e.response.status_code}: {e.response.text}")
    except httpx.RequestError as e:
        raise click.ClickException(f"Request failed: {e}")


def _task_id(cli_task=None) -> str:
    if cli_task:
        return cli_task
    env_task = os.environ.get("HIVE_TASK")
    if env_task:
        return env_task
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        task_file = directory / ".hive" / "task"
        if task_file.exists():
            return task_file.read_text().strip()
    raise click.ClickException(
        "No task specified. Either:\n"
        "  - Pass --task <task-id>\n"
        "  - Set HIVE_TASK env var\n"
        "  - Run from inside a cloned task dir (has .hive/task)"
    )


def _git(*args) -> str:
    result = subprocess.run(["git"] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        raise click.ClickException(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _parse_since(s: str) -> str:
    units = {"h": 3600, "m": 60, "d": 86400}
    unit = s[-1]
    if unit not in units:
        raise click.ClickException(f"Invalid --since: {s!r}. Use e.g. 1h, 30m, 1d")
    try:
        val = int(s[:-1])
    except ValueError:
        raise click.ClickException(f"Invalid --since: {s!r}")
    dt = datetime.now(timezone.utc) - timedelta(seconds=val * units[unit])
    return dt.isoformat()


def _json_out(data):
    """Print data as JSON and exit."""
    click.echo(json.dumps(data, indent=2))
