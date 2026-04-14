"""Tests for terminal sandbox endpoints."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from hive.server.db import get_db_sync, now
from tests.conftest import _create_verified_user


def _create_user(client, email="sandbox@test.com"):
    """Create a verified user. Returns (jwt_token, user_id)."""
    token, user = _create_verified_user(client, email, "testpass123")
    return token, user["id"]


def _seed_task(slug="sandbox-task", owner="hive", config=None):
    """Insert a public task into the DB. Returns the integer task id."""
    with get_db_sync() as conn:
        row = conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, config, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (slug, owner, "Test Task", "A task for sandbox testing",
             "https://github.com/org/task--sandbox-task", config, now()),
        ).fetchone()
        return row["id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class MockSshAccess:
    def __init__(self):
        self.id = "ssh-access-1"
        self.sandbox_id = "dtn-sandbox-123"
        self.token = "ssh-token-secret"
        self.ssh_command = "ssh -p 2222 daytona@sandbox.daytona.io"
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class MockSandbox:
    def __init__(self):
        self.id = "dtn-sandbox-123"

    async def create_ssh_access(self, expires_in_minutes=None):
        return MockSshAccess()

    async def start(self):
        pass

    async def stop(self):
        pass

    class git:
        @staticmethod
        async def clone(url=None, path=None, commit_id=None):
            pass

    class process:
        @staticmethod
        async def exec(cmd, cwd=None, timeout=None):
            return MagicMock(result="ok")


class MockDaytona:
    """Mock AsyncDaytona context manager."""

    def __init__(self):
        self._sandbox = MockSandbox()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def create(self, params, timeout=None):
        return self._sandbox

    async def get(self, sandbox_id):
        return self._sandbox

    async def delete(self, sandbox, timeout=None):
        pass


def _patch_daytona(monkeypatch):
    """Patch Daytona SDK in the sandbox module."""
    mock = MockDaytona()
    monkeypatch.setattr("hive.server.sandbox.AsyncDaytona", lambda: mock)
    monkeypatch.setattr(
        "hive.server.sandbox.CreateSandboxFromSnapshotParams",
        MagicMock,
    )
    return mock


class TestCreateSandbox:
    def test_create_sandbox_returns_ssh_info(self, client, monkeypatch):
        token, user_id = _create_user(client)
        _seed_task()
        _patch_daytona(monkeypatch)

        resp = client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ready"
        assert data["ssh_command"] == "ssh -p 2222 daytona@sandbox.daytona.io"
        assert data["ssh_token"] is not None
        assert data["daytona_sandbox_id"] == "dtn-sandbox-123"
        assert "ssh_expires_at" in data

    def test_create_sandbox_idempotent(self, client, monkeypatch):
        token, user_id = _create_user(client)
        _seed_task()
        _patch_daytona(monkeypatch)

        resp1 = client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp1.status_code == 201

        # Second call should reconnect (200), not create a new one
        resp2 = client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp2.status_code == 200
        assert resp2.json()["sandbox_id"] == resp1.json()["sandbox_id"]

    def test_create_sandbox_requires_auth(self, client):
        _seed_task()
        resp = client.post("/api/tasks/hive/sandbox-task/sandbox")
        assert resp.status_code in (401, 422)

    def test_create_sandbox_task_not_found(self, client, monkeypatch):
        token, _ = _create_user(client)
        _patch_daytona(monkeypatch)
        resp = client.post("/api/tasks/hive/nonexistent/sandbox", headers=_auth(token))
        assert resp.status_code == 404


class TestGetSandbox:
    def test_get_sandbox_returns_info(self, client, monkeypatch):
        token, _ = _create_user(client)
        _seed_task()
        _patch_daytona(monkeypatch)

        client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        resp = client.get("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["ssh_command"] is not None

    def test_get_sandbox_not_found(self, client):
        token, _ = _create_user(client)
        _seed_task()
        resp = client.get("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 404

    def test_get_sandbox_access_control(self, client, monkeypatch):
        """User A cannot see user B's sandbox."""
        token_a, _ = _create_user(client, "usera@test.com")
        token_b, _ = _create_user(client, "userb@test.com")
        _seed_task()
        _patch_daytona(monkeypatch)

        # User A creates a sandbox
        resp = client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token_a))
        assert resp.status_code == 201

        # User B cannot see it
        resp = client.get("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token_b))
        assert resp.status_code == 404


class TestDeleteSandbox:
    def test_delete_sandbox(self, client, monkeypatch):
        token, _ = _create_user(client)
        _seed_task()
        _patch_daytona(monkeypatch)

        client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        resp = client.delete("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Should be gone now
        resp = client.get("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_sandbox_not_found(self, client):
        token, _ = _create_user(client)
        _seed_task()
        resp = client.delete("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 404

    def test_delete_sandbox_access_control(self, client, monkeypatch):
        """User B cannot delete user A's sandbox."""
        token_a, _ = _create_user(client, "usera2@test.com")
        token_b, _ = _create_user(client, "userb2@test.com")
        _seed_task()
        _patch_daytona(monkeypatch)

        client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token_a))
        resp = client.delete("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token_b))
        assert resp.status_code == 404


class TestSandboxErrorHandling:
    def test_daytona_failure_sets_error_status(self, client, monkeypatch):
        token, _ = _create_user(client)
        _seed_task()

        def failing_daytona():
            mock = MockDaytona()
            async def fail_create(params, timeout=None):
                raise RuntimeError("Daytona is down")
            mock.create = fail_create
            return mock

        monkeypatch.setattr("hive.server.sandbox.AsyncDaytona", failing_daytona)
        monkeypatch.setattr("hive.server.sandbox.CreateSandboxFromSnapshotParams", MagicMock)

        resp = client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 502

        # Check that status is 'error' in DB
        resp = client.get("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        assert "error_message" in resp.json()
