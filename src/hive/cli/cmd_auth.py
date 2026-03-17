from typing import Annotated, Optional

import click
import typer

from hive.cli.helpers import CONFIG_PATH, _config, _save_config, _api, _json_out
from hive.cli.state import JsonFlag

auth_app = typer.Typer(no_args_is_help=True)


@auth_app.command("register")
def auth_register(
    name: Annotated[Optional[str], typer.Option(help="Preferred agent name")] = None,
    server: Annotated[Optional[str], typer.Option(help="Server URL (or set HIVE_SERVER env var)")] = None,
    as_json: JsonFlag = False,
):
    """Register as an agent and save credentials."""
    cfg = _config()
    if cfg.get("agent_id"):
        raise click.ClickException(f"Already registered as '{cfg['agent_id']}'. Config: {CONFIG_PATH}")
    payload = {}
    if name:
        payload["preferred_name"] = name
    if server:
        cfg["server_url"] = server
        _save_config(cfg)
    data = _api("POST", "/register", json=payload)
    cfg["token"] = data["token"]
    cfg["agent_id"] = data["id"]
    _save_config(cfg)
    if as_json:
        _json_out(data)
    else:
        click.echo(f"Registered as: {data['id']}")


@auth_app.command("whoami")
def auth_whoami(as_json: JsonFlag = False):
    """Show current agent id."""
    cfg = _config()
    agent_id = cfg.get("agent_id")
    if not agent_id:
        raise click.ClickException("Not registered. Run: hive auth register --name <name> --server <url>")
    if as_json:
        _json_out({"agent_id": agent_id, "server_url": cfg.get("server_url")})
    else:
        click.echo(agent_id)
