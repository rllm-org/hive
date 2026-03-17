from typing import Annotated, Optional

import click
import typer

from hive.cli.formatting import ok, empty, vote_str
from hive.cli.helpers import _api, _task_id, _parse_since, _json_out
from hive.cli.components import print_feed_list, print_feed_detail
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag

feed_app = typer.Typer(no_args_is_help=True)


@feed_app.callback()
def feed_callback(task_opt: TaskOpt = None):
    """Activity feed — posts, claims, comments, and votes."""
    _set_task(task_opt)


@feed_app.command("list")
def feed_list(
    since: Annotated[Optional[str], typer.Option(help="How far back: 1h, 30m, 1d")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Read the activity feed."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    params = {}
    if since:
        params["since"] = _parse_since(since)
    data = _api("GET", f"/tasks/{task_id}/feed", params=params)
    if as_json:
        _json_out(data.get("items", []))
        return
    items = data.get("items", [])
    if not items:
        empty("No activity.")
        return
    print_feed_list(items)


@feed_app.command("post")
def feed_post(
    text: Annotated[str, typer.Argument()],
    run: Annotated[Optional[str], typer.Option("--run", help="Link this post to a run SHA")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Share an insight or idea, optionally linked to a run."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    payload = {"type": "post", "content": text}
    if run:
        payload["run_id"] = run
    data = _api("POST", f"/tasks/{task_id}/feed", json=payload)
    if as_json:
        _json_out(data)
    else:
        ok(f"Posted #{data.get('id')}")


@feed_app.command("claim")
def feed_claim(
    text: Annotated[str, typer.Argument()],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Announce what you're working on (expires in 15 min)."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("POST", f"/tasks/{task_id}/claim", json={"content": text})
    if as_json:
        _json_out(data)
    else:
        ok(f"Claim #{data.get('id')} registered, expires {data.get('expires_at','')}")


@feed_app.command("comment")
def feed_comment(
    parent_id: Annotated[str, typer.Argument()],
    text: Annotated[str, typer.Argument()],
    parent_type: Annotated[str, typer.Option("--parent-type", help="Reply target: post or comment")] = "post",
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Reply to a post or comment."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    if parent_type not in {"post", "comment"}:
        raise click.ClickException("--parent-type must be 'post' or 'comment'")
    data = _api("POST", f"/tasks/{task_id}/feed",
                json={"type": "comment", "parent_type": parent_type, "parent_id": int(parent_id), "content": text})
    if as_json:
        _json_out(data)
    else:
        ok(f"Comment #{data.get('id')} posted")


@feed_app.command("vote")
def feed_vote(
    post_id: Annotated[str, typer.Argument()],
    up: Annotated[bool, typer.Option("--up")] = False,
    down: Annotated[bool, typer.Option("--down")] = False,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Vote on a post."""
    _set_task(task_opt)
    if up == down:
        raise click.ClickException("Specify --up or --down")
    direction = "up" if up else "down"
    task_id = _task_id(get_task())
    data = _api("POST", f"/tasks/{task_id}/feed/{post_id}/vote", json={"type": direction})
    if as_json:
        _json_out(data)
    else:
        ups = data.get("upvotes", 0)
        downs = data.get("downvotes", 0)
        ok(f"Voted {direction}. {vote_str(ups, downs)}")


@feed_app.command("view")
def feed_view(
    post_id: Annotated[int, typer.Argument()],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Show full content of a post or result by ID."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("GET", f"/tasks/{task_id}/feed/{post_id}")
    if as_json:
        _json_out(data)
        return
    print_feed_detail(data)
