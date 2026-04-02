import json
from datetime import timedelta, timezone, datetime

import psycopg

import hive.server.db as _db
from hive.cli.hive import hive


def _post_task(task_id="cli-items"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, %s, %s, %s, %s, 0)",
            (task_id, task_id, "test", "https://github.com/test", _db.now()),
        )


class TestItemMine:
    def test_lists_items_assigned_to_current_agent(self, cli_env):
        _post_task()
        cli_env.invoke(hive, ["auth", "register", "--name", "cli-agent"])
        cli_env.invoke(hive, ["auth", "register", "--name", "other-agent"])

        cli_env.invoke(
            hive,
            ["--task", "cli-items", "item", "create", "--title", "Mine", "--assignee", "cli-agent", "--status", "in_progress"],
        )
        cli_env.invoke(
            hive,
            ["--task", "cli-items", "item", "create", "--title", "Theirs", "--assignee", "other-agent", "--status", "review"],
        )

        result = cli_env.invoke(hive, ["--task", "cli-items", "item", "mine", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert [item["title"] for item in data] == ["Mine"]
        assert data[0]["assignee_id"] == "cli-agent"

    def test_omits_expired_assignments(self, cli_env):
        _post_task("cli-expiry")
        cli_env.invoke(hive, ["auth", "register", "--name", "cli-agent"])

        create = cli_env.invoke(
            hive,
            ["--task", "cli-expiry", "item", "create", "--title", "Expiring", "--assignee", "cli-agent", "--status", "in_progress", "--json"],
        )
        assert create.exit_code == 0
        item_id = json.loads(create.output)["id"]

        expired_at = datetime.now(timezone.utc) - timedelta(hours=3)
        with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
            conn.execute(
                "UPDATE items SET assigned_at = %s WHERE id = %s",
                (expired_at, item_id),
            )

        result = cli_env.invoke(hive, ["--task", "cli-expiry", "item", "mine", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []
