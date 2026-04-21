import pytest
from hive.server import claude_oauth


# Real captured stdout fragment from `claude setup-token` under a PTY
_CAPTURED_URL_FRAGMENT = (
    b"\x1b]8;id=18v79on;"
    b"https://claude.com/cai/oauth/authorize"
    b"?code=true&client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    b"&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.com%2Foauth%2Fcode%2Fcallback"
    b"&scope=user%3Ainference"
    b"&code_challenge=qsNmdImMPMxqXET2OAfiXE9Bah0RF-eJc12uQP_r6l8"
    b"&code_challenge_method=S256"
    b"&state=znlhKkFFt-AyHYbrPTqGH3blY0n_hT5TjDXW5qzsLxw"
    b"\x1b\\more text"
)


class TestUrlRegex:
    def test_extracts_hyperlink_oauth_url(self):
        url = claude_oauth._extract_url(_CAPTURED_URL_FRAGMENT)
        assert url is not None
        assert url.startswith("https://claude.com/cai/oauth/authorize?")
        assert "code_challenge=" in url
        assert "client_id=" in url

    def test_extracts_plain_text_oauth_url(self):
        plain = (
            b"Browser didn't open? Use the url below to sign in:\n"
            b"https://claude.com/cai/oauth/authorize?code=true&client_id=9d1c250a"
            b"&code_challenge=abc&state=xyz\n"
            b"Paste code here if prompted >"
        )
        url = claude_oauth._extract_url(plain)
        assert url is not None
        assert url.startswith("https://claude.com/cai/oauth/authorize?")

    def test_rejects_non_matching(self):
        assert claude_oauth._extract_url(b"no oauth url here") is None


class TestTokenRegex:
    def test_extracts_sk_ant_oat_token(self):
        sample = (
            b"Paste code here if prompted >\r\n"
            b"\x1b[2Ksk-ant-oat01-abcd1234EFGH_xyz-0987654321234567890abcd\r\nOK"
        )
        m = claude_oauth._TOKEN_RE.search(sample)
        assert m is not None
        assert m.group(1).startswith(b"sk-ant-oat01-")

    def test_no_match_on_plain_text(self):
        assert claude_oauth._TOKEN_RE.search(b"just chatter") is None


class TestSessionStore:
    def test_reap_expired_removes_stale(self, monkeypatch):
        import threading
        import time
        sess = claude_oauth.ClaudeAuthSession(
            id="stale", user_id=1, pid=0, master_fd=-1,
        )
        sess.created_at = time.time() - claude_oauth._SESSION_TTL_SEC - 10
        sess.done = threading.Event()
        with claude_oauth._SESSIONS_LOCK:
            claude_oauth._SESSIONS["stale"] = sess
        monkeypatch.setattr(claude_oauth, "_kill", lambda s: None)
        claude_oauth._reap_expired()
        with claude_oauth._SESSIONS_LOCK:
            assert "stale" not in claude_oauth._SESSIONS

    def test_submit_code_requires_matching_user(self):
        import threading
        sess = claude_oauth.ClaudeAuthSession(
            id="test", user_id=42, pid=0, master_fd=-1,
        )
        sess.done = threading.Event()
        with claude_oauth._SESSIONS_LOCK:
            claude_oauth._SESSIONS["test"] = sess
        try:
            with pytest.raises(PermissionError):
                claude_oauth.submit_code("test", user_id=999, code="whatever")
        finally:
            with claude_oauth._SESSIONS_LOCK:
                claude_oauth._SESSIONS.pop("test", None)

    def test_submit_code_empty_code_rejected(self):
        with pytest.raises(ValueError):
            claude_oauth.submit_code("any", 1, "")

    def test_submit_code_unknown_session(self):
        with pytest.raises(LookupError):
            claude_oauth.submit_code("no-such-session", 1, "somecode")
