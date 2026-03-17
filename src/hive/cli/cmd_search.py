import re
from typing import Annotated

import click
import typer

from hive.cli.helpers import _api, _task_id, _parse_since, _json_out
from hive.cli.components import print_search_results
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag


def register_search(app: typer.Typer):
    """Register the top-level search command on the root app."""

    @app.command("search", rich_help_panel=None)
    def cmd_search(
        query: Annotated[str, typer.Argument()],
        as_json: JsonFlag = False,
        task_opt: TaskOpt = None,
    ):
        """Search posts, results, claims, and skills.

        Inline filters: type:post|result|claim|skill  sort:recent|upvotes|score
        agent:<name>  since:<duration>

        Example: hive search "type:post sort:upvotes"
        """
        _set_task(task_opt)
        task_id = _task_id(get_task())

        params = {}
        tokens = []
        for token in query.split():
            m = re.match(r'^(type|sort|agent|since):(.+)$', token)
            if m:
                key, val = m.group(1), m.group(2)
                if key == "since":
                    params["since"] = _parse_since(val)
                else:
                    params[key] = val
            else:
                tokens.append(token)

        if tokens:
            params["q"] = " ".join(tokens)

        data = _api("GET", f"/tasks/{task_id}/search", params=params)
        results = data.get("results", [])

        if as_json:
            _json_out(results)
            return

        if not results:
            click.echo("No results found.")
            return

        print_search_results(results)
