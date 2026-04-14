import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import httpx

CONFIG_PATH = Path.home() / ".hive" / "config.json"
AGENTS_DIR = Path.home() / ".hive" / "agents"


def _config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    CONFIG_PATH.chmod(0o600)


def _migrate_config():
    cfg = _config()
    if not cfg.get("agent_id"):
        return
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agent_file = AGENTS_DIR / f"{cfg['agent_id']}.json"
    if not agent_file.exists():
        with open(agent_file, "w") as f:
            json.dump({"agent_id": cfg["agent_id"], "token": cfg["token"]}, f, indent=2)
    cfg["default_agent"] = cfg.pop("agent_id")
    cfg.pop("token", None)
    _save_config(cfg)


def _save_agent(agent_id: str, token: str):
    AGENTS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    agent_file = AGENTS_DIR / f"{agent_id}.json"
    with open(agent_file, "w") as f:
        json.dump({"agent_id": agent_id, "token": token}, f, indent=2)
    agent_file.chmod(0o600)


def _load_agent(name: str) -> dict:
    p = AGENTS_DIR / f"{name}.json"
    if not p.exists():
        raise click.ClickException(f"Agent '{name}' not found. Run: hive auth status")
    with open(p) as f:
        return json.load(f)


def _list_agents() -> list[dict]:
    if not AGENTS_DIR.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(AGENTS_DIR.glob("*.json"))]


def _resolve_agent_name() -> str:
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        agent_file = directory / ".hive" / "agent"
        if agent_file.exists():
            return agent_file.read_text().strip()
    cfg = _config()
    if cfg.get("default_agent"):
        return cfg["default_agent"]
    raise click.ClickException("No agent configured. Run: hive auth register --name <name>")


def _active_agent() -> dict:
    _migrate_config()
    return _load_agent(_resolve_agent_name())


def _agent_id() -> str:
    return _active_agent()["agent_id"]


DEFAULT_SERVER_URL = "https://hive.rllm-project.com/"


def _server_url() -> str:
    cfg = _config()
    url = os.environ.get("HIVE_SERVER") or cfg.get("server_url") or DEFAULT_SERVER_URL
    return url


def _token() -> str:
    return _active_agent()["token"]


def _api(method: str, path: str, **kwargs):
    url = _server_url().rstrip("/") + "/api" + path
    params = kwargs.pop("params", {}) or {}
    try:
        headers = kwargs.pop("headers", {})
        headers["ngrok-skip-browser-warning"] = "1"
        # Agent token: send as header (avoid URL logging leaks)
        if "X-Agent-Token" not in headers:
            try:
                agent_token = _active_agent().get("token", "")
                if agent_token:
                    headers["X-Agent-Token"] = agent_token
            except click.ClickException:
                pass
        # Send user API key if logged in
        api_key = _config().get("user_api_key")
        if api_key and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = httpx.request(method, url, params=params, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        raise click.ClickException(detail)
    except httpx.RequestError as e:
        raise click.ClickException(f"Request failed: {e}")


def _task_ref(cli_task=None) -> str:
    ref = None
    if cli_task:
        ref = cli_task
    else:
        env_task = os.environ.get("HIVE_TASK")
        if env_task:
            ref = env_task
        else:
            cwd = Path.cwd()
            for directory in [cwd, *cwd.parents]:
                task_file = directory / ".hive" / "task"
                if task_file.exists():
                    ref = task_file.read_text().strip()
                    break
    if not ref:
        raise click.ClickException(
            "No task specified. Either:\n"
            "  - Pass --task <owner/slug>\n"
            "  - Set HIVE_TASK env var\n"
            "  - Run from inside a cloned task dir (has .hive/task)"
        )
    # Legacy compat: bare slug without / -> hive/{slug}
    if "/" not in ref:
        ref = f"hive/{ref}"
    return ref


def _split_task_ref(ref: str) -> tuple[str, str]:
    owner, slug = ref.split("/", 1)
    return owner, slug


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
