import json

import pytest

from hive.server.verification import (
    DEFAULT_EVAL_TIMEOUT,
    DEFAULT_PREPARE_TIMEOUT,
    DEFAULT_SANDBOX_SNAPSHOT,
    SandboxConfig,
    VerificationConfig,
    normalize_task_config,
    parse_task_config,
    recompute_task_stats,
    verification_config_from_raw,
)


class _FakeCursor:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class _FakeConn:
    def __init__(self, *, stats_row=None, task_row=None):
        self.stats_row = stats_row
        self.task_row = task_row
        self.stats_query = ""
        self.update_params = None

    async def execute(self, query, params=()):
        if query.startswith("SELECT config FROM tasks"):
            return _FakeCursor(self.task_row)
        if "WITH ranked AS" in query:
            self.stats_query = query
            return _FakeCursor(self.stats_row)
        if query.startswith("UPDATE tasks SET best_score"):
            self.update_params = params
            return _FakeCursor(None)
        raise AssertionError(f"unexpected query: {query}")


def test_parse_task_config_invalid_json_returns_empty_when_not_strict():
    assert parse_task_config("{") == {}


def test_parse_task_config_invalid_json_raises_when_strict():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_task_config("{", strict=True)


def test_normalize_task_config_canonicalizes_verification_values():
    raw, parsed, verification = normalize_task_config(
        {
            "verify": True,
            "verification_mode": "on_submit",
            "mutable_paths": ["agent.py/", "prompts//", "agent.py"],
            "prepare_timeout": 45,
            "eval_timeout": 90,
            "score_key": "score",
            "direction": "maximize",
            "result_format": "stdout_keyed",
            "sandbox": {"snapshot": DEFAULT_SANDBOX_SNAPSHOT},
        }
    )

    assert json.loads(raw) == parsed
    assert parsed == {
        "verify": True,
        "verification_mode": "on_submit",
        "mutable_paths": ["agent.py", "prompts"],
        "prepare_timeout": 45,
        "eval_timeout": 90,
        "score_key": "score",
        "direction": "maximize",
        "result_format": "stdout_keyed",
        "sandbox": {
            "snapshot": DEFAULT_SANDBOX_SNAPSHOT,
            "env": {},
            "secret_env": {},
            "volumes": [],
            "path_links": [],
            "network_block_all": None,
            "network_allow_list": None,
        },
    }
    assert verification == VerificationConfig(
        enabled=True,
        verification_mode="on_submit",
        mutable_paths=("agent.py", "prompts"),
        prepare_timeout=45,
        eval_timeout=90,
        score_key="score",
        direction="maximize",
        result_format="stdout_keyed",
        sandbox=SandboxConfig(snapshot=DEFAULT_SANDBOX_SNAPSHOT),
    )


def test_verification_config_from_raw_disables_verify_without_mutable_paths():
    config = verification_config_from_raw({"verify": True})

    assert config == VerificationConfig(
        enabled=False,
        mutable_paths=(),
        prepare_timeout=DEFAULT_PREPARE_TIMEOUT,
        eval_timeout=DEFAULT_EVAL_TIMEOUT,
    )


@pytest.mark.asyncio
async def test_recompute_task_stats_uses_verified_score_for_verified_tasks():
    conn = _FakeConn(stats_row={"best_score": 0.91, "improvements": 2})

    await recompute_task_stats(
        conn,
        "task-1",
        VerificationConfig(enabled=True, mutable_paths=("agent.py",)),
    )

    assert "verified_score" in conn.stats_query
    assert conn.update_params == (0.91, 2, "task-1")


@pytest.mark.asyncio
async def test_recompute_task_stats_loads_task_config_when_not_provided():
    conn = _FakeConn(
        task_row={"config": json.dumps({"verify": True, "mutable_paths": ["agent.py"]})},
        stats_row={"best_score": 0.75, "improvements": 1},
    )

    await recompute_task_stats(conn, "task-1")

    assert "verified_score" in conn.stats_query
    assert conn.update_params == (0.75, 1, "task-1")
