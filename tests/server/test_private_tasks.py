"""Tests for private task branch-based workflow."""
import io
import pytest

from hive.server.db import get_db_sync, now


def _create_user_with_github(client, handle="owneruser"):
    """Create a verified user with a GitHub token. Returns (jwt_token, user_id, handle)."""
    from hive.server.db import get_db_sync
    client.post("/api/auth/signup", json={"email": "owner@test.com", "password": "testpass123", "handle": handle})
    with get_db_sync() as conn:
        row = conn.execute("SELECT code FROM pending_signups WHERE email = %s", ("owner@test.com",)).fetchone()
    resp = client.post("/api/auth/verify-code", json={"email": "owner@test.com", "code": row["code"]})
    data = resp.json()
    jwt_token = data["token"]
    user_id = data["user"]["id"]
    # Add a fake GitHub token
    with get_db_sync() as conn:
        conn.execute(
            "UPDATE users SET github_token = %s, github_id = %s, github_username = %s WHERE id = %s",
            ("fake-gh-token", 12345, "testowner", user_id),
        )
    return jwt_token, user_id, handle


def _register_agent_for_user(client, jwt_token, user_id):
    """Register an agent and link it to the user. Returns (agent_id, agent_token, jwt_token)."""
    resp = client.post("/api/register")
    data = resp.json()
    agent_id, agent_token = data["id"], data["token"]
    # Set user_id directly in DB
    with get_db_sync() as conn:
        conn.execute("UPDATE agents SET user_id = %s WHERE id = %s", (user_id, agent_id))
    return agent_id, agent_token, jwt_token


def _seed_private_task(client, owner, slug="priv-task", source_repo="testowner/myrepo",
                       installation_id=None, owner_id=None):
    """Insert a private task directly into DB."""
    with get_db_sync() as conn:
        conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, task_type, owner_id, "
            "visibility, source_repo, installation_id, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (slug, owner, "Private Task", "A private test task",
             f"https://github.com/{source_repo}", "private", owner_id or owner,
             "private", source_repo, installation_id, now()),
        )


class TestPrivateTaskClone:
    """Test clone endpoint for private tasks."""

    def test_clone_private_task_returns_branch_mode(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        agent_id, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        mock_github._repo_installations["testowner/myrepo"] = "99999"
        _seed_private_task(client, owner_handle, installation_id="99999", owner_id=user_id)

        resp = client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                           headers={"Authorization": f"Bearer {jwt}"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["mode"] == "branch"
        assert data["branch_prefix"] == f"hive/{agent_id}/"
        assert data["default_branch"] == f"hive/{agent_id}/initial"
        assert data["private_key"] == "MOCK_PRIVATE_KEY"
        assert "ssh_url" in data

    def test_clone_private_task_creates_read_only_deploy_key(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        agent_id, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        mock_github._repo_installations["testowner/myrepo"] = "99999"
        _seed_private_task(client, owner_handle, installation_id="99999", owner_id=user_id)

        client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                    headers={"Authorization": f"Bearer {jwt}"})
        # deploy_keys: (repo, title, pubkey, key_id, read_only)
        assert len(mock_github.deploy_keys) == 1
        assert mock_github.deploy_keys[0][4] is True  # read_only

    def test_clone_private_task_creates_initial_branch(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        agent_id, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        mock_github._repo_installations["testowner/myrepo"] = "99999"
        _seed_private_task(client, owner_handle, installation_id="99999", owner_id=user_id)

        client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                    headers={"Authorization": f"Bearer {jwt}"})
        assert len(mock_github.created_branches) == 1
        repo, branch, from_branch = mock_github.created_branches[0]
        assert repo == "testowner/myrepo"
        assert branch == f"hive/{agent_id}/initial"
        assert from_branch == "main"

    def test_clone_private_task_idempotent(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        _, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        mock_github._repo_installations["testowner/myrepo"] = "99999"
        _seed_private_task(client, owner_handle, installation_id="99999", owner_id=user_id)

        resp1 = client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                            headers={"Authorization": f"Bearer {jwt}"})
        resp2 = client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                            headers={"Authorization": f"Bearer {jwt}"})
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp2.json()["private_key"] == ""  # already delivered
        assert resp2.json()["mode"] == "branch"

    def test_clone_private_task_requires_owner_agent(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        mock_github._repo_installations["testowner/myrepo"] = "99999"
        _seed_private_task(client, owner_handle, installation_id="99999", owner_id=user_id)

        # Register a non-owner agent (no jwt_token => no user_id)
        resp = client.post("/api/register")
        other_token = resp.json()["token"]

        resp = client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": other_token},
                           headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 403

    def test_clone_private_task_without_app_installed(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        _, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        # Don't set _repo_installations — App not installed
        _seed_private_task(client, owner_handle, owner_id=user_id)

        resp = client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                           headers={"Authorization": f"Bearer {jwt}"})
        assert resp.status_code == 400
        assert "Install" in resp.json()["detail"]

    def test_clone_private_task_discovers_installation_id(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        _, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        # Task created without installation_id, but App is installed
        mock_github._repo_installations["testowner/myrepo"] = "88888"
        _seed_private_task(client, owner_handle, installation_id=None, owner_id=user_id)

        resp = client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                           headers={"Authorization": f"Bearer {jwt}"})
        assert resp.status_code == 201
        # Verify installation_id was stored
        with get_db_sync() as conn:
            task = conn.execute("SELECT installation_id FROM tasks WHERE owner = %s AND slug = %s", (owner_handle, "priv-task")).fetchone()
        assert task["installation_id"] == "88888"

    def test_clone_public_task_unchanged(self, client, mock_github):
        """Public task clone should still return fork mode (no mode field)."""
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO tasks (slug, owner, name, description, repo_url, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                ("pub-task", "hive", "Public Task", "A public test", "https://github.com/test/test", now()),
            )
        resp = client.post("/api/register")
        agent_token = resp.json()["token"]

        resp = client.post("/api/tasks/hive/pub-task/clone", params={"token": agent_token})
        assert resp.status_code == 201
        data = resp.json()
        assert "fork_url" in data
        assert data.get("mode") is None  # no mode field for public tasks


class TestPrivateTaskPush:
    """Test the push endpoint for private tasks."""

    def _setup(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        agent_id, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        mock_github._repo_installations["testowner/myrepo"] = "99999"
        _seed_private_task(client, owner_handle, installation_id="99999", owner_id=user_id)
        client.post(f"/api/tasks/{owner_handle}/priv-task/clone", params={"token": agent_token},
                    headers={"Authorization": f"Bearer {jwt}"})
        return agent_id, agent_token, jwt, owner_handle

    def test_push_valid_branch(self, client, mock_github):
        agent_id, agent_token, jwt, owner_handle = self._setup(client, mock_github)
        branch = f"hive/{agent_id}/experiment-1"
        bundle_content = b"fake-bundle-data"

        resp = client.post(
            f"/api/tasks/{owner_handle}/priv-task/push",
            params={"token": agent_token},
            data={"branch": branch},
            files={"bundle": ("bundle.git", io.BytesIO(bundle_content), "application/octet-stream")},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pushed"
        assert resp.json()["branch"] == branch
        assert len(mock_github.pushed_branches) == 1

    def test_push_wrong_branch_prefix(self, client, mock_github):
        agent_id, agent_token, jwt, owner_handle = self._setup(client, mock_github)
        bundle_content = b"fake-bundle-data"

        resp = client.post(
            f"/api/tasks/{owner_handle}/priv-task/push",
            params={"token": agent_token},
            data={"branch": "hive/other-agent/hack"},
            files={"bundle": ("bundle.git", io.BytesIO(bundle_content), "application/octet-stream")},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert resp.status_code == 403
        assert len(mock_github.pushed_branches) == 0

    def test_push_main_branch_rejected(self, client, mock_github):
        _, agent_token, jwt, owner_handle = self._setup(client, mock_github)
        bundle_content = b"fake-bundle-data"

        resp = client.post(
            f"/api/tasks/{owner_handle}/priv-task/push",
            params={"token": agent_token},
            data={"branch": "main"},
            files={"bundle": ("bundle.git", io.BytesIO(bundle_content), "application/octet-stream")},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert resp.status_code == 403

    def test_push_public_task_rejected(self, client, mock_github):
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO tasks (slug, owner, name, description, repo_url, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                ("pub-task", "hive", "Public Task", "A public test", "https://github.com/test/test", now()),
            )
        resp = client.post("/api/register")
        agent_token = resp.json()["token"]
        bundle_content = b"fake-bundle-data"

        resp = client.post(
            "/api/tasks/hive/pub-task/push",
            params={"token": agent_token},
            data={"branch": "main"},
            files={"bundle": ("bundle.git", io.BytesIO(bundle_content), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "public" in resp.json()["detail"].lower()

    def test_push_without_clone_rejected(self, client, mock_github):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        agent_id, agent_token, jwt = _register_agent_for_user(client, jwt_token, user_id)
        mock_github._repo_installations["testowner/myrepo"] = "99999"
        _seed_private_task(client, owner_handle, installation_id="99999", owner_id=user_id)
        # Don't clone — go straight to push
        bundle_content = b"fake-bundle-data"

        resp = client.post(
            f"/api/tasks/{owner_handle}/priv-task/push",
            params={"token": agent_token},
            data={"branch": f"hive/{agent_id}/test"},
            files={"bundle": ("bundle.git", io.BytesIO(bundle_content), "application/octet-stream")},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert resp.status_code == 400
        assert "clone" in resp.json()["detail"].lower()

    def test_push_no_branch_rejected(self, client, mock_github):
        _, agent_token, jwt, owner_handle = self._setup(client, mock_github)
        bundle_content = b"fake-bundle-data"

        resp = client.post(
            f"/api/tasks/{owner_handle}/priv-task/push",
            params={"token": agent_token},
            data={"branch": ""},
            files={"bundle": ("bundle.git", io.BytesIO(bundle_content), "application/octet-stream")},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert resp.status_code == 400


class TestPrivateTaskCreation:
    """Test that private task creation checks App installation."""

    def _mock_task_creation(self, monkeypatch):
        """Mock dependencies for private task creation."""
        import hive.server.main as main_mod
        import httpx as _httpx
        original_get = _httpx.get

        async def _fake_gh_token(uid):
            return "fake-token"
        monkeypatch.setattr(main_mod, "_get_valid_github_token", _fake_gh_token)
        monkeypatch.setattr(main_mod, "_gh_user_headers",
                            lambda t: {"Authorization": f"Bearer {t}"})
        def mock_get(url, **kwargs):
            if "api.github.com/repos/testowner/myrepo/contents" in url:
                return type("Resp", (), {"status_code": 200})()
            if "api.github.com/repos/testowner/myrepo" in url:
                return type("Resp", (), {
                    "status_code": 200,
                    "json": lambda self: {"html_url": "https://github.com/testowner/myrepo"}
                })()
            return original_get(url, **kwargs)
        monkeypatch.setattr(_httpx, "get", mock_get)

    def test_create_private_task_with_app_installed(self, client, mock_github, monkeypatch):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        mock_github._repo_installations["testowner/myrepo"] = "77777"
        self._mock_task_creation(monkeypatch)

        resp = client.post("/api/tasks/private",
                           json={"repo": "testowner/myrepo", "slug": "my-task",
                                 "name": "My Task", "description": "Testing"},
                           headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["app_installed"] is True
        with get_db_sync() as conn:
            task = conn.execute("SELECT installation_id FROM tasks WHERE owner = %s AND slug = %s", (owner_handle, "my-task")).fetchone()
        assert task["installation_id"] == "77777"

    def test_create_private_task_without_app(self, client, mock_github, monkeypatch):
        jwt_token, user_id, owner_handle = _create_user_with_github(client)
        self._mock_task_creation(monkeypatch)

        resp = client.post("/api/tasks/private",
                           json={"repo": "testowner/myrepo", "slug": "my-task2",
                                 "name": "My Task", "description": "Testing"},
                           headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["app_installed"] is False
        assert "install_url" in data
