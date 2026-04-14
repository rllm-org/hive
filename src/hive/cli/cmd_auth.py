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


@auth_app.command("register")
def auth_register(
    name: Annotated[Optional[str], typer.Option(help="Preferred agent name")] = None,
    server: Annotated[Optional[str], typer.Option(help="Server URL (or set HIVE_SERVER env var)")] = None,
    as_json: JsonFlag = False,
):
    """Register a new agent."""
    _do_login(name, server, as_json)


@auth_app.command("switch")
def auth_switch(
    name: Annotated[str, typer.Argument(help="Agent name to switch to")],
):
    """Switch the active agent."""
    _load_agent(name)  # validate exists
    cfg = _config()
    cfg["default_agent"] = name
    _save_config(cfg)
    ok(f"Switched to '{name}'")


@auth_app.command("status")
def auth_status(as_json: JsonFlag = False):
    """List all registered agents."""
    _migrate_config()
    agents = _list_agents()
    if not agents:
        raise click.ClickException("No agents registered. Run: hive auth register --name <name>")
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


@auth_app.command("unregister")
def auth_unregister(
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


@auth_app.command("login")
def auth_user_login(
    server: Annotated[Optional[str], typer.Option(help="Server URL")] = None,
    relogin: Annotated[bool, typer.Option("--relogin", help="Force re-login")] = False,
):
    """Log in as a Hive user to access private tasks."""
    import httpx
    from hive.cli.helpers import _server_url

    cfg = _config()
    if server:
        cfg["server_url"] = server
        _save_config(cfg)

    base = _server_url().rstrip("/")

    # Check if already logged in
    existing_key = cfg.get("user_api_key")
    if existing_key and not relogin:
        try:
            resp = httpx.get(
                f"{base}/api/auth/me",
                headers={"Authorization": f"Bearer {existing_key}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                me = resp.json()
                display = me.get("handle") or me.get("email", "unknown")
                click.echo(f"Already logged in as: {display}")
                click.echo("To re-login, run: hive auth login --relogin")
                return
        except Exception:
            pass

    click.echo(f"Go to your Hive account settings to find your API key:")
    click.echo(f"  {base.replace('/api', '').rstrip('/')}/me?tab=settings")
    click.echo()
    api_key = click.prompt("Paste your API key", hide_input=True).strip()

    if not api_key.startswith("hive_"):
        raise click.ClickException("Invalid API key format. Keys start with 'hive_'.")

    # Validate
    try:
        resp = httpx.get(
            f"{base}/api/auth/me",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        if resp.status_code == 401:
            raise click.ClickException("Invalid API key.")
        resp.raise_for_status()
        user = resp.json()
    except click.ClickException:
        raise
    except httpx.ConnectError:
        raise click.ClickException(f"Could not connect to {base}")
    except Exception as e:
        raise click.ClickException(f"Validation failed: {e}")

    cfg["user_api_key"] = api_key
    _save_config(cfg)
    display = user.get("handle") or user.get("email", "unknown")
    ok(f"Logged in as {display}")



@auth_app.command("claim")
def auth_claim():
    """Claim agents to link them to your user account."""
    import httpx
    from hive.cli.helpers import _server_url

    cfg = _config()
    api_key = cfg.get("user_api_key")
    if not api_key:
        raise click.ClickException("Not logged in. Run: hive auth login")

    _migrate_config()
    agents = _list_agents()
    if not agents:
        raise click.ClickException("No agents registered. Run: hive auth register")

    # Fetch already-claimed agents
    base = _server_url().rstrip("/")
    claimed_ids = set()
    try:
        resp = httpx.get(f"{base}/api/auth/me", headers={"Authorization": f"Bearer {api_key}"}, timeout=10.0)
        if resp.status_code == 200:
            claimed_ids = {a["id"] for a in resp.json().get("agents", [])}
    except Exception:
        pass

    # Filter out already-claimed agents
    unclaimed = [a for a in agents if a["agent_id"] not in claimed_ids]
    if not unclaimed:
        click.echo("All your agents are already claimed.")
        return

    # Show multi-select list
    click.echo("Select agents to claim (enter numbers separated by spaces):\n")
    for i, a in enumerate(unclaimed, 1):
        click.echo(f"  {i}. {a['agent_id']}")
    click.echo()

    selection = click.prompt("Agents to claim (e.g. 1 3 4, or 'all')").strip()
    if selection.lower() == "all":
        selected = unclaimed
    else:
        try:
            indices = [int(x) for x in selection.split()]
            selected = [unclaimed[i - 1] for i in indices if 1 <= i <= len(unclaimed)]
        except (ValueError, IndexError):
            raise click.ClickException("Invalid selection.")

    if not selected:
        click.echo("No agents selected.")
        return

    base = _server_url().rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    claimed = []
    failed = []

    for agent in selected:
        try:
            resp = httpx.post(
                f"{base}/api/auth/claim",
                json={"token": agent["token"]},
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code == 200:
                status = resp.json().get("status", "claimed")
                claimed.append((agent["agent_id"], status))
            else:
                detail = resp.json().get("detail", f"HTTP {resp.status_code}")
                failed.append((agent["agent_id"], detail))
        except Exception as e:
            failed.append((agent["agent_id"], str(e)))

    if claimed:
        names = ", ".join(name for name, _ in claimed)
        ok(f"Claimed: {names}")
    if failed:
        for name, reason in failed:
            click.echo(f"  ✗ {name}: {reason}", err=True)


@auth_app.command("whoami")
def auth_whoami(as_json: JsonFlag = False):
    """Show current agent id."""
    _migrate_config()
    try:
        name = _resolve_agent_name()
        agent = _load_agent(name)
    except click.ClickException:
        raise click.ClickException("Not registered. Run: hive auth register --name <name>")
    if as_json:
        _json_out({"agent_id": agent["agent_id"], "server_url": _config().get("server_url")})
    else:
        click.echo(agent["agent_id"])
