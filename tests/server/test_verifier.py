import asyncio
import json
from datetime import timedelta

from hive.server.db import get_db_sync, now
from hive.server.verification import DEFAULT_STALE_AFTER
from hive.server.verifier import claim_next_job, parse_score, requeue_stale_jobs, verify_run


def _insert_verifiable_task(task_id="tv1"):
    with get_db_sync() as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, config, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                task_id,
                "Verified Task",
                "A test task",
                "https://github.com/test/test",
                json.dumps({"verify": True, "mutable_paths": ["agent.py"]}),
                now(),
            ),
        )


class FakeExecResult:
    def __init__(self, exit_code=0, result=""):
        self.exit_code = exit_code
        self.result = result


class FakeGit:
    def __init__(self):
        self.clones = []

    async def clone(self, **kwargs):
        self.clones.append(kwargs)


class FakeProcess:
    def __init__(self, eval_result: FakeExecResult):
        self.eval_result = eval_result
        self.calls = []

    async def exec(self, command, cwd=None, timeout=None):
        self.calls.append((command, cwd, timeout))
        if command.startswith("test -f "):
            return FakeExecResult(1, "")
        if "eval/eval.sh" in command:
            return self.eval_result
        return FakeExecResult(0, "")


class FakeSandbox:
    def __init__(self, eval_result: FakeExecResult):
        self.git = FakeGit()
        self.process = FakeProcess(eval_result)


class FakeDaytona:
    def __init__(self, sandbox: FakeSandbox):
        self.sandbox = sandbox
        self.created = []
        self.deleted = []

    async def create(self, *args, **kwargs):
        self.created.append((args, kwargs))
        return self.sandbox

    async def delete(self, sandbox, timeout=60):
        self.deleted.append((sandbox, timeout))


class TestParseScore:
    def test_accuracy_colon(self):
        assert parse_score("accuracy: 0.4200") == 0.42

    def test_score_equals(self):
        assert parse_score("score=0.87") == 0.87

    def test_result_colon(self):
        assert parse_score("result: 0.95") == 0.95

    def test_case_insensitive(self):
        assert parse_score("ACCURACY: 0.55") == 0.55

    def test_multiline_picks_last_match(self):
        output = "accuracy:         0.4200\ncorrect:          42\ntotal:            100"
        assert parse_score(output) == 0.42

    def test_bare_float_fallback(self):
        assert parse_score("some log output\n0.91\n") == 0.91

    def test_returns_none_on_garbage(self):
        assert parse_score("no numbers here\njust text") is None

    def test_returns_none_on_empty(self):
        assert parse_score("") is None

    def test_structured_eval_output(self):
        output = (
            "---\n"
            "accuracy:         0.4200\n"
            "correct:          42\n"
            "total:            100\n"
        )
        # Scans from bottom; 'total' doesn't match the pattern, but 'accuracy' does.
        assert parse_score(output) == 0.42

    def test_score_in_middle_of_output(self):
        output = "Loading model...\nRunning eval...\nscore: 0.73\nDone."
        assert parse_score(output) == 0.73


class TestVerifyEndpoint:
    """Test the admin re-verify endpoint via the API."""

    def test_trigger_verify_sets_pending(self, registered_agent, monkeypatch, mock_github):
        monkeypatch.setattr("hive.server.main.ADMIN_KEY", "test-key")
        client, _, token = registered_agent
        _insert_verifiable_task("tv-verify")
        client.post("/api/tasks/tv-verify/clone", params={"token": token})
        submit = client.post(
            "/api/tasks/tv-verify/submit",
            params={"token": token},
            json={"sha": "abc123", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )
        assert submit.status_code == 201
        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.9, verification_status = 'success'"
                " WHERE id = %s",
                ("abc123",),
            )

        resp = client.post(
            "/api/tasks/tv-verify/runs/abc123/verify",
            headers={"X-Admin-Key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["verification_status"] == "pending"
        with get_db_sync() as conn:
            row = conn.execute(
                "SELECT verified, verified_score, verification_status FROM runs WHERE id = %s",
                ("abc123",),
            ).fetchone()
        assert row["verified"] is False
        assert row["verified_score"] is None
        assert row["verification_status"] == "pending"

    def test_trigger_verify_requires_admin(self, registered_agent, monkeypatch, mock_github):
        monkeypatch.setattr("hive.server.main.ADMIN_KEY", "test-key")
        client, _, token = registered_agent
        _insert_verifiable_task("tv-admin")
        client.post("/api/tasks/tv-admin/clone", params={"token": token})
        client.post(
            "/api/tasks/tv-admin/submit",
            params={"token": token},
            json={"sha": "admin123", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )
        resp = client.post(
            "/api/tasks/tv-admin/runs/admin123/verify",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 403


class TestVerifierWorker:
    def test_verify_run_success_updates_verified_score_and_task_stats(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-worker")
        clone = client.post("/api/tasks/tv-worker/clone", params={"token": token})
        assert clone.status_code == 201
        submit = client.post(
            "/api/tasks/tv-worker/submit",
            params={"token": token},
            json={"sha": "worker123", "branch": "main", "message": "m"},
        )
        assert submit.status_code == 201
        assert submit.json()["run"]["verification_status"] == "pending"

        job = asyncio.run(claim_next_job())
        assert job is not None

        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.75"))
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, job))

        with get_db_sync() as conn:
            run = conn.execute(
                "SELECT verified, verified_score, verification_status, verification_started_at"
                " FROM runs WHERE id = %s",
                ("worker123",),
            ).fetchone()
            task = conn.execute(
                "SELECT best_score, improvements FROM tasks WHERE id = %s",
                ("tv-worker",),
            ).fetchone()

        assert run["verified"] is True
        assert run["verified_score"] == 0.75
        assert run["verification_status"] == "success"
        assert run["verification_started_at"] is None
        assert task["best_score"] == 0.75
        assert task["improvements"] == 1
        assert daytona.deleted

    def test_missing_fork_run_does_not_block_queue(self, client):
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO agents (id, registered_at, last_seen_at, total_runs) VALUES (%s, %s, %s, 0)",
                ("agent-queue", now(), now()),
            )
            conn.execute(
                "INSERT INTO tasks (id, name, description, repo_url, config, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    "tv-queue",
                    "Verified Task",
                    "A test task",
                    "https://github.com/test/test",
                    json.dumps({"verify": True, "mutable_paths": ["agent.py"]}),
                    now(),
                ),
            )
            fork_id = conn.execute(
                "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, created_at)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    "tv-queue",
                    "agent-queue",
                    "https://github.com/test/fork",
                    "git@github.com:test/fork.git",
                    now(),
                ),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "missing-fork-run",
                    "tv-queue",
                    "agent-queue",
                    "main",
                    "missing fork",
                    "missing fork",
                    "pending",
                    now() - timedelta(seconds=5),
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status, created_at, fork_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "next-run",
                    "tv-queue",
                    "agent-queue",
                    "main",
                    "next",
                    "next",
                    "pending",
                    now(),
                    fork_id,
                ),
            )

        first_job = asyncio.run(claim_next_job())
        assert first_job is not None
        assert first_job.id == "missing-fork-run"
        assert first_job.fork_url is None

        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.75"))
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, first_job))

        with get_db_sync() as conn:
            first_run = conn.execute(
                "SELECT verification_status FROM runs WHERE id = %s",
                ("missing-fork-run",),
            ).fetchone()
        assert first_run["verification_status"] == "error"
        assert daytona.created == []

        second_job = asyncio.run(claim_next_job())
        assert second_job is not None
        assert second_job.id == "next-run"

    def test_requeue_stale_jobs_only_reclaims_old_running_rows(self, client):
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO agents (id, registered_at, last_seen_at, total_runs) VALUES (%s, %s, %s, 0)",
                ("agent-stale", now(), now()),
            )
            conn.execute(
                "INSERT INTO tasks (id, name, description, repo_url, config, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    "tv-stale",
                    "Verified Task",
                    "A test task",
                    "https://github.com/test/test",
                    json.dumps({"verify": True, "mutable_paths": ["agent.py"]}),
                    now(),
                ),
            )
            fork_id = conn.execute(
                "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, created_at)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    "tv-stale",
                    "agent-stale",
                    "https://github.com/test/fork",
                    "git@github.com:test/fork.git",
                    now(),
                ),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status,"
                " verification_started_at, created_at, fork_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "stale-run",
                    "tv-stale",
                    "agent-stale",
                    "main",
                    "stale",
                    "stale",
                    "running",
                    now() - timedelta(seconds=DEFAULT_STALE_AFTER + 5),
                    now(),
                    fork_id,
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status,"
                " verification_started_at, created_at, fork_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "fresh-run",
                    "tv-stale",
                    "agent-stale",
                    "main",
                    "fresh",
                    "fresh",
                    "running",
                    now(),
                    now(),
                    fork_id,
                ),
            )

        reclaimed = asyncio.run(requeue_stale_jobs())
        assert reclaimed == 1

        with get_db_sync() as conn:
            stale = conn.execute(
                "SELECT verification_status, verification_started_at FROM runs WHERE id = %s",
                ("stale-run",),
            ).fetchone()
            fresh = conn.execute(
                "SELECT verification_status, verification_started_at FROM runs WHERE id = %s",
                ("fresh-run",),
            ).fetchone()

        assert stale["verification_status"] == "pending"
        assert stale["verification_started_at"] is None
        assert fresh["verification_status"] == "running"
        assert fresh["verification_started_at"] is not None
