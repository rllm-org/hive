from typing import Annotated, Optional

import click
import httpx
import typer

from hive.cli.helpers import _api, _config, _json_out, _server_url, _task_id
from hive.cli.state import JsonFlag

sandbox_app = typer.Typer(no_args_is_help=True, name="sandbox")


@sandbox_app.command("up")
def sandbox_up(
    task: Annotated[Optional[str], typer.Option("--task", help="Task id")] = None,
    provider: Annotated[str, typer.Option(help="claude_code, codex, opencode")] = "claude_code",
    as_json: JsonFlag = False,
):
    """Ensure the task sandbox exists (private tasks only)."""
    tid = _task_id(task)
    data = _api("POST", f"/tasks/{tid}/sandbox", json={"provider": provider})
    if as_json:
        _json_out(data)
    else:
        click.echo(f"Sandbox: {data.get('sandbox_id')} status={data.get('status')}")


@sandbox_app.command("status")
def sandbox_status(
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    as_json: JsonFlag = False,
):
    tid = _task_id(task)
    data = _api("GET", f"/tasks/{tid}/sandbox")
    if as_json:
        _json_out(data)
    else:
        s = data.get("sandbox")
        if not s:
            click.echo("No sandbox yet. Run: hive sandbox up")
        else:
            click.echo(f"status={s.get('status')} provider={s.get('provider')} id={s.get('id')}")


@sandbox_app.command("stop")
def sandbox_stop(
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    as_json: JsonFlag = False,
):
    tid = _task_id(task)
    data = _api("POST", f"/tasks/{tid}/sandbox/stop")
    if as_json:
        _json_out(data)
    else:
        click.echo(data.get("status", "ok"))


@sandbox_app.command("delete")
def sandbox_delete(
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    as_json: JsonFlag = False,
):
    """Delete the sandbox and all sessions/events/logs."""
    tid = _task_id(task)
    data = _api("DELETE", f"/tasks/{tid}/sandbox")
    if as_json:
        _json_out(data)
    else:
        click.echo(data.get("status", "deleted"))


@sandbox_app.command("logs")
def sandbox_logs(
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    page: int = 1,
    as_json: JsonFlag = False,
):
    tid = _task_id(task)
    data = _api("GET", f"/tasks/{tid}/sandbox/logs", params={"page": page})
    if as_json:
        _json_out(data)
    else:
        for c in data.get("chunks", []):
            click.echo(f"[{c.get('source')}] {c.get('text', '').rstrip()}")


session_app = typer.Typer(no_args_is_help=True, name="session")
sandbox_app.add_typer(session_app, name="session")


@session_app.command("start")
def session_start(
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    provider: Annotated[str, typer.Option()] = "claude_code",
    auto_accept: Annotated[bool, typer.Option("--auto-accept")] = False,
    as_json: JsonFlag = False,
):
    tid = _task_id(task)
    mode = "auto_accept" if auto_accept else "guarded"
    data = _api(
        "POST",
        f"/tasks/{tid}/sandbox/sessions",
        json={"provider": provider, "approval_mode": mode},
    )
    if as_json:
        _json_out(data)
    else:
        click.echo(f"session_id={data.get('session_id')} approval={data.get('approval_mode')}")


@session_app.command("send")
def session_send(
    session_id: Annotated[str, typer.Argument()],
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    message: Annotated[str, typer.Option("--message", "-m")] = "",
    as_json: JsonFlag = False,
):
    if not message:
        raise click.ClickException("--message required")
    tid = _task_id(task)
    data = _api(
        "POST",
        f"/tasks/{tid}/sandbox/sessions/{session_id}/messages",
        json={"message": message},
    )
    if as_json:
        _json_out(data)
    else:
        click.echo("ok")


@session_app.command("attach")
def session_attach(
    session_id: Annotated[str, typer.Argument()],
    task: Annotated[Optional[str], typer.Option("--task")] = None,
):
    """Stream session events (SSE) to the terminal."""
    tid = _task_id(task)
    base = _server_url().rstrip("/") + f"/api/tasks/{tid}/sandbox/sessions/{session_id}/stream"
    headers = {"ngrok-skip-browser-warning": "1"}
    api_key = _config().get("user_api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        raise click.ClickException("User login required: hive auth login")
    with httpx.Client(timeout=None) as client:
        with client.stream("GET", base, headers=headers) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    click.echo(line[6:])


@session_app.command("interrupt")
def session_interrupt(
    session_id: Annotated[str, typer.Argument()],
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    as_json: JsonFlag = False,
):
    tid = _task_id(task)
    data = _api("POST", f"/tasks/{tid}/sandbox/sessions/{session_id}/interrupt")
    if as_json:
        _json_out(data)
    else:
        click.echo(data.get("status", "ok"))


@session_app.command("events")
def session_events(
    session_id: Annotated[str, typer.Argument()],
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    offset: int = 0,
    limit: int = 100,
    as_json: JsonFlag = False,
):
    """List session events (paginated)."""
    tid = _task_id(task)
    data = _api(
        "GET",
        f"/tasks/{tid}/sandbox/sessions/{session_id}/events",
        params={"offset": offset, "limit": limit},
    )
    if as_json:
        _json_out(data)
    else:
        for ev in data.get("events", []):
            click.echo(f"[{ev.get('offset')}] {ev.get('type')}: {ev.get('data')}")


@session_app.command("transcript")
def session_transcript(
    session_id: Annotated[str, typer.Argument()],
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    as_json: JsonFlag = False,
):
    """Dump full session transcript."""
    tid = _task_id(task)
    data = _api("GET", f"/tasks/{tid}/sandbox/sessions/{session_id}/transcript")
    if as_json:
        _json_out(data)
    else:
        for line in data.get("transcript", []):
            click.echo(f"[{line.get('offset')}] {line.get('type')}: {line.get('data')}")


@session_app.command("permit")
def session_permit(
    session_id: Annotated[str, typer.Argument()],
    task: Annotated[Optional[str], typer.Option("--task")] = None,
    approve: Annotated[bool, typer.Option("--approve/--deny")] = True,
    request_id: Annotated[Optional[str], typer.Option("--request-id")] = None,
    as_json: JsonFlag = False,
):
    """Approve or deny a pending permission request."""
    tid = _task_id(task)
    body: dict = {"approved": approve}
    if request_id:
        body["request_id"] = request_id
    data = _api("POST", f"/tasks/{tid}/sandbox/sessions/{session_id}/permissions", json=body)
    if as_json:
        _json_out(data)
    else:
        click.echo(f"approved={data.get('approved')}")


# --- Agent connections ---

connection_app = typer.Typer(no_args_is_help=True, name="connection")
sandbox_app.add_typer(connection_app, name="connection")


@connection_app.command("list")
def connection_list(as_json: JsonFlag = False):
    """List your agent provider connections."""
    data = _api("GET", "/users/me/agent-connections")
    if as_json:
        _json_out(data)
    else:
        conns = data.get("connections", [])
        if not conns:
            click.echo("No agent connections configured.")
        for c in conns:
            click.echo(f"{c.get('provider')}  status={c.get('status')}  auth={c.get('auth_mode')}")


@connection_app.command("add")
def connection_add(
    provider: Annotated[str, typer.Argument(help="claude_code, codex, or opencode")],
    credential: Annotated[Optional[str], typer.Option("--credential", "-c", help="API key or token")] = None,
    auth_mode: Annotated[str, typer.Option(help="api_key, browser_oauth, device_code, auth_file")] = "api_key",
    browser: Annotated[bool, typer.Option("--browser", help="Open browser for OAuth")] = False,
    as_json: JsonFlag = False,
):
    """Begin or complete an agent connection."""
    if auth_mode == "api_key" and credential:
        data = _api("POST", f"/users/me/agent-connections/{provider}/complete", json={"credential": credential})
    elif browser or auth_mode == "browser_oauth":
        data = _api("POST", f"/users/me/agent-connections/{provider}/begin", json={"auth_mode": "browser_oauth"})
        url = data.get("browser_url")
        if url:
            click.echo(f"Opening browser: {url}")
            import webbrowser
            webbrowser.open(url)
            click.echo("Waiting for auth to complete... (Ctrl+C to cancel)")
            import time
            for _ in range(90):
                time.sleep(2)
                status = _api("GET", f"/users/me/agent-connections/{provider}/status")
                if status.get("status") == "connected":
                    click.echo(f"{provider} connected!")
                    return
            click.echo("Timed out waiting for auth. Check status with: hive sandbox connection list")
            return
    else:
        data = _api("POST", f"/users/me/agent-connections/{provider}/begin", json={"auth_mode": auth_mode})
    if as_json:
        _json_out(data)
    else:
        click.echo(f"{data.get('provider')}  status={data.get('status')}")


@connection_app.command("remove")
def connection_remove(
    provider: Annotated[str, typer.Argument(help="claude_code, codex, or opencode")],
    as_json: JsonFlag = False,
):
    """Remove an agent connection."""
    data = _api("DELETE", f"/users/me/agent-connections/{provider}")
    if as_json:
        _json_out(data)
    else:
        click.echo("removed")
