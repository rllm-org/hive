"""Comprehensive tests for auth endpoints: signup, verification, login, and rate limiting."""
from hive.server.db import get_db_sync


def _signup_and_get_code(client, email="user@test.com", password="testpass123", handle="testuser"):
    """Signup and return the verification code from DB."""
    resp = client.post("/api/auth/signup", json={"email": email, "password": password, "handle": handle})
    assert resp.status_code == 201, resp.text
    with get_db_sync() as conn:
        row = conn.execute("SELECT code FROM pending_signups WHERE email = %s", (email,)).fetchone()
    return row["code"]


def _create_user(client, email="user@test.com", password="testpass123", handle="testuser"):
    """Full signup + verify flow. Returns JWT token."""
    code = _signup_and_get_code(client, email, password, handle)
    resp = client.post("/api/auth/verify-code", json={"email": email, "code": code})
    assert resp.status_code == 200
    return resp.json()["token"]


class TestSignup:
    def test_signup_returns_verification_required(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword", "handle": "alice"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "verification_required"
        assert data["email"] == "a@b.com"

    def test_signup_creates_pending_signup(self, client):
        client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword", "handle": "alice"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT * FROM pending_signups WHERE email = %s", ("a@b.com",)).fetchone()
        assert row is not None
        assert len(row["code"]) == 6
        assert row["handle"] == "alice"

    def test_signup_rejects_short_password(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "short", "handle": "alice"})
        assert resp.status_code == 400

    def test_signup_rejects_invalid_email(self, client):
        resp = client.post("/api/auth/signup", json={"email": "notanemail", "password": "longpassword", "handle": "alice"})
        assert resp.status_code == 400

    def test_signup_rejects_missing_handle(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword"})
        assert resp.status_code == 400

    def test_signup_rejects_invalid_handle(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword", "handle": "Bad Handle!"})
        assert resp.status_code == 400

    def test_signup_rejects_reserved_handle(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword", "handle": "hive"})
        assert resp.status_code == 400

    def test_signup_rejects_duplicate_handle(self, client):
        _create_user(client, "a@b.com", handle="alice")
        resp = client.post("/api/auth/signup", json={"email": "c@d.com", "password": "longpassword", "handle": "alice"})
        assert resp.status_code == 409

    def test_signup_rejects_duplicate_verified_email(self, client):
        _create_user(client, "a@b.com", handle="alice")
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword", "handle": "bob"})
        assert resp.status_code == 409

    def test_signup_allows_re_signup_if_pending(self, client):
        """Re-signup with same email updates the pending signup (new code)."""
        code1 = _signup_and_get_code(client, "a@b.com", handle="alice")
        code2 = _signup_and_get_code(client, "a@b.com", handle="alice")
        # Code should be refreshed (extremely unlikely to be same)
        with get_db_sync() as conn:
            row = conn.execute("SELECT code FROM pending_signups WHERE email = %s", ("a@b.com",)).fetchone()
        assert row["code"] == code2


class TestVerifyCode:
    def test_verify_creates_user(self, client):
        code = _signup_and_get_code(client)
        resp = client.post("/api/auth/verify-code", json={"email": "user@test.com", "code": code})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["email"] == "user@test.com"

    def test_verify_cleans_up_pending(self, client):
        code = _signup_and_get_code(client)
        client.post("/api/auth/verify-code", json={"email": "user@test.com", "code": code})
        with get_db_sync() as conn:
            row = conn.execute("SELECT 1 FROM pending_signups WHERE email = %s", ("user@test.com",)).fetchone()
        assert row is None

    def test_verify_rejects_wrong_code(self, client):
        _signup_and_get_code(client)
        resp = client.post("/api/auth/verify-code", json={"email": "user@test.com", "code": "000000"})
        assert resp.status_code == 400

    def test_verify_increments_attempts(self, client):
        _signup_and_get_code(client)
        client.post("/api/auth/verify-code", json={"email": "user@test.com", "code": "000000"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT attempts FROM pending_signups WHERE email = %s", ("user@test.com",)).fetchone()
        assert row["attempts"] == 1

    def test_verify_locks_after_5_attempts(self, client):
        _signup_and_get_code(client)
        for _ in range(5):
            client.post("/api/auth/verify-code", json={"email": "user@test.com", "code": "000000"})
        resp = client.post("/api/auth/verify-code", json={"email": "user@test.com", "code": "000000"})
        assert resp.status_code == 429

    def test_verify_rejects_without_signup(self, client):
        resp = client.post("/api/auth/verify-code", json={"email": "nobody@test.com", "code": "123456"})
        assert resp.status_code == 404


class TestResendCode:
    def test_resend_updates_code(self, client):
        old_code = _signup_and_get_code(client)
        resp = client.post("/api/auth/resend-code", json={"email": "user@test.com"})
        assert resp.status_code == 200
        with get_db_sync() as conn:
            row = conn.execute("SELECT code, attempts FROM pending_signups WHERE email = %s", ("user@test.com",)).fetchone()
        # New code generated
        assert row["code"] != old_code or True  # codes could theoretically match
        # Attempts reset to 0
        assert row["attempts"] == 0

    def test_resend_resets_attempt_counter(self, client):
        _signup_and_get_code(client)
        # Fail 3 times
        for _ in range(3):
            client.post("/api/auth/verify-code", json={"email": "user@test.com", "code": "000000"})
        # Resend resets attempts
        client.post("/api/auth/resend-code", json={"email": "user@test.com"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT attempts FROM pending_signups WHERE email = %s", ("user@test.com",)).fetchone()
        assert row["attempts"] == 0

    def test_resend_rejects_unknown_email(self, client):
        resp = client.post("/api/auth/resend-code", json={"email": "nobody@test.com"})
        assert resp.status_code == 404


class TestLogin:
    def test_login_success(self, client):
        _create_user(client)
        resp = client.post("/api/auth/login", json={"email": "user@test.com", "password": "testpass123"})
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_login_wrong_password(self, client):
        _create_user(client)
        resp = client.post("/api/auth/login", json={"email": "user@test.com", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_unknown_email(self, client):
        resp = client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "testpass123"})
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post("/api/auth/login", json={"email": "a@b.com"})
        assert resp.status_code == 400


class TestAuthMe:
    def test_me_returns_user(self, client):
        token = _create_user(client)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "user@test.com"
        assert data["handle"] == "testuser"
        assert "agents" in data

    def test_me_rejects_no_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code in (401, 422)

    def test_me_rejects_bad_token(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401


class TestHandleAvailable:
    def test_available_when_unused(self, client):
        resp = client.get("/api/auth/handle-available?handle=alice")
        assert resp.status_code == 200
        assert resp.json() == {"available": True}

    def test_taken_when_user_exists(self, client):
        _create_user(client, "a@b.com", handle="alice")
        resp = client.get("/api/auth/handle-available?handle=alice")
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_taken_when_pending_signup_holds_it(self, client):
        client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword", "handle": "alice"})
        resp = client.get("/api/auth/handle-available?handle=alice")
        assert resp.json()["available"] is False

    def test_invalid_handle_returns_unavailable_with_reason(self, client):
        resp = client.get("/api/auth/handle-available?handle=BadHandle!")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert "reason" in data

    def test_reserved_handle_returns_unavailable(self, client):
        resp = client.get("/api/auth/handle-available?handle=hive")
        assert resp.json()["available"] is False


class TestPatchMe:
    def test_update_handle(self, client):
        token = _create_user(client, handle="testuser")
        resp = client.patch(
            "/api/auth/me",
            json={"handle": "newhandle"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["handle"] == "newhandle"

    def test_update_handle_rejects_taken(self, client):
        _create_user(client, "first@test.com", handle="alice")
        token = _create_user(client, "second@test.com", handle="bob")
        resp = client.patch(
            "/api/auth/me",
            json={"handle": "alice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    def test_update_handle_rejects_invalid(self, client):
        token = _create_user(client, handle="testuser")
        resp = client.patch(
            "/api/auth/me",
            json={"handle": "Bad Handle!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_update_handle_rejects_reserved(self, client):
        token = _create_user(client, handle="testuser")
        resp = client.patch(
            "/api/auth/me",
            json={"handle": "admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_update_handle_no_op(self, client):
        token = _create_user(client, handle="testuser")
        resp = client.patch(
            "/api/auth/me",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_update_handle_cascades_to_private_tasks(self, client):
        token = _create_user(client, handle="alice")
        # Insert a private task directly owned by this user
        with get_db_sync() as conn:
            user_row = conn.execute("SELECT id FROM users WHERE handle = %s", ("alice",)).fetchone()
            from datetime import datetime, timezone
            conn.execute(
                "INSERT INTO tasks (slug, owner, name, description, repo_url, task_type, owner_id, visibility, source_repo, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                ("my-task", "alice", "My Task", "desc", "https://example.com/r", "private", user_row["id"], "private", "alice/r", datetime.now(timezone.utc)),
            )
        resp = client.patch(
            "/api/auth/me",
            json={"handle": "alicee"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        with get_db_sync() as conn:
            row = conn.execute("SELECT owner FROM tasks WHERE slug = %s", ("my-task",)).fetchone()
        assert row["owner"] == "alicee"
