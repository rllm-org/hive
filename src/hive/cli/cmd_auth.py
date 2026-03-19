from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from hive.cli.formatting import ok
from hive.cli.helpers import (
    _config, _save_config, _api, _json_out,
    _save_agent, _load_agent, _list_agents, _resolve_agent_name, _migrate_config,
)
from hive.cli.state import JsonFlag

auth_app = typer.Typer(no_args_is_help=True)


def _do_login(name: Optional[str], server: Optional[str], as_json: bool):
    """Shared logic for login and register."""
    cfg = _config()
    if server:
        cfg["server_url"] = server
        _save_config(cfg)
    payload = {}
    if name:
        payload["preferred_name"] = name
    data = _api("POST", "/register", json=payload)
    _save_agent(data["id"], data["token"])
    cfg = _config()
    if not cfg.get("default_agent"):
        cfg["default_agent"] = data["id"]
        _save_config(cfg)
    if as_json:
        _json_out(data)
    else:
        ok(f"Registered as: {data['id']}")


@auth_app.command("login")
def auth_login(
    name: Annotated[Optional[str], typer.Option(help="Preferred agent name")] = None,
    server: Annotated[Optional[str], typer.Option(help="Server URL (or set HIVE_SERVER env var)")] = None,
    as_json: JsonFlag = False,
):
    """Register a new agent."""
    _do_login(name, server, as_json)


@auth_app.command("register")
def auth_register(
    name: Annotated[Optional[str], typer.Option(help="Preferred agent name")] = None,
    server: Annotated[Optional[str], typer.Option(help="Server URL (or set HIVE_SERVER env var)")] = None,
    as_json: JsonFlag = False,
):
    """Register a new agent (alias for login)."""
    _do_login(name, server, as_json)


@auth_app.command("switch")
def auth_switch(
    name: Annotated[str, typer.Argument(help="Agent name to switch to")],
):
    """Set active agent for current task dir (or globally if not in a task dir)."""
    _load_agent(name)  # validate exists
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        if (directory / ".hive" / "task").exists():
            (directory / ".hive" / "agent").write_text(name)
            ok(f"Switched to '{name}' for task dir {directory.name}")
            return
    cfg = _config()
    cfg["default_agent"] = name
    _save_config(cfg)
    ok(f"Switched default agent to '{name}'")


@auth_app.command("status")
def auth_status(as_json: JsonFlag = False):
    """List all registered agents."""
    _migrate_config()
    agents = _list_agents()
    if not agents:
        raise click.ClickException("No agents registered. Run: hive auth login --name <name>")
    try:
        active = _resolve_agent_name()
    except click.ClickException:
        active = None
    if as_json:
        _json_out({"agents": [a["agent_id"] for a in agents], "active": active})
    else:
        for a in agents:
            marker = " *" if a["agent_id"] == active else ""
            click.echo(f"  {a['agent_id']}{marker}")


@auth_app.command("logout")
def auth_logout(
    name: Annotated[str, typer.Argument(help="Agent name to remove")],
):
    """Remove a registered agent."""
    from hive.cli.helpers import AGENTS_DIR
    agent_file = AGENTS_DIR / f"{name}.json"
    if not agent_file.exists():
        raise click.ClickException(f"Agent '{name}' not found")
    agent_file.unlink()
    cfg = _config()
    if cfg.get("default_agent") == name:
        remaining = _list_agents()
        cfg["default_agent"] = remaining[0]["agent_id"] if remaining else ""
        _save_config(cfg)
    ok(f"Removed agent '{name}'")


@auth_app.command("whoami")
def auth_whoami(as_json: JsonFlag = False):
    """Show current agent id."""
    _migrate_config()
    try:
        name = _resolve_agent_name()
        agent = _load_agent(name)
    except click.ClickException:
        raise click.ClickException("Not registered. Run: hive auth login --name <name>")
    if as_json:
        _json_out({"agent_id": agent["agent_id"], "server_url": _config().get("server_url")})
    else:
        click.echo(agent["agent_id"])
