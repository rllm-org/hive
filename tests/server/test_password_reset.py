"""Tests for the password reset flow."""
from hive.server.db import get_db_sync
from tests.conftest import _create_verified_user


def _create_user(client, email="user@test.com", password="oldpass123"):
    token, _ = _create_verified_user(client, email, password)
    return token


class TestForgotPassword:
    def test_sends_code_for_existing_user(self, client):
        _create_user(client)
        resp = client.post("/api/auth/forgot-password", json={"email": "user@test.com"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"
        with get_db_sync() as conn:
            row = conn.execute("SELECT code, attempts FROM password_resets WHERE email = %s", ("user@test.com",)).fetchone()
        assert row is not None
        assert len(row["code"]) == 6
        assert row["attempts"] == 0

    def test_returns_success_for_nonexistent_email(self, client):
        resp = client.post("/api/auth/forgot-password", json={"email": "nobody@test.com"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"
        with get_db_sync() as conn:
            row = conn.execute("SELECT 1 FROM password_resets WHERE email = %s", ("nobody@test.com",)).fetchone()
        assert row is None

    def test_rejects_invalid_email(self, client):
        resp = client.post("/api/auth/forgot-password", json={"email": "notanemail"})
        assert resp.status_code == 400


class TestResetPassword:
    def test_resets_password_with_valid_code(self, client):
        _create_user(client)
        client.post("/api/auth/forgot-password", json={"email": "user@test.com"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT code FROM password_resets WHERE email = %s", ("user@test.com",)).fetchone()
        resp = client.post("/api/auth/reset-password", json={
            "email": "user@test.com", "code": row["code"], "password": "newpass456"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "password_reset"
        resp = client.post("/api/auth/login", json={"email": "user@test.com", "password": "newpass456"})
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_old_password_no_longer_works(self, client):
        _create_user(client)
        client.post("/api/auth/forgot-password", json={"email": "user@test.com"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT code FROM password_resets WHERE email = %s", ("user@test.com",)).fetchone()
        client.post("/api/auth/reset-password", json={
            "email": "user@test.com", "code": row["code"], "password": "newpass456"
        })
        resp = client.post("/api/auth/login", json={"email": "user@test.com", "password": "oldpass123"})
        assert resp.status_code == 401

    def test_invalid_code_increments_attempts(self, client):
        _create_user(client)
        client.post("/api/auth/forgot-password", json={"email": "user@test.com"})
        client.post("/api/auth/reset-password", json={
            "email": "user@test.com", "code": "000000", "password": "newpass456"
        })
        with get_db_sync() as conn:
            row = conn.execute("SELECT attempts FROM password_resets WHERE email = %s", ("user@test.com",)).fetchone()
        assert row["attempts"] == 1

    def test_locks_after_5_failed_attempts(self, client):
        _create_user(client)
        client.post("/api/auth/forgot-password", json={"email": "user@test.com"})
        for _ in range(5):
            client.post("/api/auth/reset-password", json={
                "email": "user@test.com", "code": "000000", "password": "newpass456"
            })
        resp = client.post("/api/auth/reset-password", json={
            "email": "user@test.com", "code": "000000", "password": "newpass456"
        })
        assert resp.status_code == 429

    def test_rejects_short_password(self, client):
        _create_user(client)
        client.post("/api/auth/forgot-password", json={"email": "user@test.com"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT code FROM password_resets WHERE email = %s", ("user@test.com",)).fetchone()
        resp = client.post("/api/auth/reset-password", json={
            "email": "user@test.com", "code": row["code"], "password": "short"
        })
        assert resp.status_code == 400

    def test_rejects_without_forgot_password(self, client):
        _create_user(client)
        resp = client.post("/api/auth/reset-password", json={
            "email": "user@test.com", "code": "123456", "password": "newpass456"
        })
        assert resp.status_code == 400

    def test_cleanup_after_successful_reset(self, client):
        _create_user(client)
        client.post("/api/auth/forgot-password", json={"email": "user@test.com"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT code FROM password_resets WHERE email = %s", ("user@test.com",)).fetchone()
        client.post("/api/auth/reset-password", json={
            "email": "user@test.com", "code": row["code"], "password": "newpass456"
        })
        with get_db_sync() as conn:
            row = conn.execute("SELECT 1 FROM password_resets WHERE email = %s", ("user@test.com",)).fetchone()
        assert row is None
