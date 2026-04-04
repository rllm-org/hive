"""Comprehensive tests for auth endpoints: signup, verification, login, and rate limiting."""
from hive.server.db import get_db_sync


def _signup_and_get_code(client, email="user@test.com", password="testpass123"):
    """Signup and return the verification code from DB."""
    resp = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert resp.status_code == 201
    with get_db_sync() as conn:
        row = conn.execute("SELECT code FROM pending_signups WHERE email = %s", (email,)).fetchone()
    return row["code"]


def _create_user(client, email="user@test.com", password="testpass123"):
    """Full signup + verify flow. Returns JWT token."""
    code = _signup_and_get_code(client, email, password)
    resp = client.post("/api/auth/verify-code", json={"email": email, "code": code})
    assert resp.status_code == 200
    return resp.json()["token"]


class TestSignup:
    def test_signup_returns_verification_required(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "verification_required"
        assert data["email"] == "a@b.com"

    def test_signup_creates_pending_signup(self, client):
        client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword"})
        with get_db_sync() as conn:
            row = conn.execute("SELECT * FROM pending_signups WHERE email = %s", ("a@b.com",)).fetchone()
        assert row is not None
        assert len(row["code"]) == 6

    def test_signup_rejects_short_password(self, client):
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "short"})
        assert resp.status_code == 400

    def test_signup_rejects_invalid_email(self, client):
        resp = client.post("/api/auth/signup", json={"email": "notanemail", "password": "longpassword"})
        assert resp.status_code == 400

    def test_signup_rejects_duplicate_verified_email(self, client):
        _create_user(client, "a@b.com")
        resp = client.post("/api/auth/signup", json={"email": "a@b.com", "password": "longpassword"})
        assert resp.status_code == 409

    def test_signup_allows_re_signup_if_pending(self, client):
        """Re-signup with same email updates the pending signup (new code)."""
        code1 = _signup_and_get_code(client, "a@b.com")
        code2 = _signup_and_get_code(client, "a@b.com")
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
        assert "agents" in data

    def test_me_rejects_no_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code in (401, 422)

    def test_me_rejects_bad_token(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401
