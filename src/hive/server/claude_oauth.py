"""PTY-driven broker around `claude setup-token`.

The Claude Code CLI does not support a non-interactive setup-token flow: it
prints its UI via Ink (React-on-terminal), which requires a raw-TTY stdin.
We run it under a PTY, scrape the OAuth URL from its hyperlink escape code,
and later feed the user-pasted code back to its stdin. The final token is
returned to the caller for persistence (encrypted) in hive's DB.

One session per user — concurrent starts kill the prior session.
"""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field

# Hyperlink escape: \x1b]8;id=...;URL\x1b\\
_URL_RE = re.compile(
    rb"\x1b\]8;id=[^;]*;(https://claude\.com/cai/oauth/authorize[^\x1b\x07]+)",
)
# Final token pattern. setup-token prints a single opaque string on success;
# known format includes `sk-ant-oat01-...` but we accept any long URL-safe run.
_TOKEN_RE = re.compile(rb"(sk-ant-oat01-[A-Za-z0-9_\-]{40,})")
_ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")

_SESSION_TTL_SEC = 600
_URL_WAIT_SEC = 20
_FINISH_WAIT_SEC = 60


@dataclass
class ClaudeAuthSession:
    id: str
    user_id: int
    pid: int
    master_fd: int
    buffer: bytearray = field(default_factory=bytearray)
    auth_url: str | None = None
    token: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    done: threading.Event = field(default_factory=threading.Event)


_SESSIONS: dict[str, ClaudeAuthSession] = {}
_SESSIONS_LOCK = threading.Lock()


def _reap_expired() -> None:
    now = time.time()
    with _SESSIONS_LOCK:
        stale = [
            sid for sid, s in _SESSIONS.items()
            if now - s.created_at > _SESSION_TTL_SEC
        ]
        for sid in stale:
            _kill(_SESSIONS.pop(sid))


def _find_for_user(user_id: int) -> ClaudeAuthSession | None:
    with _SESSIONS_LOCK:
        for s in _SESSIONS.values():
            if s.user_id == user_id:
                return s
    return None


def _kill(session: ClaudeAuthSession) -> None:
    try:
        os.kill(session.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception:
        pass
    try:
        os.close(session.master_fd)
    except OSError:
        pass


def _reader(session: ClaudeAuthSession) -> None:
    while True:
        try:
            r, _, _ = select.select([session.master_fd], [], [], 0.25)
        except (ValueError, OSError):
            break
        if not r:
            if session.done.is_set():
                break
            continue
        try:
            chunk = os.read(session.master_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        session.buffer.extend(chunk)
        if session.auth_url is None:
            m = _URL_RE.search(session.buffer)
            if m:
                session.auth_url = m.group(1).decode("utf-8", "replace")
        if session.token is None:
            m = _TOKEN_RE.search(session.buffer)
            if m:
                session.token = m.group(1).decode("utf-8", "replace")
                session.done.set()
                return


def start_session(user_id: int) -> tuple[str, str]:
    """Spawn `claude setup-token` under a PTY, return (session_id, auth_url)."""
    _reap_expired()

    # Supersede any in-flight session for this user.
    existing = _find_for_user(user_id)
    if existing:
        with _SESSIONS_LOCK:
            _SESSIONS.pop(existing.id, None)
        _kill(existing)
        existing.done.set()

    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise RuntimeError("`claude` CLI not installed on hive server")

    pid, master_fd = pty.fork()
    if pid == 0:
        # child
        try:
            os.execvp(claude_bin, [claude_bin, "setup-token"])
        except Exception:
            os._exit(127)

    sid = uuid.uuid4().hex
    session = ClaudeAuthSession(
        id=sid, user_id=user_id, pid=pid, master_fd=master_fd,
    )
    with _SESSIONS_LOCK:
        _SESSIONS[sid] = session
    threading.Thread(target=_reader, args=(session,), daemon=True).start()

    deadline = time.time() + _URL_WAIT_SEC
    while time.time() < deadline:
        if session.auth_url:
            return sid, session.auth_url
        if session.done.is_set():
            break
        time.sleep(0.1)

    with _SESSIONS_LOCK:
        _SESSIONS.pop(sid, None)
    _kill(session)
    raise RuntimeError("timed out waiting for OAuth URL from `claude setup-token`")


def submit_code(session_id: str, user_id: int, code: str) -> str:
    """Deliver the pasted code to the running setup-token process. Returns the token."""
    code = (code or "").strip()
    if not code:
        raise ValueError("empty code")

    with _SESSIONS_LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise LookupError("auth session not found or expired")
    if session.user_id != user_id:
        raise PermissionError("auth session belongs to a different user")

    try:
        os.write(session.master_fd, (code + "\r").encode())
    except OSError as e:
        raise RuntimeError(f"failed to write code to PTY: {e}") from e

    if not session.done.wait(_FINISH_WAIT_SEC):
        with _SESSIONS_LOCK:
            _SESSIONS.pop(session_id, None)
        _kill(session)
        raise RuntimeError("timed out waiting for `claude setup-token` to return a token")

    token = session.token
    with _SESSIONS_LOCK:
        _SESSIONS.pop(session_id, None)
    _kill(session)
    if not token:
        tail = _ANSI_RE.sub(b"", bytes(session.buffer[-400:])).decode("utf-8", "replace")
        raise RuntimeError(f"no token extracted from setup-token output. Tail: {tail!r}")
    return token


def cancel_session(session_id: str, user_id: int) -> None:
    with _SESSIONS_LOCK:
        session = _SESSIONS.pop(session_id, None)
    if session is None or session.user_id != user_id:
        return
    _kill(session)
