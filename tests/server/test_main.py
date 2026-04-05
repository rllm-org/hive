"""Tests for all API endpoints."""

import io
import json
import tarfile

import pytest

from hive.server.main import _parse_sort


class TestParseSort:
    """Unit tests for _parse_sort helper (no DB needed)."""

    def test_default_desc(self):
        assert _parse_sort("score", {"score": "r.score", "recent": "r.created_at"}) == "r.score DESC"

    def test_explicit_desc(self):
        assert _parse_sort("score:desc", {"score": "r.score", "recent": "r.created_at"}) == "r.score DESC"

    def test_explicit_asc(self):
        assert _parse_sort("score:asc", {"score": "r.score", "recent": "r.created_at"}) == "r.score ASC"

    def test_case_insensitive_direction(self):
        assert _parse_sort("score:ASC", {"score": "r.score"}) == "r.score ASC"
        assert _parse_sort("score:Desc", {"score": "r.score"}) == "r.score DESC"

    def test_invalid_direction_defaults_desc(self):
        assert _parse_sort("score:invalid", {"score": "r.score"}) == "r.score DESC"

    def test_unknown_field_falls_back_to_first(self):
        assert _parse_sort("unknown", {"score": "r.score", "recent": "r.created_at"}) == "r.score DESC"

    def test_unknown_field_with_asc(self):
        assert _parse_sort("unknown:asc", {"score": "r.score"}) == "r.score ASC"

    def test_recent_asc(self):
        assert _parse_sort("recent:asc", {"score": "r.score", "recent": "r.created_at"}) == "r.created_at ASC"


class TestAuth:

    def test_signup(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "password123"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "verification_required"
        assert data["email"] == "a@b.com"

    def test_signup_duplicate_email(self, client):
        from tests.conftest import _create_verified_user
        _create_verified_user(client, "dup@b.com", "password123")
        resp = client.post("/api/auth/signup", json={"email": "dup@b.com", "password": "password456"})
        assert resp.status_code == 409

    def test_signup_short_password(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "short"})
        assert resp.status_code == 400

    def test_signup_invalid_email(self, client):
        resp = client.post("/api/auth/signup", json={"email": "notanemail", "password": "password123"})
        assert resp.status_code == 400

    def test_login(self, client):
        from tests.conftest import _create_verified_user
        _create_verified_user(client, "login@b.com", "password123")
        resp = client.post("/api/auth/login", json={"email": "login@b.com", "password": "password123"})
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_login_wrong_password(self, client):
        from tests.conftest import _create_verified_user
        _create_verified_user(client, "wrong@b.com", "password123")
        resp = client.post("/api/auth/login", json={"email": "wrong@b.com", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={"email": "nope@b.com", "password": "password123"})
        assert resp.status_code == 401

    def test_me(self, auth_user):
        client, token, user = auth_user
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"

    def test_me_no_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 422

    def test_me_invalid_token(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    def test_admin_role(self, admin_user):
        client, token, user = admin_user
        assert user["role"] == "admin"
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["role"] == "admin"


class TestAgentTokens:

    def test_register_returns_uuid_token(self, client):
        resp = client.post("/api/register")
        data = resp.json()
        assert data["token"] != data["id"]
        assert len(data["token"]) == 36  # UUID format

    def test_agent_auth_with_uuid_token(self, client, _seed_task):
        resp = client.post("/api/register")
        agent_token = resp.json()["token"]
        resp = client.get("/api/tasks/t1/runs", params={"token": agent_token})
        assert resp.status_code == 200

    def test_batch_register_returns_uuid_tokens(self, client):
        resp = client.post("/api/register/batch", json={"count": 2})
        agents = resp.json()["agents"]
        for a in agents:
            assert a["token"] != a["id"]
            assert len(a["token"]) == 36


class TestAgentClaim:

    def test_claim_agent(self, auth_user):
        client, jwt_token, user = auth_user
        resp = client.post("/api/register", json={"preferred_name": "claimable"})
        agent_token = resp.json()["token"]
        resp = client.post("/api/auth/claim",
                           json={"token": agent_token},
                           headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "claimable"
        assert resp.json()["status"] == "claimed"

    def test_claim_already_owned(self, auth_user):
        client, jwt_token, user = auth_user
        resp = client.post("/api/register", json={"preferred_name": "mine"})
        agent_token = resp.json()["token"]
        client.post("/api/auth/claim",
                    json={"token": agent_token},
                    headers={"Authorization": f"Bearer {jwt_token}"})
        # Claim again — idempotent
        resp = client.post("/api/auth/claim",
                           json={"token": agent_token},
                           headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_claimed"

    def test_claim_by_another_user(self, client):
        from tests.conftest import _create_verified_user
        # User 1 claims
        jwt1, _ = _create_verified_user(client, "u1@b.com", "password123")
        resp = client.post("/api/register", json={"preferred_name": "taken"})
        agent_token = resp.json()["token"]
        client.post("/api/auth/claim",
                    json={"token": agent_token},
                    headers={"Authorization": f"Bearer {jwt1}"})
        # User 2 tries to claim same agent
        jwt2, _ = _create_verified_user(client, "u2@b.com", "password123")
        resp = client.post("/api/auth/claim",
                           json={"token": agent_token},
                           headers={"Authorization": f"Bearer {jwt2}"})
        assert resp.status_code == 409

    def test_claim_invalid_token(self, auth_user):
        client, jwt_token, user = auth_user
        resp = client.post("/api/auth/claim",
                           json={"token": "nonexistent"},
                           headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 404

    def test_claim_requires_login(self, client):
        resp = client.post("/api/auth/claim", json={"token": "whatever"})
        assert resp.status_code == 422


def _make_tar(files: dict[str, str] = None) -> io.BytesIO:
    """Create a .tar.gz in memory with optional files."""
    if files is None:
        files = {"README.md": "hello"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf


def _post_task(
    client,
    id: str = "gsm8k",
    name: str = "GSM8K Solver",
    description: str = "A solver task",
    config: object | None = None,
    headers: dict[str, str] | None = None,
):
    """Create a task upload request, optionally with admin headers."""

    data = {"id": id, "name": name, "description": description}
    if config:
        data["config"] = config
    return client.post(
        "/api/tasks",
        data=data,
        files={"archive": ("task.tar.gz", _make_tar(), "application/gzip")},
        headers=headers or {"X-Admin-Key": "test-key"},
    )


def _insert_task(task_id="t1", name="Test Task", description="A test", config=None):
    from hive.server.db import get_db_sync, now

    with get_db_sync() as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, config, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                task_id,
                name,
                description,
                "https://github.com/test/test",
                json.dumps(config) if config is not None else None,
                now(),
            ),
        )


def _admin_headers(monkeypatch, key="test-key"):
    monkeypatch.setattr("hive.server.main.ADMIN_KEY", key)
    return {"X-Admin-Key": key}


class TestCreateTask:
    def test_create(self, client, monkeypatch):
        resp = _post_task(client, headers=_admin_headers(monkeypatch))
        assert resp.status_code == 201
        assert resp.json()["id"] == "gsm8k"
        assert resp.json()["repo_url"] == "https://github.com/hive-agents/task--gsm8k"
        assert resp.json()["status"] == "active"

    def test_description_too_long(self, client, monkeypatch):
        resp = _post_task(client, description="x" * 351, headers=_admin_headers(monkeypatch))
        assert resp.status_code == 400
        assert "350" in resp.json()["detail"]

    def test_duplicate_task(self, client, monkeypatch):
        headers = _admin_headers(monkeypatch)
        _post_task(client, id="t1", name="T", description="D", headers=headers)
        resp = _post_task(client, id="t1", name="T", description="D", headers=headers)
        assert resp.status_code == 409

    def test_missing_fields(self, client):
        h = {"X-Admin-Key": "test-key"}
        assert client.post("/api/tasks", data={}, files={"archive": ("t.tar.gz", _make_tar(), "application/gzip")}, headers=h).status_code == 422
        assert client.post("/api/tasks", data={"id": "x", "name": "X"},
                           files={"archive": ("t.tar.gz", _make_tar(), "application/gzip")}, headers=h).status_code == 422


class TestRegister:
    def test_register(self, client):
        resp = client.post("/api/register")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["token"]
        assert data["token"] != data["id"]

    def test_register_preferred_name(self, client):
        resp = client.post("/api/register", json={"preferred_name": "cool-bot"})
        assert resp.status_code == 201
        assert resp.json()["id"] == "cool-bot"

    def test_register_preferred_taken(self, client):
        client.post("/api/register", json={"preferred_name": "taken"})
        resp = client.post("/api/register", json={"preferred_name": "taken"})
        assert resp.status_code == 409


class TestListTasks:
    def test_empty(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks"] == []
        assert data["page"] == 1
        assert "per_page" in data
        assert data["has_next"] is False

    def test_search_by_name(self, client, _seed_task):
        resp = client.get("/api/tasks", params={"q": "Test"})
        assert len(resp.json()["tasks"]) == 1

    def test_search_by_description(self, client, _seed_task):
        resp = client.get("/api/tasks", params={"q": "test"})
        assert len(resp.json()["tasks"]) == 1

    def test_search_no_match(self, client, _seed_task):
        resp = client.get("/api/tasks", params={"q": "nonexistent"})
        assert resp.json()["tasks"] == []

    def test_task_has_stats_with_improvements(self, client, _seed_task):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert len(tasks) == 1
        assert "stats" in tasks[0]
        assert "improvements" in tasks[0]["stats"]


class TestGetTask:
    def test_not_found(self, client):
        resp = client.get("/api/tasks/nope")
        assert resp.status_code == 404


class TestPatchTask:
    def test_updates_name_and_description_without_admin(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.patch(
            "/api/tasks/t1",
            params={"token": token},
            json={"name": "Updated Task", "description": "Updated description"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Task"
        assert resp.json()["description"] == "Updated description"

        task = client.get("/api/tasks/t1").json()
        assert task["name"] == "Updated Task"
        assert task["description"] == "Updated description"

    def test_config_update_requires_admin(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.patch(
            "/api/tasks/t1",
            params={"token": token},
            json={"config": {"verify": True, "mutable_paths": ["agent.py"]}},
        )
        assert resp.status_code == 403

    @pytest.mark.parametrize(
        ("config", "detail_substr"),
        [
            ("{", "valid json"),
            ("[]", "json object"),
            ({"verify": "yes", "mutable_paths": ["agent.py"]}, "boolean"),
            (
                {
                    "verify": True,
                    "verification_mode": "manual",
                    "score_key": "accuracy",
                    "direction": "maximize",
                    "result_format": "stdout_keyed",
                    "sandbox": {"snapshot": "hive-verify-python"},
                },
                "mutable_paths",
            ),
            (
                {
                    "verify": True,
                    "verification_mode": "manual",
                    "mutable_paths": ["../agent.py"],
                    "score_key": "accuracy",
                    "direction": "maximize",
                    "result_format": "stdout_keyed",
                    "sandbox": {"snapshot": "hive-verify-python"},
                },
                "mutable_paths",
            ),
            (
                {
                    "verify": True,
                    "verification_mode": "manual",
                    "mutable_paths": ["agent.py"],
                    "score_key": "accuracy",
                    "direction": "maximize",
                    "result_format": "stdout_keyed",
                    "sandbox": {"snapshot": "hive-verify-python"},
                    "eval_timeout": 0,
                },
                "positive integer",
            ),
        ],
    )
    def test_config_update_rejects_invalid_values(self, registered_agent, _seed_task, monkeypatch, config, detail_substr):
        client, _, token = registered_agent
        resp = client.patch(
            "/api/tasks/t1",
            params={"token": token},
            headers=_admin_headers(monkeypatch),
            json={"config": config},
        )
        assert resp.status_code == 400
        assert detail_substr in resp.json()["detail"].lower()

    def test_config_update_normalizes_valid_values(self, registered_agent, _seed_task, monkeypatch):
        client, _, token = registered_agent
        resp = client.patch(
            "/api/tasks/t1",
            params={"token": token},
            headers=_admin_headers(monkeypatch),
            json={
                "config": {
                    "verify": True,
                    "verification_mode": "manual",
                    "mutable_paths": ["agent.py/", "prompts//", "agent.py"],
                    "prepare_timeout": 30,
                    "eval_timeout": 60,
                    "score_key": "accuracy",
                    "direction": "maximize",
                    "result_format": "stdout_keyed",
                    "sandbox": {
                        "snapshot": "hive-verify-python",
                        "env": {"SOLVER_MODEL": "gpt-5.4-mini"},
                    },
                }
            },
        )
        assert resp.status_code == 200
        assert resp.json()["config"] == {
            "verify": True,
            "verification_mode": "manual",
            "mutable_paths": ["agent.py", "prompts"],
            "prepare_timeout": 30,
            "eval_timeout": 60,
            "score_key": "accuracy",
            "direction": "maximize",
            "result_format": "stdout_keyed",
            "sandbox": {
                "snapshot": "hive-verify-python",
                "env": {"SOLVER_MODEL": "gpt-5.4-mini"},
                "secret_env": {},
                "volumes": [],
                "path_links": [],
                "network_block_all": None,
                "network_allow_list": None,
            },
        }

        task = client.get("/api/tasks/t1").json()
        assert task["config"] == {
            "verify": True,
            "verification_mode": "manual",
            "mutable_paths": ["agent.py", "prompts"],
            "prepare_timeout": 30,
            "eval_timeout": 60,
            "score_key": "accuracy",
            "direction": "maximize",
            "result_format": "stdout_keyed",
            "sandbox": {
                "snapshot": "hive-verify-python",
                "env": {"SOLVER_MODEL": "gpt-5.4-mini"},
                "secret_env": {},
                "volumes": [],
                "path_links": [],
                "network_block_all": None,
                "network_allow_list": None,
            },
        }


class TestSubmitRun:
    def test_submit(self, registered_agent, _seed_task):
        client, agent_id, token = registered_agent
        resp = client.post(
            "/api/tasks/t1/submit",
            params={"token": token},
            json={"sha": "abc123", "message": "did stuff", "score": 0.5},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["run"]["score"] == 0.5
        assert data["post_id"]

    def test_submit_no_sha(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post(
            "/api/tasks/t1/submit", params={"token": token}, json={"message": "hi"}
        )
        assert resp.status_code == 400

    def test_submit_bad_token(self, client, _seed_task):
        resp = client.post(
            "/api/tasks/t1/submit",
            params={"token": "fake"},
            json={"sha": "x", "message": "hi"},
        )
        assert resp.status_code == 401

    def test_submit_task_not_found(self, registered_agent):
        client, _, token = registered_agent
        resp = client.post(
            "/api/tasks/nope/submit",
            params={"token": token},
            json={"sha": "x", "message": "hi"},
        )
        assert resp.status_code == 404

    def test_submit_auto_fills_fork_id(self, registered_agent, _seed_task, mock_github):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/clone", params={"token": token})
        resp = client.post("/api/tasks/t1/submit", params={"token": token},
                          json={"sha": "forkrun1", "message": "test", "score": 0.5})
        assert resp.status_code == 201
        assert resp.json()["run"].get("fork_id") is not None

    def test_submit_without_fork_has_null_fork_id(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/submit", params={"token": token},
                          json={"sha": "nofork1", "message": "test", "score": 0.5})
        assert resp.status_code == 201
        assert resp.json()["run"].get("fork_id") is None

    def test_submit_invalid_score(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/submit", params={"token": token},
                          json={"sha": "badscore1", "message": "m", "score": "hello"})
        assert resp.status_code == 400
        assert "score" in resp.json()["detail"].lower()

    def test_submit_verifiable_run_requires_fork(self, registered_agent):
        client, _, token = registered_agent
        _insert_task("tv1", config={"verify": True, "mutable_paths": ["agent.py"]})
        resp = client.post(
            "/api/tasks/tv1/submit",
            params={"token": token},
            json={"sha": "verifyfork1", "message": "m", "score": 0.9},
        )
        assert resp.status_code == 400
        assert "fork" in resp.json()["detail"].lower()

    def test_submit_verifiable_run_sets_pending_without_updating_task_stats(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_task("tv2", config={"verify": True, "mutable_paths": ["agent.py"]})
        clone = client.post("/api/tasks/tv2/clone", params={"token": token})
        assert clone.status_code == 201

        resp = client.post(
            "/api/tasks/tv2/submit",
            params={"token": token},
            json={"sha": "verifypending1", "message": "m", "score": 0.9},
        )
        assert resp.status_code == 201
        run = resp.json()["run"]
        assert run["verification_status"] == "pending"
        assert run["verified_score"] is None
        task = client.get("/api/tasks/tv2").json()
        assert task["stats"]["best_score"] is None
        assert task["stats"]["improvements"] == 0

    def test_submit_verifiable_run_queues_even_without_reported_score(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_task("tv3", config={"verify": True, "mutable_paths": ["agent.py"]})
        clone = client.post("/api/tasks/tv3/clone", params={"token": token})
        assert clone.status_code == 201

        resp = client.post(
            "/api/tasks/tv3/submit",
            params={"token": token},
            json={"sha": "verifynull1", "message": "m"},
        )
        assert resp.status_code == 201
        run = resp.json()["run"]
        assert run["score"] is None
        assert run["verification_status"] == "pending"


class TestListRuns:
    def test_best_runs(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s2", "message": "m", "score": 0.7})
        resp = client.get("/api/tasks/t1/runs")
        assert resp.status_code == 200
        data = resp.json()
        runs = data["runs"]
        assert runs[0]["score"] >= runs[-1]["score"]
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_best_runs_excludes_null_scores(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "ns1", "message": "m"})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "ns2", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs")
        runs = resp.json()["runs"]
        assert all(r["score"] is not None for r in runs)

    def test_contributors_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s3", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs", params={"view": "contributors"})
        data = resp.json()
        assert data["view"] == "contributors"
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data
        # contributors entries have agent_id, total_runs, best_score, improvements
        entries = data["entries"]
        assert len(entries) == 1
        assert "agent_id" in entries[0]
        assert "total_runs" in entries[0]
        assert "best_score" in entries[0]
        assert "improvements" in entries[0]
        assert entries[0]["improvements"] >= 1

    def test_deltas_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "p1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "c1", "message": "m", "score": 0.6, "parent_id": "p1"})
        resp = client.get("/api/tasks/t1/runs", params={"view": "deltas"})
        data = resp.json()
        assert data["view"] == "deltas"
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_improvers_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "i1", "message": "m", "score": 0.2})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "i2", "message": "m", "score": 0.9})
        resp = client.get("/api/tasks/t1/runs", params={"view": "improvers"})
        data = resp.json()
        assert data["view"] == "improvers"
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_sort_score_asc(self, registered_agent, _seed_task):
        """sort=score:asc returns lowest score first."""
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "asc1", "message": "m", "score": 0.9})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "asc2", "message": "m", "score": 0.3})
        resp = client.get("/api/tasks/t1/runs", params={"sort": "score:asc"})
        runs = resp.json()["runs"]
        assert runs[0]["score"] <= runs[-1]["score"]

    def test_sort_score_desc_explicit(self, registered_agent, _seed_task):
        """sort=score:desc is equivalent to sort=score (default DESC)."""
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "desc1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "desc2", "message": "m", "score": 0.9})
        resp = client.get("/api/tasks/t1/runs", params={"sort": "score:desc"})
        runs = resp.json()["runs"]
        assert runs[0]["score"] >= runs[-1]["score"]

    def test_sort_invalid_direction_defaults_desc(self, registered_agent, _seed_task):
        """sort=score:invalid falls back to DESC."""
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "inv1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "inv2", "message": "m", "score": 0.9})
        resp = client.get("/api/tasks/t1/runs", params={"sort": "score:invalid"})
        runs = resp.json()["runs"]
        assert runs[0]["score"] >= runs[-1]["score"]

    def test_task_not_found(self, client):
        resp = client.get("/api/tasks/nope/runs")
        assert resp.status_code == 404

    def test_verified_only_uses_verified_score_even_without_reported_score(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_task("tv4", config={"verify": True, "mutable_paths": ["agent.py"]})
        client.post("/api/tasks/tv4/clone", params={"token": token})
        client.post(
            "/api/tasks/tv4/submit",
            params={"token": token},
            json={"sha": "verifiedonly1", "message": "m"},
        )
        client.post(
            "/api/tasks/tv4/submit",
            params={"token": token},
            json={"sha": "reportedonly1", "message": "m", "score": 0.95},
        )
        from hive.server.db import get_db_sync

        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.8, verification_status = 'success'"
                " WHERE id = %s",
                ("verifiedonly1",),
            )
        resp = client.get("/api/tasks/tv4/runs", params={"verified_only": True})
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert [run["id"] for run in runs] == ["verifiedonly1"]
        assert runs[0]["verified_score"] == 0.8


class TestGetRun:
    def test_get(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "r1", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs/r1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "r1"

    def test_not_found(self, client):
        resp = client.get("/api/tasks/t1/runs/nope")
        assert resp.status_code == 404

    def test_get_run_includes_fork_url(self, registered_agent, _seed_task, mock_github):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/clone", params={"token": token})
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "forksha1", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs/forksha1")
        assert resp.status_code == 200
        assert resp.json().get("fork_url") is not None

    def test_get_run_falls_back_to_repo_url(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "noforksha", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs/noforksha")
        assert resp.status_code == 200
        assert resp.json()["fork_url"] == "https://github.com/test/test"


class TestPatchRun:
    def test_invalidating_verified_run_recomputes_task_stats(self, registered_agent, monkeypatch, mock_github):
        from hive.server.db import get_db_sync

        client, _, token = registered_agent
        headers = _admin_headers(monkeypatch)
        _insert_task("tv-patch", config={"verify": True, "mutable_paths": ["agent.py"]})
        client.post("/api/tasks/tv-patch/clone", params={"token": token})
        client.post(
            "/api/tasks/tv-patch/submit",
            params={"token": token},
            json={"sha": "patchlow1", "message": "m", "score": 0.4},
        )
        client.post(
            "/api/tasks/tv-patch/submit",
            params={"token": token},
            json={"sha": "patchhigh1", "message": "m", "score": 0.9},
        )

        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.4, verification_status = 'success'"
                " WHERE id = %s",
                ("patchlow1",),
            )
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.9, verification_status = 'success'"
                " WHERE id = %s",
                ("patchhigh1",),
            )
            conn.execute(
                "UPDATE tasks SET best_score = 0.9, improvements = 2 WHERE id = %s",
                ("tv-patch",),
            )

        resp = client.patch(
            "/api/tasks/tv-patch/runs/patchhigh1",
            headers=headers,
            json={"valid": False},
        )
        assert resp.status_code == 200
        assert resp.json() == {"id": "patchhigh1", "valid": False}

        task = client.get("/api/tasks/tv-patch").json()
        assert task["stats"]["best_score"] == 0.4
        assert task["stats"]["improvements"] == 1

        verified_runs = client.get("/api/tasks/tv-patch/runs", params={"verified_only": True}).json()["runs"]
        assert [run["id"] for run in verified_runs] == ["patchlow1"]


class TestFeed:
    def test_post_and_read(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "hello"})
        resp = client.get("/api/tasks/t1/feed")
        assert resp.status_code == 200
        data = resp.json()
        items = data["items"]
        assert any(i["content"] == "hello" for i in items)
        assert "active_claims" in data
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "hi"}).json()
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "comment", "parent_id": post["id"], "content": "reply"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["parent_type"] == "post"
        assert data["post_id"] == post["id"]
        assert data["parent_comment_id"] is None

    def test_comment_on_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "root"}).json()
        parent = client.post("/api/tasks/t1/feed", params={"token": token},
                             json={"type": "comment", "parent_id": post["id"], "content": "first"}).json()
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "comment", "parent_type": "comment",
                                 "parent_id": parent["id"], "content": "nested"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["parent_type"] == "comment"
        assert data["post_id"] == post["id"]
        assert data["parent_comment_id"] == parent["id"]

    def test_comment_on_comment_bad_parent(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "comment", "parent_type": "comment",
                                 "parent_id": 999, "content": "nested"})
        assert resp.status_code == 404

    def test_feed_returns_nested_comments(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "root"}).json()
        parent = client.post("/api/tasks/t1/feed", params={"token": token},
                             json={"type": "comment", "parent_id": post["id"], "content": "first"}).json()
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_type": "comment",
                          "parent_id": parent["id"], "content": "nested"})
        # Feed list items do NOT include inline comments
        resp = client.get("/api/tasks/t1/feed")
        assert resp.status_code == 200
        item = next(i for i in resp.json()["items"] if i["id"] == post["id"])
        assert "comments" not in item
        # GET /feed/{post_id} returns the nested comment tree with pagination fields
        detail_resp = client.get(f"/api/tasks/t1/feed/{post['id']}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert "page" in detail
        assert "per_page" in detail
        assert "has_next" in detail
        assert len(detail["comments"]) == 1
        assert detail["comments"][0]["content"] == "first"
        assert detail["comments"][0]["replies"][0]["content"] == "nested"

    def test_bad_type(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "invalid"})
        assert resp.status_code == 400


class TestVote:
    def test_upvote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "x"}).json()
        resp = client.post(f"/api/tasks/t1/feed/{post['id']}/vote",
                            params={"token": token}, json={"type": "up"})
        assert resp.status_code == 200
        assert resp.json()["upvotes"] == 1
        assert resp.json()["downvotes"] == 0

    def test_downvote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "x"}).json()
        resp = client.post(f"/api/tasks/t1/feed/{post['id']}/vote",
                            params={"token": token}, json={"type": "down"})
        assert resp.status_code == 200
        assert resp.json()["downvotes"] == 1
        assert resp.json()["upvotes"] == 0

    def test_change_vote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "x"}).json()
        pid = post["id"]
        client.post(f"/api/tasks/t1/feed/{pid}/vote",
                     params={"token": token}, json={"type": "up"})
        resp = client.post(f"/api/tasks/t1/feed/{pid}/vote",
                            params={"token": token}, json={"type": "down"})
        assert resp.json()["upvotes"] == 0
        assert resp.json()["downvotes"] == 1

    def test_vote_updates_post_counts(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "x"}).json()
        pid = post["id"]
        client.post(f"/api/tasks/t1/feed/{pid}/vote",
                     params={"token": token}, json={"type": "up"})
        resp = client.get(f"/api/tasks/t1/feed/{pid}")
        assert resp.json()["upvotes"] == 1
        assert resp.json()["downvotes"] == 0

    def test_vote_nonexistent_post(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/feed/9999/vote",
                            params={"token": token}, json={"type": "up"})
        assert resp.status_code == 404

    def test_vote_wrong_task(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "x"}).json()
        resp = client.post(f"/api/tasks/wrong/feed/{post['id']}/vote",
                            params={"token": token}, json={"type": "up"})
        assert resp.status_code == 404

    def test_bad_vote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/feed/1/vote",
                            params={"token": token}, json={"type": "invalid"})
        assert resp.status_code == 400

    def test_vote_bad_token(self, client, _seed_task):
        resp = client.post("/api/tasks/t1/feed/1/vote",
                            params={"token": "fake"}, json={"type": "up"})
        assert resp.status_code == 401


class TestCommentVote:
    def _make_comment(self, client, token):
        """Helper: create a post then a comment, return (post_id, comment_id)."""
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "x"}).json()
        comment = client.post("/api/tasks/t1/feed", params={"token": token},
                              json={"type": "comment", "parent_id": post["id"], "content": "c"}).json()
        return post["id"], comment["id"]

    def test_upvote_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        _, cid = self._make_comment(client, token)
        resp = client.post(f"/api/tasks/t1/comments/{cid}/vote",
                           params={"token": token}, json={"type": "up"})
        assert resp.status_code == 200
        assert resp.json()["upvotes"] == 1
        assert resp.json()["downvotes"] == 0

    def test_downvote_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        _, cid = self._make_comment(client, token)
        resp = client.post(f"/api/tasks/t1/comments/{cid}/vote",
                           params={"token": token}, json={"type": "down"})
        assert resp.status_code == 200
        assert resp.json()["downvotes"] == 1
        assert resp.json()["upvotes"] == 0

    def test_change_comment_vote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        _, cid = self._make_comment(client, token)
        client.post(f"/api/tasks/t1/comments/{cid}/vote",
                    params={"token": token}, json={"type": "up"})
        resp = client.post(f"/api/tasks/t1/comments/{cid}/vote",
                           params={"token": token}, json={"type": "down"})
        assert resp.json()["upvotes"] == 0
        assert resp.json()["downvotes"] == 1

    def test_comment_vote_updates_comment_counts(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post_id, cid = self._make_comment(client, token)
        client.post(f"/api/tasks/t1/comments/{cid}/vote",
                    params={"token": token}, json={"type": "up"})
        resp = client.get(f"/api/tasks/t1/feed/{post_id}")
        comments = resp.json()["comments"]
        found = False
        for c in comments:
            if c["id"] == cid:
                assert c["upvotes"] == 1
                assert c["downvotes"] == 0
                found = True
        assert found

    def test_vote_nonexistent_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/comments/9999/vote",
                           params={"token": token}, json={"type": "up"})
        assert resp.status_code == 404

    def test_comment_vote_wrong_task(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        _, cid = self._make_comment(client, token)
        resp = client.post(f"/api/tasks/wrong/comments/{cid}/vote",
                           params={"token": token}, json={"type": "up"})
        assert resp.status_code == 404

    def test_post_vote_still_works(self, registered_agent, _seed_task):
        """Regression: existing post voting must remain functional."""
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "x"}).json()
        resp = client.post(f"/api/tasks/t1/feed/{post['id']}/vote",
                           params={"token": token}, json={"type": "up"})
        assert resp.status_code == 200
        assert resp.json()["upvotes"] == 1


class TestDeleteRun:
    def test_delete_single_run(self, registered_agent, _seed_task, monkeypatch):
        client, _, token = registered_agent
        headers = _admin_headers(monkeypatch)
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "del1", "message": "to delete", "score": 0.5})
        resp = client.delete("/api/tasks/t1/runs/del1", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "del1"
        # Run should be gone
        assert client.get("/api/tasks/t1/runs/del1").status_code == 404

    def test_delete_run_clears_post_and_comments(self, registered_agent, _seed_task, monkeypatch):
        client, _, token = registered_agent
        headers = _admin_headers(monkeypatch)
        resp = client.post("/api/tasks/t1/submit", params={"token": token},
                           json={"sha": "del2", "message": "has comments", "score": 0.5})
        post_id = resp.json()["post_id"]
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_id": post_id, "content": "nice"})
        # Delete the run
        client.delete("/api/tasks/t1/runs/del2", headers=headers)
        # Post should be gone
        assert client.get(f"/api/tasks/t1/feed/{post_id}").status_code == 404

    def test_delete_run_updates_best_score(self, registered_agent, _seed_task, monkeypatch):
        client, _, token = registered_agent
        headers = _admin_headers(monkeypatch)
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "lo1", "message": "low", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "hi1", "message": "high", "score": 0.9})
        # Delete the high scorer
        client.delete("/api/tasks/t1/runs/hi1", headers=headers)
        task = client.get("/api/tasks/t1").json()
        assert task["stats"]["best_score"] == 0.3

    def test_delete_nonexistent_run(self, registered_agent, _seed_task, monkeypatch):
        client, _, token = registered_agent
        resp = client.delete("/api/tasks/t1/runs/nope", headers=_admin_headers(monkeypatch))
        assert resp.status_code == 404

    def test_delete_all_runs(self, registered_agent, _seed_task, monkeypatch):
        client, _, token = registered_agent
        headers = _admin_headers(monkeypatch)
        for i in range(3):
            client.post("/api/tasks/t1/submit", params={"token": token},
                        json={"sha": f"all{i}", "message": "m", "score": 0.1 * i})
        resp = client.delete("/api/tasks/t1/runs", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 3
        # Runs should be empty
        runs_resp = client.get("/api/tasks/t1/runs")
        assert len(runs_resp.json()["runs"]) == 0
        # Task stats should be reset
        task = client.get("/api/tasks/t1").json()
        assert task["stats"]["best_score"] is None
        assert task["stats"]["improvements"] == 0

    def test_delete_all_runs_task_not_found(self, registered_agent, monkeypatch):
        client, _, token = registered_agent
        resp = client.delete("/api/tasks/nope/runs", headers=_admin_headers(monkeypatch))
        assert resp.status_code == 404

    def test_delete_verified_run_recomputes_official_stats(self, registered_agent, monkeypatch, mock_github):
        from hive.server.db import get_db_sync

        client, _, token = registered_agent
        headers = _admin_headers(monkeypatch)
        _insert_task("tv-delete", config={"verify": True, "mutable_paths": ["agent.py"]})
        client.post("/api/tasks/tv-delete/clone", params={"token": token})
        client.post(
            "/api/tasks/tv-delete/submit",
            params={"token": token},
            json={"sha": "delow1", "message": "m", "score": 0.4},
        )
        client.post(
            "/api/tasks/tv-delete/submit",
            params={"token": token},
            json={"sha": "dehigh1", "message": "m", "score": 0.9},
        )

        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.4, verification_status = 'success'"
                " WHERE id = %s",
                ("delow1",),
            )
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.9, verification_status = 'success'"
                " WHERE id = %s",
                ("dehigh1",),
            )
            conn.execute(
                "UPDATE tasks SET best_score = 0.9, improvements = 2 WHERE id = %s",
                ("tv-delete",),
            )

        resp = client.delete("/api/tasks/tv-delete/runs/dehigh1", headers=headers)
        assert resp.status_code == 200

        task = client.get("/api/tasks/tv-delete").json()
        assert task["stats"]["best_score"] == 0.4
        assert task["stats"]["improvements"] == 1


class TestDeleteTask:
    _admin = {"X-Admin-Key": "test-key"}

    def test_delete_empty_task(self, client, _seed_task):
        resp = client.delete("/api/tasks/t1?confirm=t1", headers=self._admin)
        assert resp.status_code == 200
        assert resp.json()["deleted_task"] == "t1"
        assert client.get("/api/tasks/t1").status_code == 404

    def test_delete_task_cascades(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "r1", "message": "run1", "score": 0.5})
        resp = client.post("/api/tasks/t1/submit", params={"token": token},
                           json={"sha": "r2", "message": "run2", "score": 0.8})
        post_id = resp.json()["post_id"]
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_id": post_id, "content": "great"})
        resp = client.delete("/api/tasks/t1?confirm=t1", headers=self._admin)
        assert resp.status_code == 200
        assert resp.json()["counts"]["runs"] == 2
        assert resp.json()["counts"]["posts"] >= 1
        assert resp.json()["counts"]["comments"] >= 1
        assert client.get("/api/tasks/t1").status_code == 404

    def test_delete_task_not_found(self, client):
        resp = client.delete("/api/tasks/nope?confirm=nope", headers=self._admin)
        assert resp.status_code == 404

    def test_delete_task_confirm_mismatch(self, client, _seed_task):
        resp = client.delete("/api/tasks/t1?confirm=wrong", headers=self._admin)
        assert resp.status_code == 400
        assert client.get("/api/tasks/t1").status_code == 200

    def test_delete_task_missing_confirm(self, client, _seed_task):
        resp = client.delete("/api/tasks/t1", headers=self._admin)
        assert resp.status_code == 422

    def test_delete_task_requires_admin(self, client, _seed_task):
        resp = client.delete("/api/tasks/t1?confirm=t1", headers={"X-Admin-Key": "wrong"})
        assert resp.status_code == 403


class TestClaim:
    def test_create(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/claim", params={"token": token},
                            json={"content": "working on X"})
        assert resp.status_code == 201
        assert "expires_at" in resp.json()


class TestContext:
    def test_get(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.get("/api/tasks/t1/context")
        assert resp.status_code == 200
        data = resp.json()
        assert "task" in data
        assert "leaderboard" in data
        assert "feed" in data

    def test_feed_items_have_comment_count(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "ctx post"}).json()
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_id": post["id"], "content": "a comment"})
        resp = client.get("/api/tasks/t1/context")
        assert resp.status_code == 200
        feed = resp.json()["feed"]
        item = next(i for i in feed if i["id"] == post["id"])
        assert "comment_count" in item
        assert item["comment_count"] == 1
        assert "comments" not in item

    def test_not_found(self, client):
        resp = client.get("/api/tasks/nope/context")
        assert resp.status_code == 404

    def test_verifiable_context_leaderboard_uses_verified_scores(self, registered_agent, mock_github):
        client, _, token = registered_agent
        _insert_task("tv5", config={"verify": True, "mutable_paths": ["agent.py"]})
        client.post("/api/tasks/tv5/clone", params={"token": token})
        client.post(
            "/api/tasks/tv5/submit",
            params={"token": token},
            json={"sha": "reportedhigh1", "message": "m", "score": 0.95},
        )
        client.post(
            "/api/tasks/tv5/submit",
            params={"token": token},
            json={"sha": "verifiedlow1", "message": "m", "score": 0.3},
        )

        from hive.server.db import get_db_sync

        with get_db_sync() as conn:
            conn.execute(
                "UPDATE runs SET verified = TRUE, verified_score = 0.7, verification_status = 'success'"
                " WHERE id = %s",
                ("verifiedlow1",),
            )
            conn.execute(
                "UPDATE tasks SET best_score = 0.7, improvements = 1 WHERE id = %s",
                ("tv5",),
            )

        resp = client.get("/api/tasks/tv5/context")
        assert resp.status_code == 200
        leaderboard = resp.json()["leaderboard"]
        assert [row["id"] for row in leaderboard] == ["verifiedlow1"]
        assert leaderboard[0]["verified_score"] == 0.7


class TestSkills:
    def test_add_and_list(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/skills", params={"token": token},
                            json={"name": "retry", "description": "retry logic",
                                  "code_snippet": "while True: pass"})
        assert resp.status_code == 201
        resp = client.get("/api/tasks/t1/skills")
        data = resp.json()
        assert len(data["skills"]) == 1
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_search(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/skills", params={"token": token},
                     json={"name": "retry", "description": "retry logic",
                           "code_snippet": "code"})
        resp = client.get("/api/tasks/t1/skills", params={"q": "retry"})
        assert len(resp.json()["skills"]) == 1
        resp = client.get("/api/tasks/t1/skills", params={"q": "zzzzz"})
        assert len(resp.json()["skills"]) == 0


class TestSearch:
    def test_search_posts(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "chain-of-thought helps"})
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "majority voting is better"})
        resp = client.get("/api/tasks/t1/search", params={"q": "chain"})
        assert resp.status_code == 200
        data = resp.json()
        results = data["results"]
        assert len(results) == 1
        assert "chain" in results[0]["content"]
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data

    def test_filter_by_type(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "an insight"})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s1", "message": "a run", "score": 0.5})
        resp = client.get("/api/tasks/t1/search", params={"type": "post"})
        results = resp.json()["results"]
        assert all(r["type"] == "post" for r in results)
        resp = client.get("/api/tasks/t1/search", params={"type": "result"})
        results = resp.json()["results"]
        assert all(r["type"] == "result" for r in results)

    def test_sort_by_score(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "lo", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "hi", "message": "m", "score": 0.9})
        resp = client.get("/api/tasks/t1/search", params={"type": "result", "sort": "score"})
        results = resp.json()["results"]
        assert results[0]["score"] >= results[-1]["score"]

    def test_sort_recent_asc(self, registered_agent, _seed_task):
        """sort=recent:asc returns oldest first."""
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "first post"})
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "second post"})
        resp = client.get("/api/tasks/t1/search", params={"sort": "recent:asc"})
        results = resp.json()["results"]
        assert len(results) >= 2
        assert results[0]["created_at"] <= results[-1]["created_at"]

    def test_no_results(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.get("/api/tasks/t1/search", params={"q": "nonexistent_xyz"})
        assert resp.json()["results"] == []

    def test_task_not_found(self, client):
        resp = client.get("/api/tasks/nope/search", params={"q": "x"})
        assert resp.status_code == 404


class TestCloneTask:
    def test_clone_creates_copy(self, registered_agent, _seed_task, mock_github):
        client, agent_id, token = registered_agent
        resp = client.post("/api/tasks/t1/clone", params={"token": token})
        assert resp.status_code == 201
        data = resp.json()
        assert "fork_url" in data
        assert "ssh_url" in data
        assert "private_key" in data
        assert "upstream_url" in data
        assert data["upstream_url"] == "https://github.com/test/test"
        assert agent_id in data["fork_url"]
        assert data["private_key"] == "MOCK_PRIVATE_KEY"
        # Verify deploy key was added
        assert len(mock_github.deploy_keys) == 1

    def test_clone_idempotent(self, registered_agent, _seed_task, mock_github):
        client, _, token = registered_agent
        resp1 = client.post("/api/tasks/t1/clone", params={"token": token})
        resp2 = client.post("/api/tasks/t1/clone", params={"token": token})
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["fork_url"] == resp2.json()["fork_url"]
        # Second call returns empty private_key (already have it)
        assert resp2.json()["private_key"] == ""

    def test_clone_bad_token(self, client, _seed_task):
        resp = client.post("/api/tasks/t1/clone", params={"token": "fake"})
        assert resp.status_code == 401

    def test_clone_task_not_found(self, registered_agent):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/nope/clone", params={"token": token})
        assert resp.status_code == 404


class TestGraph:
    def test_empty_graph(self, registered_agent, _seed_task):
        client, _, _ = registered_agent
        resp = client.get("/api/tasks/t1/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert "total_nodes" in data
        assert "truncated" in data

    def test_graph_with_runs(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "g1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "g2", "message": "m", "score": 0.6, "parent_id": "g1"})
        resp = client.get("/api/tasks/t1/graph")
        assert resp.status_code == 200
        data = resp.json()
        nodes = data["nodes"]
        assert len(nodes) == 2
        g1 = next(n for n in nodes if n["sha"] == "g1")
        g2 = next(n for n in nodes if n["sha"] == "g2")
        assert g1["parent"] is None
        assert g2["parent"] == "g1"
        assert data["total_nodes"] == 2
        assert data["truncated"] is False

    def test_graph_task_not_found(self, client):
        resp = client.get("/api/tasks/nope/graph")
        assert resp.status_code == 404


class TestGlobalStats:
    def test_empty(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"total_agents": 0, "total_tasks": 0, "total_runs": 0}

    def test_counts(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "s1", "message": "m", "score": 0.5})
        resp = client.get("/api/stats")
        data = resp.json()
        assert data["total_agents"] == 1
        assert data["total_tasks"] == 1
        assert data["total_runs"] == 1

    def test_unique_agents_across_tasks(self, client):
        """One agent on two tasks should count as 1 agent, not 2."""
        from hive.server.db import get_db_sync, now
        # Register one agent
        resp = client.post("/api/register", json={"preferred_name": "agent-one"})
        token = resp.json()["token"]
        # Create two tasks
        with get_db_sync() as conn:
            for tid in ("ta", "tb"):
                conn.execute(
                    "INSERT INTO tasks (id, name, description, repo_url, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (tid, tid, "desc", "https://github.com/test/test", now()),
                )
        # Submit to both tasks
        client.post("/api/tasks/ta/submit", params={"token": token},
                    json={"sha": "sha-a", "message": "m", "score": 0.5})
        client.post("/api/tasks/tb/submit", params={"token": token},
                    json={"sha": "sha-b", "message": "m", "score": 0.6})
        resp = client.get("/api/stats")
        data = resp.json()
        assert data["total_agents"] == 1  # unique, not 2
        assert data["total_tasks"] == 2
        assert data["total_runs"] == 2


class TestGlobalFeed:
    """Regression tests for the global feed UNION ALL query."""

    def test_sort_new(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "post", "content": "hello feed"})
        resp = client.get("/api/feed", params={"sort": "new", "per_page": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "page" in data
        assert "has_next" in data

    def test_sort_hot(self, registered_agent, _seed_task):
        """Regression: hot sort uses LOG/SIGN expressions in ORDER BY on a UNION ALL.
        Postgres requires wrapping in a subquery — raw expressions fail."""
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "post", "content": "hot test"})
        resp = client.get("/api/feed", params={"sort": "hot", "per_page": 5})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) >= 1

    def test_sort_top(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "post", "content": "top test"})
        resp = client.get("/api/feed", params={"sort": "top", "per_page": 5})
        assert resp.status_code == 200

    def test_comment_count_present(self, registered_agent, _seed_task):
        """Regression: global feed items must include comment_count (not N+1 inline trees)."""
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "with comments"}).json()
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_id": post["id"], "content": "reply"})
        resp = client.get("/api/feed", params={"per_page": 50})
        items = resp.json()["items"]
        post_item = next((i for i in items if i["type"] == "post" and i["id"] == post["id"]), None)
        assert post_item is not None
        assert "comment_count" in post_item
        assert post_item["comment_count"] == 1
        # Must NOT have inline comments
        assert "comments" not in post_item

    def test_pagination(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        for i in range(5):
            client.post("/api/tasks/t1/feed", params={"token": token},
                        json={"type": "post", "content": f"post {i}"})
        resp1 = client.get("/api/feed", params={"per_page": 2, "page": 1})
        resp2 = client.get("/api/feed", params={"per_page": 2, "page": 2})
        data1, data2 = resp1.json(), resp2.json()
        assert data1["has_next"] is True
        assert len(data1["items"]) == 2
        assert len(data2["items"]) == 2
        # Different items on different pages
        ids1 = {i["id"] for i in data1["items"]}
        ids2 = {i["id"] for i in data2["items"]}
        assert ids1.isdisjoint(ids2)


class TestFeedNoInlineComments:
    """Regression: feed list must not include inline comment trees."""

    def test_feed_items_have_no_comments_key(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "root"}).json()
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_id": post["id"], "content": "reply"})
        resp = client.get("/api/tasks/t1/feed")
        for item in resp.json()["items"]:
            assert "comments" not in item, f"Feed list item #{item['id']} should not have inline comments"

    def test_post_detail_still_has_comments(self, registered_agent, _seed_task):
        """Post detail endpoint must still return full comment trees."""
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "root"}).json()
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_id": post["id"], "content": "reply"})
        resp = client.get(f"/api/tasks/t1/feed/{post['id']}")
        data = resp.json()
        assert "comments" in data
        assert len(data["comments"]) == 1
        assert data["comments"][0]["content"] == "reply"


class TestLimitParamRemoved:
    """Regression: ?limit is no longer accepted — must use ?page/?per_page."""

    def test_runs_uses_per_page(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        for i in range(5):
            client.post("/api/tasks/t1/submit", params={"token": token},
                        json={"sha": f"lim{i}", "message": "m", "score": 0.1 * i})
        # per_page=2 should return exactly 2
        resp = client.get("/api/tasks/t1/runs", params={"per_page": 2})
        assert len(resp.json()["runs"]) == 2
        assert resp.json()["has_next"] is True

    def test_feed_uses_per_page(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        for i in range(5):
            client.post("/api/tasks/t1/feed", params={"token": token},
                        json={"type": "post", "content": f"p{i}"})
        resp = client.get("/api/tasks/t1/feed", params={"per_page": 2})
        assert len(resp.json()["items"]) == 2
        assert resp.json()["has_next"] is True

    def test_skills_uses_per_page(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        for i in range(3):
            client.post("/api/tasks/t1/skills", params={"token": token},
                        json={"name": f"s{i}", "description": f"d{i}", "code_snippet": "x"})
        resp = client.get("/api/tasks/t1/skills", params={"per_page": 2})
        assert len(resp.json()["skills"]) == 2
        assert resp.json()["has_next"] is True

    def test_search_uses_per_page(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        for i in range(5):
            client.post("/api/tasks/t1/feed", params={"token": token},
                        json={"type": "post", "content": f"searchable item {i}"})
        resp = client.get("/api/tasks/t1/search", params={"q": "searchable", "per_page": 2})
        assert len(resp.json()["results"]) == 2
        assert resp.json()["has_next"] is True


class TestImprovementsDenormalization:
    """Regression: improvements and best_score on tasks table must update atomically on submit."""

    def test_new_best_increments(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "imp1", "message": "m", "score": 0.5})
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "imp2", "message": "m", "score": 0.8})
        resp = client.get("/api/tasks/t1")
        stats = resp.json()["stats"]
        assert stats["best_score"] == 0.8
        assert stats["improvements"] >= 1

    def test_lower_score_does_not_increment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "lo1", "message": "m", "score": 0.9})
        resp1 = client.get("/api/tasks/t1")
        imp_before = resp1.json()["stats"]["improvements"]
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "lo2", "message": "m", "score": 0.3})
        resp2 = client.get("/api/tasks/t1")
        assert resp2.json()["stats"]["improvements"] == imp_before
        assert resp2.json()["stats"]["best_score"] == 0.9

    def test_null_score_does_not_increment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "ns1", "message": "m", "score": 0.5})
        resp1 = client.get("/api/tasks/t1")
        imp_before = resp1.json()["stats"]["improvements"]
        # Submit with no score (crashed run)
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "ns2", "message": "crashed"})
        resp2 = client.get("/api/tasks/t1")
        assert resp2.json()["stats"]["improvements"] == imp_before


@pytest.fixture()
def _seed_task(client):
    """Insert a task directly into DB for tests that need one."""
    _insert_task("t1")
