import asyncio
import json
from datetime import timedelta

import pytest

from hive.server.db import get_db_sync, now
from hive.server.verification import DEFAULT_STALE_AFTER
from hive.server.verifier import (
    _create_sandbox_with_retry,
    _effective_pool_max,
    _run_one_job,
    claim_next_job,
    parse_score,
    requeue_stale_jobs,
    verify_run,
)


def _insert_task(slug="tv1", config=None, owner="hive"):
    with get_db_sync() as conn:
        row = conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, config, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                slug,
                owner,
                "Verified Task",
                "A test task",
                "https://github.com/test/test",
                json.dumps(config) if config is not None else None,
                now(),
            ),
        ).fetchone()
        return row["id"]


def _insert_verifiable_task(slug="tv1"):
    return _insert_task(
        slug,
        {
            "verify": True,
            "verification_mode": "on_submit",
            "mutable_paths": ["agent.py"],
            "score_key": "accuracy",
            "direction": "maximize",
            "result_format": "stdout_keyed",
            "sandbox": {"snapshot": "hive-verify-python"},
        },
    )


def _admin_headers(monkeypatch, key="test-key"):
    monkeypatch.setattr("hive.server.main.ADMIN_KEY", key)
    return {"X-Admin-Key": key}


def _submit_and_claim_job(client, token, slug, sha, *, score=None):
    clone = client.post(f"/api/tasks/hive/{slug}/clone", params={"token": token})
    assert clone.status_code == 201
    payload = {"sha": sha, "branch": "main", "message": "m", "tldr": "t"}
    if score is not None:
        payload["score"] = score
    submit = client.post(f"/api/tasks/hive/{slug}/submit", params={"token": token}, json=payload)
    assert submit.status_code == 201
    job = asyncio.run(claim_next_job())
    assert job is not None
    assert job.id == sha
    return job


def _load_run(run_id):
    with get_db_sync() as conn:
        return conn.execute(
            "SELECT verified, verified_score, verification_status, verification_log, verified_at,"
            " verification_started_at FROM runs WHERE id = %s",
            (run_id,),
        ).fetchone()


@pytest.fixture(autouse=True)
def _fake_daytona_snapshot_params(monkeypatch):
    class FakeSnapshotParams:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("hive.server.verifier.CreateSandboxFromSnapshotParams", FakeSnapshotParams)


class FakeExecResult:
    def __init__(self, exit_code=0, result=""):
        self.exit_code = exit_code
        self.result = result


class FakeGit:
    def __init__(self, clone_error=None):
        self.clones = []
        self.clone_error = clone_error

    async def clone(self, **kwargs):
        self.clones.append(kwargs)
        if self.clone_error is not None:
            raise self.clone_error


class FakeProcess:
    def __init__(
        self,
        eval_result: FakeExecResult,
        *,
        prepare_exists: bool = False,
        prepare_result: FakeExecResult | None = None,
        overlay_result: FakeExecResult | None = None,
    ):
        self.eval_result = eval_result
        self.prepare_exists = prepare_exists
        self.prepare_result = prepare_result
        self.overlay_result = overlay_result
        self.calls = []

    async def exec(self, command, cwd=None, timeout=None):
        self.calls.append((command, cwd, timeout))
        if command.startswith("test -f "):
            return FakeExecResult(0 if self.prepare_exists else 1, "")
        if "cp -R" in command and self.overlay_result is not None:
            return self.overlay_result
        if command == "bash prepare.sh" and self.prepare_result is not None:
            return self.prepare_result
        if "eval/eval.sh" in command:
            return self.eval_result
        return FakeExecResult(0, "")


class FakeFileSystem:
    def __init__(self):
        self.uploads = []

    async def upload_file(self, content, remote_path, timeout=None):
        self.uploads.append((content, remote_path, timeout))


class FakeSandbox:
    def __init__(
        self,
        eval_result: FakeExecResult,
        *,
        prepare_exists: bool = False,
        prepare_result: FakeExecResult | None = None,
        overlay_result: FakeExecResult | None = None,
        clone_error=None,
    ):
        self.git = FakeGit(clone_error=clone_error)
        self.process = FakeProcess(
            eval_result,
            prepare_exists=prepare_exists,
            prepare_result=prepare_result,
            overlay_result=overlay_result,
        )
        self.fs = FakeFileSystem()


class FakeDaytona:
    def __init__(self, sandbox: FakeSandbox, *, create_error=None):
        self.sandbox = sandbox
        self.created = []
        self.deleted = []
        self.create_error = create_error

    async def create(self, *args, **kwargs):
        self.created.append((args, kwargs))
        if self.create_error is not None:
            raise self.create_error
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
        assert parse_score("some log output\n0.91\n", result_format="stdout_last_float") == 0.91

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
        client, _, token = registered_agent
        _insert_verifiable_task("tv-verify")
        client.post("/api/tasks/hive/tv-verify/clone", params={"token": token})
        submit = client.post(
            "/api/tasks/hive/tv-verify/submit",
            params={"token": token},
            json={"sha": "abc123", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )
        assert submit.status_code == 201
        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.9, verification_status = 'success',"
                " verification_log = 'old log', verified_at = %s"
                " WHERE id = %s",
                (now(), "abc123"),
            )

        resp = client.post(
            "/api/tasks/hive/tv-verify/runs/abc123/verify",
            headers=_admin_headers(monkeypatch),
        )
        assert resp.status_code == 200
        assert resp.json()["verification_status"] == "pending"
        with get_db_sync() as conn:
            row = conn.execute(
                "SELECT verified, verified_score, verification_status, verification_log, verified_at"
                " FROM runs WHERE id = %s",
                ("abc123",),
            ).fetchone()
        assert row["verified"] is False
        assert row["verified_score"] is None
        assert row["verification_status"] == "pending"
        assert row["verification_log"] is None
        assert row["verified_at"] is None

    def test_trigger_verify_requires_admin(self, registered_agent, monkeypatch, mock_github):
        monkeypatch.setattr("hive.server.main.ADMIN_KEY", "test-key")
        client, _, token = registered_agent
        _insert_verifiable_task("tv-admin")
        client.post("/api/tasks/hive/tv-admin/clone", params={"token": token})
        client.post(
            "/api/tasks/hive/tv-admin/submit",
            params={"token": token},
            json={"sha": "admin123", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )
        resp = client.post(
            "/api/tasks/hive/tv-admin/runs/admin123/verify",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    def test_trigger_verify_recomputes_task_stats_when_requeued(self, registered_agent, monkeypatch, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-requeue")
        client.post("/api/tasks/hive/tv-requeue/clone", params={"token": token})
        submit = client.post(
            "/api/tasks/hive/tv-requeue/submit",
            params={"token": token},
            json={"sha": "requeue123", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )
        assert submit.status_code == 201

        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.9, verification_status = 'success'"
                " WHERE id = %s",
                ("requeue123",),
            )
            conn.execute(
                "UPDATE tasks SET best_score = 0.9, improvements = 1 WHERE owner = %s AND slug = %s",
                ("hive", "tv-requeue"),
            )

        resp = client.post(
            "/api/tasks/hive/tv-requeue/runs/requeue123/verify",
            headers=_admin_headers(monkeypatch),
        )
        assert resp.status_code == 200

        task = client.get("/api/tasks/hive/tv-requeue").json()
        assert task["stats"]["best_score"] is None
        assert task["stats"]["improvements"] == 0

    def test_trigger_verify_rejects_disabled_tasks(self, registered_agent, monkeypatch):
        client, _, _ = registered_agent
        _insert_task("tv-disabled", {"verify": False})

        resp = client.post(
            "/api/tasks/hive/tv-disabled/runs/abc123/verify",
            headers=_admin_headers(monkeypatch),
        )
        assert resp.status_code == 400
        assert "not enabled" in resp.json()["detail"]

    def test_trigger_verify_returns_404_for_missing_run(self, registered_agent, monkeypatch):
        client, _, _ = registered_agent
        _insert_verifiable_task("tv-missing")

        resp = client.post(
            "/api/tasks/hive/tv-missing/runs/nope/verify",
            headers=_admin_headers(monkeypatch),
        )
        assert resp.status_code == 404

    def test_trigger_verify_rejects_ambiguous_prefix(self, registered_agent, monkeypatch, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-ambiguous")
        client.post("/api/tasks/hive/tv-ambiguous/clone", params={"token": token})
        client.post(
            "/api/tasks/hive/tv-ambiguous/submit",
            params={"token": token},
            json={"sha": "abc12345", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )
        client.post(
            "/api/tasks/hive/tv-ambiguous/submit",
            params={"token": token},
            json={"sha": "abc12367", "branch": "main", "score": 0.6, "tldr": "t", "message": "m"},
        )

        resp = client.post(
            "/api/tasks/hive/tv-ambiguous/runs/abc123/verify",
            headers=_admin_headers(monkeypatch),
        )
        assert resp.status_code == 400
        assert "ambiguous" in resp.json()["detail"]

    def test_trigger_verify_rejects_runs_without_fork(self, registered_agent, monkeypatch):
        client, agent_id, _ = registered_agent
        task_id = _insert_verifiable_task("tv-no-fork")
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                ("nofork123", task_id, agent_id, "main", "t", "m", "pending", now()),
            )

        resp = client.post(
            "/api/tasks/hive/tv-no-fork/runs/nofork123/verify",
            headers=_admin_headers(monkeypatch),
        )
        assert resp.status_code == 400
        assert "no fork" in resp.json()["detail"].lower()

    def test_trigger_verify_rejects_running_runs(self, registered_agent, monkeypatch, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-running")
        client.post("/api/tasks/hive/tv-running/clone", params={"token": token})
        client.post(
            "/api/tasks/hive/tv-running/submit",
            params={"token": token},
            json={"sha": "running123", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )
        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verification_status = 'running' WHERE id = %s",
                ("running123",),
            )

        resp = client.post(
            "/api/tasks/hive/tv-running/runs/running123/verify",
            headers=_admin_headers(monkeypatch),
        )
        assert resp.status_code == 409

    def test_trigger_verify_missing_header_returns_403(self, registered_agent, monkeypatch, mock_github):
        monkeypatch.setattr("hive.server.main.ADMIN_KEY", "test-key")
        client, _, token = registered_agent
        _insert_verifiable_task("tv-missing-header")
        client.post("/api/tasks/hive/tv-missing-header/clone", params={"token": token})
        client.post(
            "/api/tasks/hive/tv-missing-header/submit",
            params={"token": token},
            json={"sha": "missinghdr1", "branch": "main", "score": 0.5, "tldr": "t", "message": "m"},
        )

        resp = client.post("/api/tasks/hive/tv-missing-header/runs/missinghdr1/verify")
        assert resp.status_code == 403


class TestVerifierWorker:
    def test_verify_run_success_updates_verified_score_and_task_stats(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-worker")
        clone = client.post("/api/tasks/hive/tv-worker/clone", params={"token": token})
        assert clone.status_code == 201
        submit = client.post(
            "/api/tasks/hive/tv-worker/submit",
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

        run = _load_run("worker123")
        with get_db_sync() as conn:
            task = conn.execute(
                "SELECT best_score, improvements FROM tasks WHERE owner = %s AND slug = %s",
                ("hive", "tv-worker"),
            ).fetchone()

        assert run["verified"] is True
        assert run["verified_score"] == 0.75
        assert run["verification_status"] == "success"
        assert "eval/eval.sh" in run["verification_log"]
        assert run["verified_at"] is not None
        assert run["verification_started_at"] is None
        assert task["best_score"] == 0.75
        assert task["improvements"] == 1
        assert daytona.deleted

    def test_verify_run_marks_failed_when_eval_exits_nonzero(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-eval-fail")
        job = _submit_and_claim_job(client, token, "tv-eval-fail", "evalfail1")

        sandbox = FakeSandbox(FakeExecResult(1, "eval boom"))
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, job))

        run = _load_run("evalfail1")
        assert run["verified"] is False
        assert run["verified_score"] is None
        assert run["verification_status"] == "failed"
        assert "eval/eval.sh" in run["verification_log"]
        assert run["verified_at"] is None
        assert daytona.deleted

    def test_verify_run_marks_failed_when_output_is_unparseable(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-unparseable")
        job = _submit_and_claim_job(client, token, "tv-unparseable", "noscore1")

        sandbox = FakeSandbox(FakeExecResult(0, "not a score"))
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, job))

        run = _load_run("noscore1")
        assert run["verified"] is False
        assert run["verified_score"] is None
        assert run["verification_status"] == "failed"
        assert "Could not parse score" in run["verification_log"]
        assert run["verified_at"] is None

    def test_verify_run_marks_failed_when_prepare_step_errors(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-prepare-fail")
        job = _submit_and_claim_job(client, token, "tv-prepare-fail", "preparefail1")

        sandbox = FakeSandbox(
            FakeExecResult(0, "accuracy: 0.99"),
            prepare_exists=True,
            prepare_result=FakeExecResult(1, "prepare boom"),
        )
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, job))

        run = _load_run("preparefail1")
        assert run["verification_status"] == "failed"
        assert "prepare.sh" in run["verification_log"]
        assert run["verified_score"] is None

    def test_verify_run_marks_failed_when_overlay_errors(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-overlay-fail")
        job = _submit_and_claim_job(client, token, "tv-overlay-fail", "overlayfail1")

        sandbox = FakeSandbox(
            FakeExecResult(0, "accuracy: 0.99"),
            overlay_result=FakeExecResult(1, "copy boom"),
        )
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, job))

        run = _load_run("overlayfail1")
        assert run["verification_status"] == "failed"
        assert "overlay agent.py" in run["verification_log"]
        assert run["verified_score"] is None

    def test_verify_run_marks_error_when_verification_is_disabled(self, client):
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO agents (id, registered_at, last_seen_at, total_runs) VALUES (%s, %s, %s, 0)",
                ("agent-disabled", now(), now()),
            )
        tid = _insert_task("tv-disabled-worker", {"verify": True})
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status,"
                " verification_config, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "disabled1",
                    tid,
                    "agent-disabled",
                    "main",
                    "t",
                    "m",
                    "pending",
                    json.dumps({"verify": False}),
                    now(),
                ),
            )

        job = asyncio.run(claim_next_job())
        assert job is not None
        assert job.id == "disabled1"
        assert job.config.enabled is False

        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.8"))
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, job))

        run = _load_run("disabled1")
        assert run["verification_status"] == "error"
        assert run["verification_log"] == "Task verification is not enabled"
        assert daytona.created == []

    def test_verify_run_marks_error_when_sandbox_creation_raises(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-create-error")
        job = _submit_and_claim_job(client, token, "tv-create-error", "createerr1")

        daytona = FakeDaytona(
            FakeSandbox(FakeExecResult(0, "accuracy: 0.8")),
            create_error=RuntimeError("sandbox boom"),
        )
        asyncio.run(verify_run(daytona, job))

        run = _load_run("createerr1")
        assert run["verification_status"] == "error"
        assert run["verification_log"] == "sandbox boom"
        assert daytona.deleted == []

    def test_verify_run_marks_error_when_clone_raises(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-clone-error")
        job = _submit_and_claim_job(client, token, "tv-clone-error", "cloneerr1")

        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.8"), clone_error=RuntimeError("clone boom"))
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, job))

        run = _load_run("cloneerr1")
        assert run["verification_status"] == "error"
        assert run["verification_log"] == "clone boom"
        assert daytona.deleted

    def test_failed_verification_does_not_block_next_job(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-failed-queue")
        client.post("/api/tasks/hive/tv-failed-queue/clone", params={"token": token})
        client.post(
            "/api/tasks/hive/tv-failed-queue/submit",
            params={"token": token},
            json={"sha": "failedfirst1", "branch": "main", "message": "m", "tldr": "t"},
        )
        client.post(
            "/api/tasks/hive/tv-failed-queue/submit",
            params={"token": token},
            json={"sha": "failednext1", "branch": "main", "message": "m", "tldr": "t"},
        )

        first_job = asyncio.run(claim_next_job())
        assert first_job is not None
        assert first_job.id == "failedfirst1"

        sandbox = FakeSandbox(FakeExecResult(1, "eval boom"))
        daytona = FakeDaytona(sandbox)
        asyncio.run(verify_run(daytona, first_job))

        first_run = _load_run("failedfirst1")
        assert first_run["verification_status"] == "failed"

        second_job = asyncio.run(claim_next_job())
        assert second_job is not None
        assert second_job.id == "failednext1"

    def test_missing_fork_run_does_not_block_queue(self, client):
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO agents (id, registered_at, last_seen_at, total_runs) VALUES (%s, %s, %s, 0)",
                ("agent-queue", now(), now()),
            )
            tid = conn.execute(
                "INSERT INTO tasks (slug, owner, name, description, repo_url, config, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    "tv-queue",
                    "hive",
                    "Verified Task",
                    "A test task",
                    "https://github.com/test/test",
                    json.dumps({"verify": True, "mutable_paths": ["agent.py"]}),
                    now(),
                ),
            ).fetchone()["id"]
            fork_id = conn.execute(
                "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, created_at)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    tid,
                    "agent-queue",
                    "https://github.com/test/fork",
                    "git@github.com:test/fork.git",
                    now(),
                ),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status,"
                " task_repo_sha, verification_config, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "missing-fork-run",
                    tid,
                    "agent-queue",
                    "main",
                    "missing fork",
                    "missing fork",
                    "pending",
                    "task-base-sha",
                    json.dumps({"verify": True, "mutable_paths": ["agent.py"]}),
                    now() - timedelta(seconds=5),
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, verification_status,"
                " task_repo_sha, verification_config, created_at, fork_id)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "next-run",
                    tid,
                    "agent-queue",
                    "main",
                    "next",
                    "next",
                    "pending",
                    "task-base-sha",
                    json.dumps({"verify": True, "mutable_paths": ["agent.py"]}),
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
            tid = conn.execute(
                "INSERT INTO tasks (slug, owner, name, description, repo_url, config, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    "tv-stale",
                    "hive",
                    "Verified Task",
                    "A test task",
                    "https://github.com/test/test",
                    json.dumps({"verify": True, "mutable_paths": ["agent.py"]}),
                    now(),
                ),
            ).fetchone()["id"]
            fork_id = conn.execute(
                "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, created_at)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    tid,
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
                    tid,
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
                    tid,
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


class TestConcurrency:
    """Tests for the concurrency scheduler and pool sizing."""

    def test_effective_pool_max_default(self, monkeypatch):
        monkeypatch.setattr("hive.server.verifier.MAX_CONCURRENT_JOBS", 1)
        monkeypatch.setattr("hive.server.verifier.DB_POOL_MAX", 0)
        assert _effective_pool_max() == 4  # max(4, 1*2+2)

    def test_effective_pool_max_scales_with_concurrency(self, monkeypatch):
        monkeypatch.setattr("hive.server.verifier.MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("hive.server.verifier.DB_POOL_MAX", 0)
        assert _effective_pool_max() == 12  # max(4, 5*2+2)

    def test_effective_pool_max_explicit_override(self, monkeypatch):
        monkeypatch.setattr("hive.server.verifier.MAX_CONCURRENT_JOBS", 5)
        monkeypatch.setattr("hive.server.verifier.DB_POOL_MAX", 20)
        assert _effective_pool_max() == 20

    def test_run_one_job_returns_false_when_no_jobs(self, client):
        """No pending jobs → returns False, no crash."""
        result = asyncio.run(_run_one_job(0))
        assert result is False

    def test_run_one_job_processes_and_returns_true(self, registered_agent, mock_github, monkeypatch):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-concurrent")
        client.post("/api/tasks/hive/tv-concurrent/clone", params={"token": token})
        client.post(
            "/api/tasks/hive/tv-concurrent/submit",
            params={"token": token},
            json={"sha": "conc123", "branch": "main", "message": "m", "tldr": "t"},
        )

        class FakeAsyncDaytona:
            def __init__(self):
                self.sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.88"))
            async def __aenter__(self):
                return FakeDaytona(self.sandbox)
            async def __aexit__(self, *a):
                pass

        monkeypatch.setattr("hive.server.verifier.AsyncDaytona", FakeAsyncDaytona)
        result = asyncio.run(_run_one_job(0))
        assert result is True

        run = _load_run("conc123")
        assert run["verification_status"] == "success"
        assert run["verified_score"] == 0.88

    def test_run_one_job_handles_daytona_crash(self, registered_agent, mock_github, monkeypatch):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-daytona-crash")
        client.post("/api/tasks/hive/tv-daytona-crash/clone", params={"token": token})
        client.post(
            "/api/tasks/hive/tv-daytona-crash/submit",
            params={"token": token},
            json={"sha": "crash123", "branch": "main", "message": "m", "tldr": "t"},
        )

        class BrokenDaytona:
            async def __aenter__(self):
                raise RuntimeError("daytona down")
            async def __aexit__(self, *a):
                pass

        monkeypatch.setattr("hive.server.verifier.AsyncDaytona", BrokenDaytona)
        result = asyncio.run(_run_one_job(0))
        assert result is True  # job was claimed and processed (as error)

        run = _load_run("crash123")
        assert run["verification_status"] == "error"
        assert "Daytona client error" in run["verification_log"]

    def test_concurrent_claims_are_independent(self, client):
        """Two concurrent claim_next_job calls get different jobs."""
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO agents (id, registered_at, last_seen_at, total_runs) VALUES (%s, %s, %s, 0)",
                ("agent-conc", now(), now()),
            )
            tid = conn.execute(
                "INSERT INTO tasks (slug, owner, name, description, repo_url, config, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                ("tv-conc", "hive", "T", "T", "https://github.com/t/t",
                 json.dumps({"verify": True, "mutable_paths": ["a"]}), now()),
            ).fetchone()["id"]
            for sha in ["conc-a", "conc-b"]:
                conn.execute(
                    "INSERT INTO runs (id, task_id, agent_id, branch, tldr, message, score,"
                    " verification_status, verification_config, task_repo_sha, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (sha, tid, "agent-conc", "main", "t", "m", 1.0,
                     "pending", json.dumps({"verify": True, "mutable_paths": ["a"]}),
                     "sha1", now()),
                )

        job1 = asyncio.run(claim_next_job())
        job2 = asyncio.run(claim_next_job())
        assert job1 is not None
        assert job2 is not None
        assert job1.id != job2.id


class TestSandboxRetry:
    """Tests for sandbox creation retry logic."""

    def test_succeeds_on_first_try(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_verifiable_task("tv-retry-ok")
        job = _submit_and_claim_job(client, token, "tv-retry-ok", "retryok1")

        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.5"))
        daytona = FakeDaytona(sandbox)
        result = asyncio.run(_create_sandbox_with_retry(daytona, job))
        assert result is sandbox
        assert len(daytona.created) == 1

    def test_retries_on_transient_failure(self, registered_agent, mock_github, monkeypatch):
        monkeypatch.setattr("hive.server.verifier.SANDBOX_MAX_RETRIES", 3)
        monkeypatch.setattr("hive.server.verifier.SANDBOX_RETRY_BACKOFF", 0)  # no delay in tests

        client, _, token = registered_agent
        _insert_verifiable_task("tv-retry-transient")
        job = _submit_and_claim_job(client, token, "tv-retry-transient", "retrytrans1")

        call_count = 0
        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.5"))

        class RetryDaytona:
            def __init__(self):
                self.created = []

            async def create(self, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                self.created.append((args, kwargs))
                if call_count < 3:
                    raise RuntimeError("CPU limit exceeded")
                return sandbox

            async def delete(self, sb, timeout=60):
                pass

        daytona = RetryDaytona()
        result = asyncio.run(_create_sandbox_with_retry(daytona, job))
        assert result is sandbox
        assert call_count == 3  # failed twice, succeeded on third

    def test_retries_indefinitely_until_success(self, registered_agent, mock_github, monkeypatch):
        monkeypatch.setattr("hive.server.verifier.SANDBOX_MAX_RETRIES", 3)
        monkeypatch.setattr("hive.server.verifier.SANDBOX_RETRY_BACKOFF", 0)

        client, _, token = registered_agent
        _insert_verifiable_task("tv-retry-persist")
        job = _submit_and_claim_job(client, token, "tv-retry-persist", "retrypersist1")

        call_count = 0
        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.5"))

        class PersistRetryDaytona:
            def __init__(self):
                self.created = []

            async def create(self, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                self.created.append((args, kwargs))
                if call_count < 6:  # fail 5 times (well past old max of 3)
                    raise RuntimeError("CPU limit exceeded")
                return sandbox

            async def delete(self, sb, timeout=60):
                pass

        daytona = PersistRetryDaytona()
        result = asyncio.run(_create_sandbox_with_retry(daytona, job))
        assert result is sandbox
        assert call_count == 6  # retried 5 times, succeeded on 6th

    def test_backoff_is_capped(self, registered_agent, mock_github, monkeypatch):
        """Backoff caps at SANDBOX_RETRY_BACKOFF * SANDBOX_MAX_RETRIES."""
        monkeypatch.setattr("hive.server.verifier.SANDBOX_MAX_RETRIES", 2)
        monkeypatch.setattr("hive.server.verifier.SANDBOX_RETRY_BACKOFF", 10)

        client, _, token = registered_agent
        _insert_verifiable_task("tv-retry-cap")
        job = _submit_and_claim_job(client, token, "tv-retry-cap", "retrycap1")

        delays = []
        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            delays.append(seconds)

        monkeypatch.setattr("hive.server.verifier.asyncio.sleep", mock_sleep)

        call_count = 0
        sandbox = FakeSandbox(FakeExecResult(0, "accuracy: 0.5"))

        class CapDaytona:
            def __init__(self):
                self.created = []

            async def create(self, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                self.created.append((args, kwargs))
                if call_count < 5:
                    raise RuntimeError("CPU limit exceeded")
                return sandbox

            async def delete(self, sb, timeout=60):
                pass

        daytona = CapDaytona()
        asyncio.run(_create_sandbox_with_retry(daytona, job))
        # backoff: 10*1=10, 10*2=20, 10*3=20(capped), 10*4=20(capped)
        assert delays == [10, 20, 20, 20]
