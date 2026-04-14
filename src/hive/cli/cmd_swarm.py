"""Manage concurrent agent swarms on a task."""

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from hive.cli.console import get_console
from hive.cli.formatting import ok, empty, relative_time
from hive.cli.helpers import _api, _server_url, _save_agent, _config, _save_config, _split_task_ref
from hive.cli.state import JsonFlag
from hive.cli.swarm_state import (
    load_swarm, save_swarm, delete_swarm, list_swarms,
    new_swarm_state, add_agent_to_state, refresh_statuses,
    stop_agent_process,
)

swarm_app = typer.Typer(no_args_is_help=True)

_DEFAULT_PROMPT = """\
You are an autonomous agent in a collaborative swarm. Multiple agents work on the same task. Results flow through the shared hive server.

1. Read program.md for task-specific instructions (what to modify, metric, rules).
2. Run: hive task context — to see the leaderboard, active claims, and feed.
3. Then loop:
   a. hive feed claim "what you are trying" — announce your experiment (expires 15 min)
   b. Modify code based on your hypothesis
   c. bash eval/eval.sh > run.log 2>&1 — run evaluation
   d. Extract the score from run.log (see program.md for the metric name)
   e. git add -A && git commit -m "description of change"
   f. hive push — push your code (works for both public and private tasks)
   g. hive run submit -m "description" --score <score> --parent <sha> --tldr "short summary"
      Use --parent none for your very first run.
   h. hive feed post "what I learned from this experiment"
   i. Check hive task context again and go back to (a)

Build on the best runs from the leaderboard. Share insights. Do not stop or ask for confirmation.\
"""


@swarm_app.callback()
def swarm_callback():
    """Manage agent swarms — spawn, monitor, and stop groups of agents."""


def _register_agents(count: int, prefix: str | None) -> list[dict]:
    agents = []
    try:
        payload = {"count": count}
        if prefix:
            payload["prefix"] = prefix
        data = _api("POST", "/register/batch", json=payload)
        agents = data["agents"]
    except click.ClickException:
        # Fallback to sequential registration if batch not available
        for i in range(count):
            name = f"{prefix}-{i + 1}" if prefix else None
            payload = {}
            if name:
                payload["preferred_name"] = name
            data = _api("POST", "/register", json=payload)
            agents.append({"id": data["id"], "token": data["token"]})
    # Save each agent locally
    for a in agents:
        _save_agent(a["id"], a["token"])
    return agents


def _clone_one(task_ref: str, agent: dict, base_dir: Path) -> dict:
    token = agent["token"]
    agent_id = agent["id"]
    owner, slug = _split_task_ref(task_ref)
    resp = _api("POST", f"/tasks/{owner}/{slug}/clone", params={"token": token})
    mode = resp.get("mode", "fork")
    ssh_url = resp["ssh_url"]
    private_key = resp.get("private_key", "")

    # Save deploy key
    key_dir = Path.home() / ".hive" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    fork_name = ssh_url.split("/")[-1].replace(".git", "")
    key_path = key_dir / fork_name
    if private_key:
        key_path.write_text(private_key)
        key_path.chmod(0o600)

    work_dir = base_dir / agent_id
    ssh_cmd = f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"

    result = subprocess.run(
        ["git", "clone", ssh_url, str(work_dir)],
        capture_output=True, text=True,
        env={**os.environ, "GIT_SSH_COMMAND": ssh_cmd},
    )
    if result.returncode != 0:
        raise click.ClickException(f"git clone failed for {agent_id}: {result.stderr}")

    subprocess.run(["git", "-C", str(work_dir), "config", "core.sshCommand", ssh_cmd],
                    capture_output=True, text=True)

    # Write .hive metadata
    hive_dir = work_dir / ".hive"
    hive_dir.mkdir(exist_ok=True)
    (hive_dir / "task").write_text(task_ref)
    (hive_dir / "agent").write_text(agent_id)

    if mode == "branch":
        # Branch mode: checkout initial branch, no upstream remote
        default_branch = resp.get("default_branch", "")
        if default_branch:
            subprocess.run(["git", "-C", str(work_dir), "checkout", default_branch],
                           capture_output=True, text=True)
        (hive_dir / "fork.json").write_text(json.dumps({
            "mode": "branch",
            "branch_prefix": resp.get("branch_prefix", ""),
            "key_path": str(key_path),
        }, indent=2))
    else:
        # Fork mode: add upstream remote
        upstream_url = resp.get("upstream_url", "")
        if upstream_url:
            subprocess.run(["git", "-C", str(work_dir), "remote", "add", "upstream", upstream_url],
                           capture_output=True, text=True)
        (hive_dir / "fork.json").write_text(json.dumps({
            "mode": "fork",
            "fork_url": resp.get("fork_url", ""), "key_path": str(key_path),
        }, indent=2))

    return {"agent_id": agent_id, "work_dir": str(work_dir), "key_path": str(key_path)}


def _start_agent_process(agent_id: str, work_dir: str, command: str | None,
                          task_ref: str, server_url: str,
                          skip_permissions: bool = False) -> tuple[int, str]:
    hive_dir = Path(work_dir) / ".hive"
    hive_dir.mkdir(exist_ok=True)
    log_file = str(hive_dir / "agent.log")

    if command is None:
        # Write default prompt to file and pipe it to claude via -p
        prompt_path = hive_dir / "prompt.md"
        prompt_path.write_text(_DEFAULT_PROMPT)
        escaped_path = str(prompt_path).replace("'", "'\\''")
        perm_flag = "--dangerously-skip-permissions" if skip_permissions else "--permission-mode auto"
        command = (
            f"claude -p \"$(cat '{escaped_path}')\""
            f" {perm_flag} --verbose --output-format stream-json"
        )

    # Find deploy key for this agent's fork
    key_dir = Path.home() / ".hive" / "keys"
    key_path = None
    for k in key_dir.glob(f"*--{agent_id}*"):
        key_path = str(k)
        break

    env = {**os.environ, "HIVE_SERVER": server_url, "HIVE_TASK": task_ref}
    if key_path:
        env["GIT_SSH_COMMAND"] = f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"

    with open(log_file, "w") as lf:
        proc = subprocess.Popen(
            command, shell=True, cwd=work_dir,
            stdin=subprocess.DEVNULL,
            stdout=lf, stderr=subprocess.STDOUT,
            env=env, start_new_session=True,
        )
    return proc.pid, log_file


@swarm_app.command("up")
def swarm_up(
    task_ref: Annotated[str, typer.Argument(help="Task to swarm on (OWNER/SLUG)")],
    agents: Annotated[int, typer.Option("--agents", "-n", help="Number of agents")] = 3,
    command: Annotated[Optional[str], typer.Option("--command", "-c", help="Agent command (default: claude with built-in prompt)")] = None,
    base_dir: Annotated[Optional[str], typer.Option("--dir", help="Base directory for work dirs")] = None,
    prefix: Annotated[Optional[str], typer.Option("--prefix", help="Agent name prefix")] = None,
    stagger: Annotated[int, typer.Option("--stagger", help="Seconds between agent starts")] = 30,
    dangerously_skip_permissions: Annotated[bool, typer.Option("--dangerously-skip-permissions", help="Skip all permission checks in spawned agents")] = False,
    as_json: JsonFlag = False,
):
    """Spawn N agents to work on a task concurrently."""
    console = get_console()
    # Legacy compat: bare slug -> hive/{slug}
    if "/" not in task_ref:
        task_ref = f"hive/{task_ref}"
    _owner, slug = _split_task_ref(task_ref)
    base = Path(base_dir) if base_dir else Path.cwd() / "hive-swarm" / slug
    base.mkdir(parents=True, exist_ok=True)
    server = _server_url()

    # Check existing swarm — state file keyed by slug
    state = load_swarm(slug)
    if state:
        state = refresh_statuses(state)
        running = [a for a in state["agents"] if a["status"] == "running"]
        stopped = [a for a in state["agents"] if a["status"] == "stopped"]

        if len(running) >= agents:
            console.print(f"[yellow]Swarm already has {len(running)} running agents.[/yellow]")
            _print_agent_table(console, state)
            return

        # Restart stopped agents
        for agent in stopped:
            pid, log_file = _start_agent_process(
                agent["agent_id"], agent["work_dir"], command, task_ref, server,
                skip_permissions=dangerously_skip_permissions)
            agent["pid"] = pid
            agent["log_file"] = log_file
            agent["status"] = "running"
            console.print(f"  Restarted [cyan]{agent['agent_id']}[/cyan] (PID {pid})")

        state = refresh_statuses(state)
        running = [a for a in state["agents"] if a["status"] == "running"]
        needed = agents - len(running)
        if needed <= 0:
            save_swarm(state)
            _print_agent_table(console, state)
            return
        agents = needed
        console.print(f"  Adding {needed} more agents...")
    else:
        state = new_swarm_state(slug, str(base), command or "claude (default prompt)")

    # Register agents
    with console.status("[bold]Registering agents...", spinner="dots"):
        new_agents = _register_agents(agents, prefix)
    names = [a["id"] for a in new_agents]
    console.print(f"[green]\u2713[/green] Registered {len(new_agents)} agents: {', '.join(names)}")

    # Clone forks (rate-limited concurrency)
    console.print("[bold]Cloning forks...[/bold]")
    clone_results = {}
    max_workers = min(3, len(new_agents))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_clone_one, task_ref, a, base): a for a in new_agents}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            agent = futures[future]
            try:
                result = future.result()
                clone_results[agent["id"]] = result
                console.print(f"  [{done_count}/{len(new_agents)}] [cyan]{agent['id']}[/cyan] cloned")
            except Exception as e:
                console.print(f"  [{done_count}/{len(new_agents)}] [red]{agent['id']}[/red] failed: {e}")

    # Start agent processes with stagger
    console.print(f"[bold]Starting agents ({stagger}s stagger)...[/bold]")
    for i, agent in enumerate(new_agents):
        if agent["id"] not in clone_results:
            continue
        cr = clone_results[agent["id"]]
        if i > 0 and stagger > 0:
            time.sleep(stagger)
        pid, log_file = _start_agent_process(
            agent["id"], cr["work_dir"], command, task_ref, server,
            skip_permissions=dangerously_skip_permissions)
        add_agent_to_state(state, agent["id"], agent["token"], pid, cr["work_dir"], log_file)
        console.print(f"  Started [cyan]{agent['id']}[/cyan] (PID {pid})")

    save_swarm(state)
    console.print()
    _print_agent_table(console, state)

    console.print()
    console.print(f"  [dim]hive swarm status {slug}[/dim]    — check progress")
    console.print(f"  [dim]hive swarm logs <agent>[/dim]        — watch an agent")
    console.print(f"  [dim]hive swarm stop {slug}[/dim]      — stop all")


@swarm_app.command("status")
def swarm_status(
    slug: Annotated[Optional[str], typer.Argument(help="Task slug (omit for all)")] = None,
    as_json: JsonFlag = False,
):
    """Show swarm status."""
    console = get_console()

    if slug:
        state = load_swarm(slug)
        if not state:
            raise click.ClickException(f"No swarm found for task '{slug}'")
        state = refresh_statuses(state)
        save_swarm(state)
        if as_json:
            from hive.cli.helpers import _json_out
            _json_out(state)
            return
        _print_agent_table(console, state)
        return

    swarms = list_swarms()
    if not swarms:
        empty("No active swarms. Run: hive swarm up <task-id> --agents N")
        return
    for s in swarms:
        s = refresh_statuses(s)
        save_swarm(s)
        running = sum(1 for a in s["agents"] if a["status"] == "running")
        total = len(s["agents"])
        console.print(f"  [cyan]{s['task_id']}[/cyan]  {running}/{total} running  (created {relative_time(s['created_at'])})")


@swarm_app.command("logs")
def swarm_logs(
    agent_name: Annotated[str, typer.Argument(help="Agent name")],
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow log output")] = False,
    tail: Annotated[int, typer.Option("--tail", "-n", help="Number of lines")] = 50,
):
    """View agent logs."""
    # Find the agent across all swarms
    log_file = None
    for s in list_swarms():
        for a in s["agents"]:
            if a["agent_id"] == agent_name:
                log_file = a.get("log_file")
                break
        if log_file:
            break

    if not log_file:
        raise click.ClickException(f"Agent '{agent_name}' not found in any swarm")
    if not Path(log_file).exists():
        raise click.ClickException(f"Log file not found: {log_file}")

    if follow:
        os.execvp("tail", ["tail", "-f", "-n", str(tail), log_file])
    else:
        result = subprocess.run(["tail", "-n", str(tail), log_file],
                                capture_output=True, text=True)
        click.echo(result.stdout)


@swarm_app.command("stop")
def swarm_stop(
    slug: Annotated[Optional[str], typer.Argument(help="Task slug (omit to stop all)")] = None,
    agent: Annotated[Optional[str], typer.Option("--agent", help="Stop a specific agent")] = None,
):
    """Stop running agents."""
    console = get_console()

    if slug:
        targets = [slug]
    else:
        targets = [s["task_id"] for s in list_swarms()]

    if not targets:
        empty("No active swarms.")
        return

    for tid in targets:
        state = load_swarm(tid)
        if not state:
            continue
        state = refresh_statuses(state)
        for a in state["agents"]:
            if agent and a["agent_id"] != agent:
                continue
            if a["status"] == "running":
                console.print(f"  Stopping [cyan]{a['agent_id']}[/cyan]...")
                stop_agent_process(a)
                console.print(f"  [green]\u2713[/green] Stopped {a['agent_id']}")
        save_swarm(state)

    ok("Done")


@swarm_app.command("down")
def swarm_down(
    slug: Annotated[str, typer.Argument(help="Task slug")],
    clean: Annotated[bool, typer.Option("--clean", help="Also remove work directories")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
):
    """Stop all agents and remove swarm state."""
    console = get_console()
    state = load_swarm(slug)
    if not state:
        raise click.ClickException(f"No swarm found for task '{slug}'")

    # Stop all running agents
    state = refresh_statuses(state)
    for a in state["agents"]:
        if a["status"] == "running":
            console.print(f"  Stopping [cyan]{a['agent_id']}[/cyan]...")
            stop_agent_process(a)

    if clean:
        base = Path(state["base_dir"])
        if base.exists():
            if not yes:
                click.confirm(f"Remove work directories at {base}?", abort=True)
            import shutil
            shutil.rmtree(base)
            console.print(f"  Removed {base}")

    delete_swarm(slug)
    ok(f"Swarm for '{slug}' removed")


def _print_agent_table(console, state):
    from rich.table import Table
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Agent", style="cyan")
    table.add_column("PID", justify="right")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Work Dir", style="dim")

    for a in state["agents"]:
        status = a.get("status", "unknown")
        style = "green" if status == "running" else "red" if status == "stopped" else "yellow"
        started = relative_time(a.get("started_at", "")) if a.get("started_at") else ""
        table.add_row(
            a["agent_id"],
            str(a.get("pid", "")),
            f"[{style}]{status}[/{style}]",
            started,
            a.get("work_dir", ""),
        )

    console.print(table)
