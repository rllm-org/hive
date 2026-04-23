from typing import Annotated

import typer

from hive.cli.formatting import ok
from hive.cli.helpers import _api, _json_out
from hive.cli.state import JsonFlag, WorkspaceOpt, _set_workspace, get_workspace

workspace_app = typer.Typer(no_args_is_help=True)


@workspace_app.callback()
def workspace_callback(workspace_opt: WorkspaceOpt = None):
    """Workspace — list agents, view workspace info."""
    _set_workspace(workspace_opt)


@workspace_app.command("agents")
def workspace_agents(
    as_json: JsonFlag = False,
    workspace_opt: WorkspaceOpt = None,
):
    """List agents in this workspace with roles and descriptions."""
    _set_workspace(workspace_opt)
    ws = get_workspace()
    if ws is None:
        typer.echo("Error: --workspace is required", err=True)
        raise typer.Exit(1)
    data = _api("GET", f"/workspaces/{ws}/agents")
    if as_json:
        _json_out(data)
        return
    agents = data.get("agents", [])
    if not agents:
        typer.echo("No agents in this workspace.")
        return
    for a in agents:
        parts = [f"  @{a['id']}"]
        if a.get("role"):
            parts.append(f"  Role: {a['role']}")
        if a.get("description"):
            parts.append(f"  Description: {a['description']}")
        parts.append(f"  Model: {a.get('model', 'unknown')} | Harness: {a.get('harness', 'unknown')}")
        typer.echo("\n".join(parts))
        typer.echo("")
