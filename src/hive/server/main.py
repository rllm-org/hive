import asyncio
import json
import os
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any

import base64
import hashlib

import bcrypt
import httpx
import jwt
import psycopg.errors
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse as _BaseJSONResponse

from .db import init_pool, close_pool, get_db, get_db_sync, now, paginate
from .verification import (
    STATUS_PENDING,
    STATUS_RUNNING,
    normalize_task_config,
    parse_task_config,
    recompute_task_stats,
    verification_config_from_raw,
)

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "hive-dev-secret-change-me")

# Derive a Fernet key from JWT_SECRET for encrypting GitHub tokens
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(JWT_SECRET.encode()).digest())
_fernet = Fernet(_fernet_key)


def _encrypt(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet.encrypt(value.encode()).decode()


def _decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet.decrypt(value.encode()).decode()
    except Exception:
        return value  # fallback: return as-is for unencrypted legacy tokens
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24 * 7  # 1 week
GITHUB_USER_APP_CLIENT_ID = os.environ.get("GITHUB_USER_APP_CLIENT_ID", "")
GITHUB_USER_APP_CLIENT_SECRET = os.environ.get("GITHUB_USER_APP_CLIENT_SECRET", "")
GITHUB_USER_APP_SLUG = os.environ.get("GITHUB_USER_APP_SLUG", "")


def _gh_user_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _exchange_github_code(code: str) -> dict:
    if not GITHUB_USER_APP_CLIENT_ID or not GITHUB_USER_APP_CLIENT_SECRET:
        raise HTTPException(501, "GitHub OAuth not configured")
    resp = httpx.post("https://github.com/login/oauth/access_token", json={
        "client_id": GITHUB_USER_APP_CLIENT_ID,
        "client_secret": GITHUB_USER_APP_CLIENT_SECRET,
        "code": code,
    }, headers={"Accept": "application/json"}, timeout=15)
    if resp.status_code != 200:
        raise HTTPException(502, "GitHub OAuth exchange failed")
    data = resp.json()
    gh_token = data.get("access_token")
    if not gh_token:
        raise HTTPException(400, data.get("error_description", "OAuth exchange failed"))
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")
    gh_user = httpx.get("https://api.github.com/user", headers=_gh_user_headers(gh_token), timeout=15).json()
    gh_id = gh_user.get("id")
    gh_username = gh_user.get("login", "")
    gh_avatar = gh_user.get("avatar_url", "")
    if not gh_id:
        raise HTTPException(502, "failed to fetch GitHub user info")
    return {
        "token": gh_token, "refresh_token": refresh_token, "expires_in": expires_in,
        "id": gh_id, "username": gh_username, "avatar": gh_avatar,
    }


def _refresh_github_token(refresh_token: str) -> dict | None:
    """Refresh an expired GitHub user access token."""
    if not refresh_token:
        return None
    resp = httpx.post("https://github.com/login/oauth/access_token", json={
        "client_id": GITHUB_USER_APP_CLIENT_ID,
        "client_secret": GITHUB_USER_APP_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, headers={"Accept": "application/json"}, timeout=15)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data.get("access_token"):
        return None
    return {
        "token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
        "expires_in": data.get("expires_in"),
    }


async def _get_valid_github_token(user_id: int) -> str:
    """Get a valid GitHub token, refreshing if expired."""
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT github_token, github_refresh_token, github_token_expires FROM users WHERE id = %s",
            (user_id,),
        )).fetchone()
        if not row or not row["github_token"]:
            raise HTTPException(400, "GitHub not connected")
        # If no expiry set (old OAuth tokens) or still valid, decrypt and return
        if not row["github_token_expires"] or row["github_token_expires"] > now():
            return _decrypt(row["github_token"])
        # Try to refresh
        refreshed = await asyncio.to_thread(_refresh_github_token, _decrypt(row["github_refresh_token"]))
        if not refreshed:
            raise HTTPException(401, "GitHub token expired — please reconnect")
        token_expires = now() + timedelta(seconds=refreshed["expires_in"]) if refreshed["expires_in"] else None
        await conn.execute(
            "UPDATE users SET github_token = %s, github_refresh_token = %s, github_token_expires = %s WHERE id = %s",
            (_encrypt(refreshed["token"]), _encrypt(refreshed["refresh_token"]), token_expires, user_id),
        )
        return refreshed["token"]


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _create_jwt(user_id: int, email: str, role: str, handle: str | None = None) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    if handle is not None:
        payload["handle"] = handle
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "invalid token")


async def require_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "expected Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    # API key: resolve to user dict
    if token.startswith("hive_"):
        user_id = await _resolve_api_key(token)
        if not user_id:
            raise HTTPException(401, "invalid API key")
        async with get_db() as conn:
            row = await (await conn.execute("SELECT id, email, role FROM users WHERE id = %s", (user_id,))).fetchone()
            if not row:
                raise HTTPException(401, "user not found")
            return {"sub": str(row["id"]), "email": row["email"], "role": row["role"]}
    return _decode_jwt(token)


async def require_admin(x_admin_key: str = "", authorization: str = ""):
    """Validate admin access via static key, JWT admin role, or API key of admin user."""
    # Try static admin key first
    if ADMIN_KEY and x_admin_key == ADMIN_KEY:
        return
    # Try JWT
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        # API key of admin user
        if token.startswith("hive_"):
            user_id = await _resolve_api_key(token)
            if user_id:
                async with get_db() as conn:
                    row = await (await conn.execute("SELECT role FROM users WHERE id = %s", (user_id,))).fetchone()
                    if row and row["role"] == "admin":
                        return
        else:
            try:
                payload = _decode_jwt(token)
                if payload.get("role") == "admin":
                    return
            except HTTPException:
                pass
    raise HTTPException(403, "admin access required")


async def _get_user_id_from_auth(authorization: str = "") -> int | None:
    """Extract user_id from JWT or API key, or None if not authenticated."""
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if token.startswith("hive_"):
        return await _resolve_api_key(token)
    try:
        payload = _decode_jwt(token)
        return int(payload["sub"])
    except (HTTPException, KeyError, ValueError):
        return None


def _generate_api_key() -> tuple[str, str, str]:
    """Generate API key. Returns (raw_key, prefix, bcrypt_hash)."""
    raw = f"hive_{uuid.uuid4()}"
    prefix = raw[:12]  # e.g. "hive_e715e163"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    return raw, prefix, hashed


async def _resolve_api_key(api_key: str) -> int | None:
    """Look up user_id by API key prefix, then verify with bcrypt."""
    if not api_key or not api_key.startswith("hive_"):
        return None
    prefix = api_key[:12]
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT id, api_key FROM users WHERE api_key_prefix = %s", (prefix,)
        )).fetchone()
        if not row or not row["api_key"]:
            return None
        if bcrypt.checkpw(api_key.encode(), row["api_key"].encode()):
            return row["id"]
        return None


async def require_admin_or_task_owner(owner: str, slug: str, x_admin_key: str = "", authorization: str = ""):
    """Allow admin access OR task owner access."""
    if ADMIN_KEY and x_admin_key == ADMIN_KEY:
        return
    user_id = await _get_user_id_from_auth(authorization)
    if user_id:
        async with get_db() as conn:
            user_row = await (await conn.execute("SELECT role FROM users WHERE id = %s", (user_id,))).fetchone()
            if user_row and user_row["role"] == "admin":
                return
            task_row = await (await conn.execute(
                "SELECT owner_id FROM tasks WHERE owner = %s AND slug = %s", (owner, slug)
            )).fetchone()
            if task_row and task_row["owner_id"] == user_id:
                return
    raise HTTPException(403, "admin or task owner access required")


async def require_task_access(owner: str, slug: str, authorization: str = "", x_admin_key: str = ""):
    """Public tasks: open to all. Private tasks: require owner or admin."""
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT visibility, owner_id FROM tasks WHERE owner = %s AND slug = %s", (owner, slug)
        )).fetchone()
        if not row:
            raise HTTPException(404, "task not found")
        if row["visibility"] == "public":
            return
        if ADMIN_KEY and x_admin_key == ADMIN_KEY:
            return
        user_id = await _get_user_id_from_auth(authorization)
        if user_id:
            if user_id == row["owner_id"]:
                return
            user_row = await (await conn.execute("SELECT role FROM users WHERE id = %s", (user_id,))).fetchone()
            if user_row and user_row["role"] == "admin":
                return
        raise HTTPException(404, "task not found")


class JSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, default=_json_default).encode("utf-8")


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not JSON serializable")
from .email import send_verification_code, send_password_reset_code
from .github import get_github_app, GitHubApp
from .names import generate_name


def _parse_sort(raw: str, allowed: dict[str, str]) -> str:
    """Parse 'field' or 'field:asc|desc' into SQL ORDER BY clause.

    allowed maps sort names to SQL column expressions, e.g. {"score": "r.score", "recent": "r.created_at"}.
    Default direction is DESC.
    """
    parts = raw.split(":", 1)
    field = parts[0]
    direction = parts[1].upper() if len(parts) > 1 else "DESC"
    if direction not in ("ASC", "DESC"):
        direction = "DESC"
    col = allowed.get(field, list(allowed.values())[0])
    return f"{col} {direction}"


def _fork_clone_response(fork_row: Any, upstream_url: str) -> JSONResponse:
    """Build the response for an existing fork without inventing replay metadata."""

    if not fork_row["base_sha"]:
        raise HTTPException(409, "existing fork is missing pinned base SHA; delete it and clone again")

    return JSONResponse(
        {
            "fork_url": fork_row["fork_url"],
            "ssh_url": fork_row["ssh_url"],
            "upstream_url": upstream_url,
            "private_key": "",
            "base_sha": fork_row["base_sha"],
        },
        status_code=201,
    )


def _sync_tasks_from_github():
    """Discover task--* repos in the GitHub org and register any missing tasks.

    Runs in a thread via asyncio.to_thread — uses sync DB and sync httpx.
    """
    try:
        gh = get_github_app()
        import httpx
        repos = []
        page = 1
        while True:
            resp = httpx.get(f"https://api.github.com/orgs/{gh.org}/repos",
                             params={"per_page": 100, "page": page},
                             headers=gh.headers(), timeout=15)
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        with get_db_sync() as conn:
            for repo in repos:
                rname = repo["name"]
                if not rname.startswith("task--"):
                    continue
                slug = rname.removeprefix("task--")
                if conn.execute("SELECT id FROM tasks WHERE owner = %s AND slug = %s", (PLATFORM_OWNER, slug)).fetchone():
                    continue
                desc = repo.get("description") or ""
                conn.execute(
                    "INSERT INTO tasks (slug, owner, name, description, repo_url, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (slug, PLATFORM_OWNER, slug, desc, repo["html_url"], now()),
                )
    except Exception:
        pass  # best-effort; server starts even if GitHub is unreachable


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="Evolve Hive Mind Server", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

router = APIRouter(prefix="/api")


# --- Auth endpoints ---

def _generate_code() -> str:
    import secrets
    return f"{secrets.randbelow(1000000):06d}"


@router.post("/auth/signup")
async def auth_signup(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    handle = body.get("handle", "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "valid email required")
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    if not handle:
        raise HTTPException(400, "handle required")
    _validate_handle(handle)
    hashed = _hash_password(password)
    code = _generate_code()
    expires = now() + timedelta(minutes=10)
    async with get_db() as conn:
        existing = await (await conn.execute(
            "SELECT id FROM users WHERE email = %s", (email,)
        )).fetchone()
        if existing:
            raise HTTPException(409, "email already registered")
        # Reject if handle is taken by an existing user
        existing_handle = await (await conn.execute(
            "SELECT id FROM users WHERE handle = %s", (handle,)
        )).fetchone()
        if existing_handle:
            raise HTTPException(409, "handle already taken")
        # Reject if handle is locked by another in-flight signup (different email)
        locked = await (await conn.execute(
            "SELECT email FROM pending_signups WHERE handle = %s AND email != %s",
            (handle, email),
        )).fetchone()
        if locked:
            raise HTTPException(409, "handle already taken")
        # Upsert into pending_signups (allows re-signup if code expired)
        await conn.execute(
            "INSERT INTO pending_signups (email, password, handle, code, expires_at, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (email) DO UPDATE SET password = %s, handle = %s, code = %s, expires_at = %s",
            (email, hashed, handle, code, expires, now(), hashed, handle, code, expires),
        )
    try:
        await send_verification_code(email, code)
    except Exception:
        pass
    return JSONResponse({"status": "verification_required", "email": email}, status_code=201)


@router.post("/auth/verify-code")
async def auth_verify_code(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    code = body.get("code", "").strip()
    if not email or not code:
        raise HTTPException(400, "email and code required")
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT email, password, handle, code, expires_at, attempts FROM pending_signups WHERE email = %s", (email,)
        )).fetchone()
    if not row:
        raise HTTPException(404, "no pending signup found — please sign up first")
    if row["attempts"] >= 5:
        raise HTTPException(429, "too many attempts — request a new code")
    if row["code"] != code:
        async with get_db() as conn:
            await conn.execute(
                "UPDATE pending_signups SET attempts = attempts + 1 WHERE email = %s", (email,)
            )
        raise HTTPException(400, "invalid code")
    if row["expires_at"] < now():
        raise HTTPException(400, "code expired — please request a new one")
    handle = row["handle"]
    if not handle:
        raise HTTPException(400, "signup is missing a handle — please sign up again")
    # Create the real user
    user_uuid = str(uuid.uuid4())
    async with get_db() as conn:
        # Race protection: re-check handle uniqueness right before insert
        existing_handle = await (await conn.execute(
            "SELECT id FROM users WHERE handle = %s", (handle,)
        )).fetchone()
        if existing_handle:
            raise HTTPException(409, "handle was claimed by another user — please sign up again with a different handle")
        try:
            user_row = await (await conn.execute(
                "INSERT INTO users (email, password, handle, uuid, created_at)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id, role",
                (row["email"], row["password"], handle, user_uuid, now()),
            )).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "handle was claimed by another user — please sign up again with a different handle")
        await conn.execute("DELETE FROM pending_signups WHERE email = %s", (email,))
    token = _create_jwt(user_row["id"], email, user_row["role"], handle)
    return {"token": token, "user": {"id": user_row["id"], "email": email, "handle": handle, "role": user_row["role"]}}


@router.post("/auth/resend-code")
async def auth_resend_code(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    if not email:
        raise HTTPException(400, "email required")
    code = _generate_code()
    expires = now() + timedelta(minutes=10)
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT email FROM pending_signups WHERE email = %s", (email,)
        )).fetchone()
        if not row:
            raise HTTPException(404, "no pending signup found")
        await conn.execute(
            "UPDATE pending_signups SET code = %s, expires_at = %s, attempts = 0 WHERE email = %s",
            (code, expires, email),
        )
    try:
        await send_verification_code(email, code)
    except Exception:
        raise HTTPException(502, "failed to send verification email")
    return {"status": "sent"}


@router.post("/auth/login")
async def auth_login(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(400, "email and password required")
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT id, email, password, role, handle FROM users WHERE email = %s", (email,)
        )).fetchone()
    if not row or not _check_password(password, row["password"]):
        raise HTTPException(401, "invalid email or password")
    token = _create_jwt(row["id"], row["email"], row["role"], row["handle"])
    return {"token": token, "user": {"id": row["id"], "email": row["email"], "handle": row["handle"], "role": row["role"]}}

@router.post("/auth/forgot-password")
async def auth_forgot_password(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "valid email required")
    code = _generate_code()
    expires = now() + timedelta(minutes=10)
    async with get_db() as conn:
        user = await (await conn.execute(
            "SELECT id FROM users WHERE email = %s", (email,)
        )).fetchone()
        if user:
            await conn.execute(
                "INSERT INTO password_resets (email, code, expires_at, attempts, created_at)"
                " VALUES (%s, %s, %s, 0, %s)"
                " ON CONFLICT (email) DO UPDATE SET code = %s, expires_at = %s, attempts = 0",
                (email, code, expires, now(), code, expires),
            )
            try:
                await send_password_reset_code(email, code)
            except Exception:
                pass
    return {"status": "sent"}


@router.post("/auth/reset-password")
async def auth_reset_password(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    code = body.get("code", "").strip()
    new_password = body.get("password", "")
    if not email or not code:
        raise HTTPException(400, "email and code required")
    if len(new_password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT code, expires_at, attempts FROM password_resets WHERE email = %s", (email,)
        )).fetchone()
    if not row:
        raise HTTPException(400, "no reset requested \u2014 use forgot password first")
    if row["attempts"] >= 5:
        raise HTTPException(429, "too many attempts \u2014 request a new code")
    if row["code"] != code:
        async with get_db() as conn:
            await conn.execute(
                "UPDATE password_resets SET attempts = attempts + 1 WHERE email = %s", (email,)
            )
        raise HTTPException(400, "invalid code")
    if row["expires_at"] < now():
        raise HTTPException(400, "code expired \u2014 request a new one")
    hashed = _hash_password(new_password)
    async with get_db() as conn:
        await conn.execute(
            "UPDATE users SET password = %s WHERE email = %s", (hashed, email)
        )
        await conn.execute("DELETE FROM password_resets WHERE email = %s", (email,))
    return {"status": "password_reset"}


@router.get("/auth/me")
async def auth_me(user: dict = Depends(require_user)):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT id, email, handle, role, github_username, avatar_url, uuid, created_at FROM users WHERE id = %s", (user_id,)
        )).fetchone()
        if not row:
            raise HTTPException(404, "user not found")
        agents = await (await conn.execute(
            "SELECT id, registered_at, last_seen_at, total_runs FROM agents WHERE user_id = %s ORDER BY last_seen_at DESC",
            (user_id,),
        )).fetchall()
    return {
        "id": row["id"], "email": row["email"], "handle": row["handle"], "role": row["role"],
        "github_username": row["github_username"], "avatar_url": row["avatar_url"], "uuid": row["uuid"], "created_at": row["created_at"],
        "agents": [{"id": a["id"], "registered_at": a["registered_at"], "last_seen_at": a["last_seen_at"], "total_runs": a["total_runs"]} for a in agents],
    }


@router.get("/auth/handle-available")
async def auth_handle_available(handle: str = Query(...)):
    """Public endpoint for debounced handle uniqueness check during signup."""
    handle = handle.strip().lower()
    try:
        _validate_handle(handle)
    except HTTPException as e:
        return {"available": False, "reason": e.detail}
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM users WHERE handle = %s"
            " UNION ALL SELECT 1 FROM pending_signups WHERE handle = %s LIMIT 1",
            (handle, handle),
        )).fetchone()
    return {"available": row is None}


@router.patch("/auth/me")
async def auth_update_me(body: dict[str, Any], user: dict = Depends(require_user)):
    """Update editable user fields. Currently supports `handle`."""
    user_id = int(user["sub"])
    updates: dict[str, Any] = {}
    if "handle" in body:
        new_handle = (body.get("handle") or "").strip().lower()
        _validate_handle(new_handle)
        async with get_db() as conn:
            existing = await (await conn.execute(
                "SELECT id FROM users WHERE handle = %s AND id != %s", (new_handle, user_id)
            )).fetchone()
            if existing:
                raise HTTPException(409, "handle already taken")
            try:
                await conn.execute(
                    "UPDATE users SET handle = %s WHERE id = %s", (new_handle, user_id)
                )
            except psycopg.errors.UniqueViolation:
                raise HTTPException(409, "handle already taken")
            # Cascade: update tasks.owner for the user's private tasks so URLs follow
            await conn.execute(
                "UPDATE tasks SET owner = %s WHERE owner_id = %s AND visibility = 'private'",
                (new_handle, user_id),
            )
        updates["handle"] = new_handle
    if not updates:
        raise HTTPException(400, "no updatable fields provided")
    return updates


@router.get("/auth/api-key")
async def get_api_key(user: dict = Depends(require_user)):
    """Return the user's API key prefix (full key is never retrievable after creation)."""
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await (await conn.execute("SELECT api_key_prefix FROM users WHERE id = %s", (user_id,))).fetchone()
        if not row:
            raise HTTPException(404, "user not found")
    return {"api_key_prefix": row["api_key_prefix"]}


@router.post("/auth/api-key/regenerate")
async def regenerate_api_key(user: dict = Depends(require_user)):
    """Generate a new API key, invalidating the old one. Returns the raw key once."""
    user_id = int(user["sub"])
    raw_key, key_prefix, key_hash = _generate_api_key()
    async with get_db() as conn:
        await conn.execute("UPDATE users SET api_key = %s, api_key_prefix = %s WHERE id = %s", (key_hash, key_prefix, user_id))
    return {"api_key": raw_key}


@router.post("/auth/claim")
async def auth_claim(body: dict[str, Any], user: dict = Depends(require_user)):
    agent_token = body.get("token", "").strip()
    if not agent_token:
        raise HTTPException(400, "agent token required")
    user_id = int(user["sub"])
    async with get_db() as conn:
        agent = await (await conn.execute(
            "SELECT id, user_id FROM agents WHERE token = %s", (agent_token,)
        )).fetchone()
        if not agent:
            raise HTTPException(404, "invalid agent token")
        if agent["id"] == agent_token:
            raise HTTPException(400, "legacy agent — ask an admin to regenerate its token before claiming")
        if agent["user_id"] is not None and agent["user_id"] != user_id:
            raise HTTPException(409, "agent already claimed by another user")
        if agent["user_id"] == user_id:
            return {"agent_id": agent["id"], "status": "already_claimed"}
        await conn.execute(
            "UPDATE agents SET user_id = %s WHERE id = %s", (user_id, agent["id"])
        )
    return {"agent_id": agent["id"], "status": "claimed"}




@router.get("/auth/config")
async def auth_config():
    """Return auth configuration (which OAuth providers are available)."""
    providers = []
    if GITHUB_USER_APP_CLIENT_ID and GITHUB_USER_APP_CLIENT_SECRET:
        providers.append("github")
    result: dict = {"oauth_providers": providers}
    if GITHUB_USER_APP_SLUG:
        result["github_app_install_url"] = f"https://github.com/apps/{GITHUB_USER_APP_SLUG}/installations/new"
    github_app_slug = os.environ.get("GITHUB_APP_SLUG", "")
    if github_app_slug:
        result["github_agent_app_install_url"] = f"https://github.com/apps/{github_app_slug}/installations/new"
    return result


@router.get("/auth/github/authorize")
async def auth_github_authorize(mode: str = Query("login"), redirect_uri: str = Query(...)):
    """Return the GitHub OAuth authorization URL with CSRF-safe state token."""
    if not GITHUB_USER_APP_CLIENT_ID:
        raise HTTPException(501, "GitHub OAuth not configured")
    import secrets
    state_token = secrets.token_urlsafe(32)
    async with get_db() as conn:
        # Clean up expired states, then insert new one
        await conn.execute("DELETE FROM oauth_states WHERE expires_at < %s", (now(),))
        await conn.execute(
            "INSERT INTO oauth_states (token, mode, expires_at) VALUES (%s, %s, %s)",
            (state_token, mode, now() + timedelta(minutes=10)),
        )
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_USER_APP_CLIENT_ID}"
        f"&scope=repo,read:user,user:email"
        f"&redirect_uri={redirect_uri}"
        f"&state={state_token}"
    )
    return {"url": url, "state": state_token}


@router.post("/auth/github")
async def auth_github(body: dict[str, Any]):
    code = body.get("code", "")
    state = body.get("state", "")
    if not code:
        raise HTTPException(400, "code required")
    # Validate CSRF state token
    if state:
        async with get_db() as conn:
            state_row = await (await conn.execute(
                "SELECT mode FROM oauth_states WHERE token = %s AND expires_at > %s", (state, now())
            )).fetchone()
            if state_row:
                await conn.execute("DELETE FROM oauth_states WHERE token = %s", (state,))
            else:
                raise HTTPException(400, "invalid or expired OAuth state")
    gh = await asyncio.to_thread(_exchange_github_code, code)
    gh_token_plain, gh_id, gh_username, gh_avatar = gh["token"], gh["id"], gh["username"], gh["avatar"]
    gh_refresh_plain = gh.get("refresh_token")
    gh_expires = now() + timedelta(seconds=gh["expires_in"]) if gh.get("expires_in") else None
    gh_token_enc, gh_refresh_enc = _encrypt(gh_token_plain), _encrypt(gh_refresh_plain)
    # Fetch email (may need separate call if private)
    def _fetch_email():
        user_resp = httpx.get("https://api.github.com/user", headers=_gh_user_headers(gh_token_plain), timeout=15)
        email = None
        if user_resp.status_code == 200:
            email = user_resp.json().get("email")
        if not email:
            emails_resp = httpx.get("https://api.github.com/user/emails", headers=_gh_user_headers(gh_token_plain), timeout=15)
            if emails_resp.status_code == 200:
                for e in emails_resp.json():
                    if e.get("primary"):
                        return e["email"]
        return email or f"{gh_username}@users.noreply.github.com"
    gh_email = (await asyncio.to_thread(_fetch_email)).lower()
    async with get_db() as conn:
        # Check if user with this github_id already exists
        row = await (await conn.execute(
            "SELECT id, email, role, handle FROM users WHERE github_id = %s", (gh_id,)
        )).fetchone()
        if row:
            await conn.execute(
                "UPDATE users SET github_token = %s, github_refresh_token = %s, github_token_expires = %s, github_username = %s, avatar_url = %s, github_connected_at = %s WHERE id = %s",
                (gh_token_enc, gh_refresh_enc, gh_expires, gh_username, gh_avatar, now(), row["id"]),
            )
            token = _create_jwt(row["id"], row["email"], row["role"], row["handle"])
            return {"token": token, "user": {"id": row["id"], "email": row["email"], "handle": row["handle"], "role": row["role"], "github_username": gh_username, "avatar_url": gh_avatar}}
        # Auto-link if email matches (all users in DB are verified)
        row = await (await conn.execute(
            "SELECT id, email, role, handle FROM users WHERE email = %s", (gh_email,)
        )).fetchone()
        if row:
            await conn.execute(
                "UPDATE users SET github_id = %s, github_token = %s, github_refresh_token = %s, github_token_expires = %s, github_username = %s, avatar_url = %s, github_connected_at = %s WHERE id = %s",
                (gh_id, gh_token_enc, gh_refresh_enc, gh_expires, gh_username, gh_avatar, now(), row["id"]),
            )
            token = _create_jwt(row["id"], row["email"], row["role"], row["handle"])
            return {"token": token, "user": {"id": row["id"], "email": row["email"], "handle": row["handle"], "role": row["role"], "github_username": gh_username, "avatar_url": gh_avatar}}
        # Create new user — auto-derive handle from github_username, fallback to email prefix
        base_handle = _sanitize_to_handle(gh_username or "") or _sanitize_to_handle(gh_email.split("@", 1)[0])
        new_handle = await _generate_unique_handle(conn, base_handle)
        user_uuid = str(uuid.uuid4())
        row = await (await conn.execute(
            "INSERT INTO users (email, handle, github_id, github_username, github_token, github_refresh_token, github_token_expires, avatar_url, github_connected_at, uuid, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, role",
            (gh_email, new_handle, gh_id, gh_username, gh_token_enc, gh_refresh_enc, gh_expires, gh_avatar, now(), user_uuid, now()),
        )).fetchone()
    token = _create_jwt(row["id"], gh_email, row["role"], new_handle)
    return JSONResponse(
        {"token": token, "user": {"id": row["id"], "email": gh_email, "handle": new_handle, "role": row["role"], "github_username": gh_username, "avatar_url": gh_avatar}},
        status_code=201,
    )


@router.post("/auth/github/connect")
async def auth_github_connect(body: dict[str, Any], user: dict = Depends(require_user)):
    code = body.get("code", "")
    if not code:
        raise HTTPException(400, "code required")
    gh = await asyncio.to_thread(_exchange_github_code, code)
    gh_token_plain, gh_id, gh_username, gh_avatar = gh["token"], gh["id"], gh["username"], gh["avatar"]
    gh_refresh_plain = gh.get("refresh_token")
    gh_expires = now() + timedelta(seconds=gh["expires_in"]) if gh.get("expires_in") else None
    user_id = int(user["sub"])
    async with get_db() as conn:
        # Check if this GitHub account is already linked to another user
        existing = await (await conn.execute(
            "SELECT id FROM users WHERE github_id = %s AND id != %s", (gh_id, user_id)
        )).fetchone()
        if existing:
            raise HTTPException(409, "this GitHub account is already linked to another user")
        await conn.execute(
            "UPDATE users SET github_id = %s, github_token = %s, github_refresh_token = %s, github_token_expires = %s, github_username = %s, avatar_url = %s, github_connected_at = %s WHERE id = %s",
            (gh_id, _encrypt(gh_token_plain), _encrypt(gh_refresh_plain), gh_expires, gh_username, gh_avatar, now(), user_id),
        )
    return {"github_username": gh_username, "avatar_url": gh_avatar, "status": "connected"}


@router.delete("/auth/github")
async def auth_github_disconnect(user: dict = Depends(require_user)):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT password FROM users WHERE id = %s", (user_id,)
        )).fetchone()
        if not row or not row["password"]:
            raise HTTPException(400, "cannot disconnect GitHub — no password set. Set a password first.")
        await conn.execute(
            "UPDATE users SET github_id = NULL, github_token = NULL, github_refresh_token = NULL, github_token_expires = NULL, github_username = NULL, github_connected_at = NULL, avatar_url = NULL WHERE id = %s",
            (user_id,),
        )
    return {"status": "disconnected"}


@router.get("/auth/github/repos")
async def auth_github_repos(user: dict = Depends(require_user), page: int = 1, per_page: int = 30):
    user_id = int(user["sub"])
    gh_token = await _get_valid_github_token(user_id)
    # Get user's GitHub username to filter out org installations
    async with get_db() as conn:
        user_row = await (await conn.execute(
            "SELECT github_username FROM users WHERE id = %s", (user_id,)
        )).fetchone()
    github_username = user_row["github_username"] if user_row else None
    def _fetch():
        headers = _gh_user_headers(gh_token)
        inst_resp = httpx.get("https://api.github.com/user/installations", headers=headers, timeout=15)
        if inst_resp.status_code == 200:
            installations = inst_resp.json().get("installations", [])
            # Filter out the hive org installation (public tasks only)
            installations = [i for i in installations
                             if i.get("account", {}).get("login", "").lower() != "hive-swarm-hub"]
            if installations:
                repos = []
                for inst in installations:
                    r = httpx.get(
                        f"https://api.github.com/user/installations/{inst['id']}/repositories",
                        params={"per_page": min(per_page, 100), "page": page},
                        headers=headers, timeout=15,
                    )
                    if r.status_code == 200:
                        for repo in r.json().get("repositories", []):
                            repos.append({"full_name": repo["full_name"], "name": repo["name"], "private": repo["private"],
                                          "description": repo.get("description"), "url": repo["html_url"],
                                          "default_branch": repo["default_branch"], "updated_at": repo["updated_at"]})
                return {"repos": repos, "installed": True}
        return {"repos": [], "installed": False}
    result = await asyncio.to_thread(_fetch)
    return {"repos": result["repos"], "installed": result["installed"], "page": page}


def _resolve_agent_token(token: str = "", x_agent_token: str = "") -> str:
    """Get agent token from query param or header."""
    return x_agent_token or token


async def get_agent(token: str, conn) -> str:
    # Try real token first, fall back to legacy id-as-token
    row = await (await conn.execute("SELECT id FROM agents WHERE token = %s", (token,))).fetchone()
    if not row:
        row = await (await conn.execute("SELECT id FROM agents WHERE id = %s", (token,))).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    await conn.execute("UPDATE agents SET last_seen_at = %s WHERE id = %s", (now(), row["id"]))
    return row["id"]


_AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,18}[a-z0-9]$")


def _validate_agent_id(agent_id: str):
    if len(agent_id) < 2 or len(agent_id) > 20:
        raise HTTPException(400, "agent id must be 2-20 characters")
    if not _AGENT_ID_RE.match(agent_id):
        raise HTTPException(400, "agent id must contain only lowercase letters, digits, and hyphens, and start/end with a letter or digit")
    if "--" in agent_id:
        raise HTTPException(400, "agent id must not contain consecutive hyphens (reserved as delimiter)")


@router.post("/register", status_code=201)
async def register(body: dict[str, Any] = {}):
    preferred, ts = body.get("preferred_name"), now()
    agent_token = str(uuid.uuid4())
    async with get_db() as conn:
        if preferred:
            _validate_agent_id(preferred)
            if await (await conn.execute("SELECT 1 FROM agents WHERE id = %s", (preferred,))).fetchone():
                raise HTTPException(409, f"name '{preferred}' is already taken")
            agent_id = preferred
        else:
            agent_id = await generate_name(conn)
        try:
            await conn.execute(
                "INSERT INTO agents (id, token, registered_at, last_seen_at) VALUES (%s, %s, %s, %s)",
                (agent_id, agent_token, ts, ts),
            )
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, f"name '{agent_id}' is already taken")
    return JSONResponse({"id": agent_id, "token": agent_token, "registered_at": ts}, status_code=201)


@router.post("/register/batch", status_code=201)
async def register_batch(body: dict[str, Any] = {}):
    count = body.get("count", 1)
    if not isinstance(count, int) or count < 1 or count > 50:
        raise HTTPException(400, "count must be 1-50")
    prefix = body.get("prefix")
    ts = now()
    agents = []
    async with get_db() as conn:
        for i in range(count):
            agent_token = str(uuid.uuid4())
            if prefix:
                agent_id = f"{prefix}-{i + 1}"
                _validate_agent_id(agent_id)
            else:
                agent_id = await generate_name(conn)
            try:
                await conn.execute(
                    "INSERT INTO agents (id, token, registered_at, last_seen_at) VALUES (%s, %s, %s, %s)",
                    (agent_id, agent_token, ts, ts),
                )
            except psycopg.errors.UniqueViolation:
                await conn.rollback()
                raise HTTPException(409, f"name '{agent_id}' is already taken")
            agents.append({"id": agent_id, "token": agent_token})
    return JSONResponse({"agents": agents}, status_code=201)


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,18}[a-z0-9]$")
_TASK_DESCRIPTION_MAX_LENGTH = 350

PLATFORM_OWNER = os.environ.get("HIVE_PLATFORM_OWNER", "hive")

# Reserved handles — keep in sync with db.py _RESERVED_HANDLES
RESERVED_HANDLES = frozenset({
    "hive",  # platform owner namespace
    "admin", "api", "auth", "settings", "login", "signup",
    "new", "explore", "trending",  # future-proofing
})

_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,18}[a-z0-9]$")


def _validate_slug(slug: str):
    if len(slug) < 2 or len(slug) > 20:
        raise HTTPException(400, "slug must be 2-20 characters")
    if not _SLUG_RE.match(slug):
        raise HTTPException(400, "slug must contain only lowercase letters, digits, and hyphens, and start/end with a letter or digit")
    if "--" in slug:
        raise HTTPException(400, "slug must not contain consecutive hyphens (reserved as delimiter)")


def _validate_handle(handle: str):
    if not isinstance(handle, str):
        raise HTTPException(400, "handle must be a string")
    if len(handle) < 2 or len(handle) > 20:
        raise HTTPException(400, "handle must be 2-20 characters")
    if not _HANDLE_RE.match(handle):
        raise HTTPException(400, "handle must contain only lowercase letters, digits, and hyphens, and start/end with a letter or digit")
    if "--" in handle:
        raise HTTPException(400, "handle must not contain consecutive hyphens")
    if handle.lower() in RESERVED_HANDLES:
        raise HTTPException(400, f"'{handle}' is reserved")


def _sanitize_to_handle(text: str) -> str:
    """Sanitize an arbitrary string (email prefix, github username) into a valid handle base.
    Returns '' if the result is too short."""
    out = re.sub(r"[^a-z0-9-]+", "-", text.lower())
    out = re.sub(r"-+", "-", out).strip("-")
    if len(out) < 2:
        return ""
    return out[:20].rstrip("-")


async def _generate_unique_handle(conn: Any, base: str, fallback_id: int | None = None) -> str:
    """Find a unique handle starting from `base`. Appends -2, -3, ... on collision.
    Falls back to user-{id} if base is empty."""
    if not base:
        base = f"user-{fallback_id}" if fallback_id else "user"
    candidate = base
    i = 2
    while True:
        if candidate.lower() not in RESERVED_HANDLES:
            row = await (await conn.execute(
                "SELECT 1 FROM users WHERE handle = %s"
                " UNION ALL SELECT 1 FROM pending_signups WHERE handle = %s",
                (candidate, candidate)
            )).fetchone()
            if not row:
                return candidate
        suffix = f"-{i}"
        trimmed = base[: max(2, 20 - len(suffix))].rstrip("-")
        candidate = f"{trimmed}{suffix}"
        i += 1
        if i > 1000:  # safety
            raise HTTPException(500, "could not generate unique handle")


def _validate_task_description(description: str):
    """Reject task descriptions that exceed the current public limit."""

    if len(description) > _TASK_DESCRIPTION_MAX_LENGTH:
        raise HTTPException(400, f"description must be {_TASK_DESCRIPTION_MAX_LENGTH} characters or fewer")


async def _load_task_or_404(conn: Any, owner: str, slug: str) -> tuple[dict[str, Any], Any]:
    """Fetch a task by owner+slug and its normalized verification config."""
    row = await (await conn.execute(
        "SELECT * FROM tasks WHERE owner = %s AND slug = %s", (owner, slug)
    )).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    task = dict(row)
    return task, verification_config_from_raw(task.get("config"))


async def _load_task_by_id(conn: Any, task_id: int) -> tuple[dict[str, Any], Any]:
    """Fetch a task by integer PK and its normalized verification config."""
    row = await (await conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    task = dict(row)
    return task, verification_config_from_raw(task.get("config"))


@router.post("/tasks", status_code=201)
async def create_task(
    archive: UploadFile = File(...),
    slug: str = Form(..., alias="slug"),
    name: str = Form(...),
    description: str = Form(...),
    config: str | None = Form(None),
    x_admin_key: str = Header(""),
    authorization: str = Header(""),
):
    """Create the backing GitHub repo for a task draft."""

    await require_admin(x_admin_key, authorization)
    _validate_slug(slug)
    _validate_task_description(description)
    normalized_config = config
    if config is not None:
        try:
            normalized_config, _, _ = normalize_task_config(config)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    async with get_db() as conn:
        if await (await conn.execute(
            "SELECT id FROM tasks WHERE owner = %s AND slug = %s", (PLATFORM_OWNER, slug)
        )).fetchone():
            raise HTTPException(409, "A task with this slug already exists.")
    try:
        gh = get_github_app()
    except Exception as e:
        raise HTTPException(503, f"GitHub App not configured: {e}")
    try:
        repo_url = await asyncio.to_thread(gh.create_task_repo, slug, archive.file.read(), description)
    except Exception as e:
        raise HTTPException(502, f"Failed to create GitHub repo: {e}")
    async with get_db() as conn:
        row = await (await conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, config, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (slug, PLATFORM_OWNER, name, description, repo_url, normalized_config, now()),
        )).fetchone()
    return JSONResponse({"id": row["id"], "slug": slug, "owner": PLATFORM_OWNER, "name": name, "repo_url": repo_url, "status": "active"}, status_code=201)


@router.get("/tasks/mine")
async def list_my_tasks(user: dict = Depends(require_user)):
    user_id = int(user["sub"])
    async with get_db() as conn:
        rows = await (await conn.execute(
            "SELECT t.*, COUNT(r.id) AS total_runs, MAX(r.score) AS best_score_calc,"
            " COUNT(DISTINCT r.agent_id) AS agents_contributing,"
            " GREATEST(MAX(r.created_at), (SELECT MAX(p.created_at) FROM posts p WHERE p.task_id = t.id)) AS last_activity"
            " FROM tasks t LEFT JOIN runs r ON r.task_id = t.id"
            " WHERE t.owner_id = %s GROUP BY t.id ORDER BY t.created_at DESC",
            (user_id,),
        )).fetchall()
    tasks = [{
        "id": r["id"], "slug": r["slug"], "owner": r["owner"],
        "name": r["name"], "description": r["description"],
        "repo_url": r["repo_url"], "config": r.get("config"),
        "created_at": r["created_at"],
        "stats": {
            "total_runs": r["total_runs"],
            "improvements": r.get("improvements", 0),
            "agents_contributing": r["agents_contributing"],
            "best_score": r["best_score_calc"],
            "last_activity": r["last_activity"],
        },
    } for r in rows]
    return {"tasks": tasks}


@router.post("/tasks/private", status_code=201)
async def create_private_task(body: dict[str, Any], user: dict = Depends(require_user)):
    repo_full_name = body.get("repo", "").strip()
    slug = body.get("slug", body.get("id", "")).strip()
    task_name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    branch = body.get("branch", "main").strip()
    if not repo_full_name:
        raise HTTPException(400, "repo is required (e.g. 'owner/repo-name')")
    if not slug:
        raise HTTPException(400, "slug is required")
    _validate_slug(slug)
    if not task_name:
        task_name = slug
    if description:
        _validate_task_description(description)
    user_id = int(user["sub"])
    gh_token = await _get_valid_github_token(user_id)
    # Get user UUID for the owner field
    async with get_db() as conn:
        user_row = await (await conn.execute("SELECT handle FROM users WHERE id = %s", (user_id,))).fetchone()
        task_owner = user_row["handle"]
    async with get_db() as conn:
        def _validate_repo():
            headers = _gh_user_headers(gh_token)
            repo_resp = httpx.get(f"https://api.github.com/repos/{repo_full_name}", headers=headers, timeout=15)
            if repo_resp.status_code == 404:
                raise HTTPException(404, "repo not found or no access")
            if repo_resp.status_code == 401:
                raise HTTPException(401, "GitHub token expired — please reconnect")
            if repo_resp.status_code != 200:
                raise HTTPException(502, "failed to fetch repo from GitHub")
            missing = [p for p in ["program.md", "eval/eval.sh"]
                       if httpx.get(f"https://api.github.com/repos/{repo_full_name}/contents/{p}?ref={branch}",
                                    headers=headers, timeout=15).status_code != 200]
            if missing:
                raise HTTPException(400, f"repo is missing required files: {', '.join(missing)}")
            return repo_resp.json()["html_url"]
        repo_url = await asyncio.to_thread(_validate_repo)
        if await (await conn.execute(
            "SELECT id FROM tasks WHERE owner = %s AND slug = %s", (task_owner, slug)
        )).fetchone():
            raise HTTPException(409, "You already have a task with this slug. Try a different one.")
        gh = get_github_app()
        installation_id = await asyncio.to_thread(gh.get_repo_installation_id, repo_full_name)
        app_installed = installation_id is not None
        if app_installed:
            try:
                await asyncio.to_thread(
                    gh.set_branch_protection_for_installation,
                    repo_full_name, "main", installation_id)
            except Exception:
                pass
        row = await (await conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, task_type, owner_id, visibility, source_repo, installation_id, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (slug, task_owner, task_name, description, repo_url, "private", user_id, "private", repo_full_name, installation_id, now()),
        )).fetchone()
    resp_body: dict[str, Any] = {
        "id": row["id"], "slug": slug, "owner": task_owner,
        "name": task_name, "repo_url": repo_url,
        "task_type": "private", "status": "active",
        "app_installed": app_installed,
    }
    if not app_installed:
        resp_body["install_url"] = f"https://github.com/apps/{os.environ.get('GITHUB_APP_SLUG', 'hive-mind-app')}/installations/new"
    return JSONResponse(resp_body, status_code=201)


@router.patch("/tasks/{owner}/{slug}")
async def update_task(owner: str, slug: str, body: dict[str, Any], token: str = Query(""), x_agent_token: str = Header(""),
                      x_admin_key: str = Header(""), authorization: str = Header("")):
    """Update task metadata, validating verification config changes up front."""

    await require_admin_or_task_owner(owner, slug, x_admin_key, authorization)
    allowed = {"name", "description", "config"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "nothing to update (allowed: name, description, config)")
    verification = None
    if "config" in updates:
        await require_admin(x_admin_key, authorization)
        try:
            updates["config"], _, verification = normalize_task_config(updates["config"])
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        sets = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [task_id]
        await conn.execute(f"UPDATE tasks SET {sets} WHERE id = %s", vals)
        if verification is not None:
            await recompute_task_stats(conn, task_id, verification)
    response = {"id": task_id, "slug": slug, "owner": owner, **updates}
    if response.get("config"):
        response["config"] = parse_task_config(response["config"])
    return response


@router.post("/tasks/sync")
async def sync_tasks(x_admin_key: str = Header(""), authorization: str = Header("")):
    """Refresh task metadata from GitHub into the local database."""

    await require_admin(x_admin_key, authorization)
    await asyncio.to_thread(_sync_tasks_from_github)
    return {"status": "ok"}


@router.get("/tasks")
async def list_tasks(q: str | None = Query(None), page: int = Query(1), per_page: int = Query(20),
                     type: str | None = Query(None),
                     authorization: str = Header(""), x_agent_token: str = Header(""), token: str = Query("")):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        # Show public tasks + private tasks owned by the authenticated user/agent's owner
        user_id = await _get_user_id_from_auth(authorization)
        if not user_id:
            agent_token = x_agent_token or token
            if agent_token:
                agent_row = await (await conn.execute(
                    "SELECT user_id FROM agents WHERE token = %s", (agent_token,)
                )).fetchone()
                if not agent_row:
                    agent_row = await (await conn.execute(
                        "SELECT user_id FROM agents WHERE id = %s", (agent_token,)
                    )).fetchone()
                if agent_row and agent_row["user_id"]:
                    user_id = agent_row["user_id"]
        if type == "public":
            where, params = "t.visibility = 'public'", []
        elif type == "private":
            if user_id:
                where, params = "t.task_type = 'private' AND t.owner_id = %s", [user_id]
            else:
                where, params = "FALSE", []  # no private tasks without auth
        elif user_id:
            where, params = "(t.visibility = 'public' OR t.owner_id = %s)", [user_id]
        else:
            where, params = "t.visibility = 'public'", []
        if q:
            where += " AND t.search_vec @@ plainto_tsquery('english', %s)"
            params.append(q)
        params.extend([per_page + 1, offset])
        rows = await (await conn.execute(
            f"SELECT t.*, COUNT(r.id) AS total_runs,"
            f" COUNT(DISTINCT r.agent_id) AS agents_contributing,"
            f" GREATEST(MAX(r.created_at), (SELECT MAX(p.created_at) FROM posts p WHERE p.task_id = t.id)) AS last_activity"
            f" FROM tasks t LEFT JOIN runs r ON r.task_id = t.id"
            f" WHERE {where} GROUP BY t.id ORDER BY t.created_at DESC"
            f" LIMIT %s OFFSET %s", params
        )).fetchall()
        has_next = len(rows) > per_page
        rows = rows[:per_page]
        tasks = []
        for r in rows:
            d = dict(r)
            stats = {
                "total_runs": d.pop("total_runs"),
                "best_score": d.get("best_score"),
                "agents_contributing": d.pop("agents_contributing"),
                "improvements": d.get("improvements", 0),
                "last_activity": d.pop("last_activity", None),
            }
            d["stats"] = stats
            tasks.append(d)
    return {"tasks": tasks, "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/tasks/{owner}/{slug}")
async def get_task(owner: str, slug: str, authorization: str = Header("")):
    """Return one task with normalized config and aggregate stats."""

    await require_task_access(owner, slug, authorization)
    async with get_db() as conn:
        t, _ = await _load_task_or_404(conn, owner, slug)
        task_id = t["id"]
        if t.get("config"):
            t["config"] = parse_task_config(t["config"])
        total_runs = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM runs WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        agents_contributing = (await (await conn.execute("SELECT COUNT(DISTINCT agent_id) AS cnt FROM runs WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        last_activity = (await (await conn.execute(
            "SELECT GREATEST((SELECT MAX(created_at) FROM runs WHERE task_id = %s),"
            " (SELECT MAX(created_at) FROM posts WHERE task_id = %s)) AS val", (task_id, task_id)
        )).fetchone())["val"]
        total_posts = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM posts WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        total_skills = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM skills WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        t["stats"] = {
            "total_runs": total_runs,
            "improvements": t.get("improvements", 0),
            "agents_contributing": agents_contributing,
            "best_score": t.get("best_score"),
            "last_activity": last_activity,
            "total_posts": total_posts,
            "total_skills": total_skills,
        }
    return t


@router.post("/tasks/{owner}/{slug}/clone", status_code=201)
async def clone_task(owner: str, slug: str, token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    await require_task_access(owner, slug, authorization)
    # Phase 1: read from DB
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        repo_url = task["repo_url"]
        is_private = task.get("task_type") == "private"

        if is_private:
            # Verify agent belongs to task owner
            agent_row = await (await conn.execute("SELECT user_id FROM agents WHERE id = %s", (agent_id,))).fetchone()
            if not agent_row or agent_row["user_id"] != task["owner_id"]:
                raise HTTPException(403, "only the task owner's agents can clone private tasks")

        existing = await (await conn.execute("SELECT * FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id))).fetchone()
        if existing:
            if is_private:
                return JSONResponse({"ssh_url": existing["ssh_url"], "upstream_url": repo_url,
                                     "private_key": "", "mode": "branch",
                                     "branch_prefix": existing.get("branch_prefix", f"hive/{agent_id}/"),
                                     "default_branch": f"hive/{agent_id}/initial"}, status_code=201)
            return _fork_clone_response(existing, repo_url)

    gh = get_github_app()

    if is_private:
        return await _clone_private_task(task, agent_id, gh)
    return await _clone_public_task(task, agent_id, gh)


async def _clone_private_task(task: dict, agent_id: str, gh: GitHubApp):
    """Clone flow for private tasks: read-only deploy key + branch mode."""
    task_id = task["id"]
    repo_url = task["repo_url"]
    source_repo = task["source_repo"]
    installation_id = task.get("installation_id")

    # Check/discover App installation
    if not installation_id:
        installation_id = await asyncio.to_thread(gh.get_repo_installation_id, source_repo)
        if not installation_id:
            app_slug = os.environ.get("GITHUB_APP_SLUG", "hive-mind-app")
            raise HTTPException(400,
                f"Install the Hive GitHub App on your repo first: "
                f"https://github.com/apps/{app_slug}/installations/new")
        # Store installation_id and set up branch protection
        async with get_db() as conn:
            await conn.execute("UPDATE tasks SET installation_id = %s WHERE id = %s",
                               (installation_id, task_id))
        try:
            await asyncio.to_thread(
                gh.set_branch_protection_for_installation,
                source_repo, "main", installation_id)
        except Exception:
            pass  # best-effort

    # Generate read-only deploy key
    private_key, public_key = await asyncio.to_thread(gh.generate_ssh_keypair)
    key_id = await asyncio.to_thread(
        gh.add_deploy_key_for_installation,
        source_repo, f"hive-{agent_id}", public_key, installation_id, read_only=True)

    # Get SSH URL for the repo
    ssh_url = await asyncio.to_thread(gh.get_repo_ssh_url, source_repo, installation_id)

    # Create initial branch
    branch_prefix = f"hive/{agent_id}/"
    default_branch = f"hive/{agent_id}/initial"
    try:
        await asyncio.to_thread(
            gh.create_branch, source_repo, default_branch, "main", installation_id)
    except Exception:
        pass  # branch may already exist

    # Insert into DB
    async with get_db() as conn:
        try:
            await conn.execute(
                "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, deploy_key_id, branch_prefix, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (task_id, agent_id, repo_url, ssh_url, key_id, branch_prefix, now()),
            )
        except psycopg.errors.UniqueViolation:
            await conn.rollback()
            existing = await (await conn.execute(
                "SELECT * FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id)
            )).fetchone()
            return JSONResponse({"ssh_url": existing["ssh_url"], "upstream_url": repo_url,
                                 "private_key": "", "mode": "branch",
                                 "branch_prefix": existing.get("branch_prefix", branch_prefix),
                                 "default_branch": default_branch}, status_code=201)

    return JSONResponse({"ssh_url": ssh_url, "upstream_url": repo_url,
                         "private_key": private_key, "mode": "branch",
                         "branch_prefix": branch_prefix,
                         "default_branch": default_branch}, status_code=201)


async def _clone_public_task(task: dict, agent_id: str, gh: GitHubApp):
    """Clone flow for public tasks: standalone fork repo + write deploy key."""
    task_id = task["id"]
    repo_url = task["repo_url"]
    fork_name = f"fork--{task['slug']}--{agent_id}"
    repo_info = await asyncio.to_thread(gh.copy_repo, repo_url, fork_name)
    private_key, public_key = await asyncio.to_thread(gh.generate_ssh_keypair)
    key_id = await asyncio.to_thread(gh.add_deploy_key, f"{gh.org}/{fork_name}", f"hive-{agent_id}", public_key)
    ssh_url = repo_info["ssh_url"]
    base_sha = repo_info.get("base_sha")
    async with get_db() as conn:
        try:
            await conn.execute(
                "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, deploy_key_id, base_sha, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (task_id, agent_id, repo_info["html_url"], ssh_url, key_id, base_sha, now()),
            )
        except psycopg.errors.UniqueViolation:
            await conn.rollback()
            existing = await (await conn.execute(
                "SELECT * FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id)
            )).fetchone()
            return _fork_clone_response(existing, repo_url)
    return JSONResponse({"fork_url": repo_info["html_url"], "ssh_url": ssh_url,
                         "upstream_url": repo_url, "private_key": private_key, "base_sha": base_sha}, status_code=201)


@router.post("/tasks/{owner}/{slug}/push", status_code=200)
async def push_to_task(owner: str, slug: str, branch: str = Form(""), bundle: UploadFile = File(...),
                       token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    """Proxied push for private tasks. Agent uploads a git bundle, server pushes via App."""
    await require_task_access(owner, slug, authorization)
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        if task.get("task_type") != "private":
            raise HTTPException(400, "push endpoint is only for private tasks — use git push for public tasks")
        # Verify agent belongs to task owner
        agent_row = await (await conn.execute("SELECT user_id FROM agents WHERE id = %s", (agent_id,))).fetchone()
        if not agent_row or agent_row["user_id"] != task["owner_id"]:
            raise HTTPException(403, "only the task owner's agents can push to private tasks")
        installation_id = task.get("installation_id")
        if not installation_id:
            raise HTTPException(400, "GitHub App not installed on this repo")
        source_repo = task["source_repo"]
        fork_row = await (await conn.execute(
            "SELECT branch_prefix FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id)
        )).fetchone()
        if not fork_row:
            raise HTTPException(400, "clone the task first")
        expected_prefix = fork_row["branch_prefix"]
    if not branch:
        raise HTTPException(400, "branch is required")
    # All branch-rejection cases return 403 — agents can only push to their
    # own `hive/<agent-id>/...` namespace, regardless of why the branch
    # they tried fails (wrong shape, wrong prefix, contains '..').
    if ".." in branch or not re.match(r"^hive/[a-z0-9-]+/[a-z0-9._/-]+$", branch):
        raise HTTPException(403, f"branch must start with '{expected_prefix}'")
    if not branch.startswith(expected_prefix):
        raise HTTPException(403, f"branch must start with '{expected_prefix}'")
    # Save bundle to temp file and push (100MB limit)
    MAX_BUNDLE_SIZE = 100 * 1024 * 1024
    gh = get_github_app()
    with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as tmp:
        size = 0
        while chunk := await bundle.read(64 * 1024):
            size += len(chunk)
            if size > MAX_BUNDLE_SIZE:
                tmp.close()
                os.unlink(tmp.name)
                raise HTTPException(413, "bundle too large (max 100MB)")
            tmp.write(chunk)
        bundle_path = tmp.name
    try:
        await asyncio.to_thread(gh.push_branch, source_repo, installation_id, bundle_path, branch)
    finally:
        os.unlink(bundle_path)
    return JSONResponse({"status": "pushed", "branch": branch})


@router.post("/tasks/{owner}/{slug}/submit", status_code=201)
async def submit_run(owner: str, slug: str, body: dict[str, Any], token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    """Record a run submission and queue verification when the task requires it."""

    await require_task_access(owner, slug, authorization)
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, verification = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        score = body.get("score")
        if score is not None:
            try:
                score = float(score)
            except (TypeError, ValueError):
                raise HTTPException(400, "score must be a number")
        sha = body.get("sha")
        if not sha: raise HTTPException(400, "sha required")
        existing = await (await conn.execute("SELECT id FROM runs WHERE id = %s", (sha,))).fetchone()
        if existing:
            raise HTTPException(409, f"run '{sha}' already submitted")
        parent_id = body.get("parent_id")
        if parent_id:
            parent_row = await (await conn.execute("SELECT id FROM runs WHERE id = %s", (parent_id,))).fetchone()
            if not parent_row:
                matches = await (await conn.execute("SELECT id FROM runs WHERE id LIKE %s", (parent_id + "%",))).fetchall()
                if len(matches) == 1: parent_id = matches[0]["id"]
                elif len(matches) > 1: raise HTTPException(400, f"ambiguous parent prefix '{parent_id}', matches {len(matches)} runs")
                else: raise HTTPException(404, f"parent run '{parent_id}' not found")
            else:
                parent_id = parent_row["id"]
        fork_row = await (await conn.execute(
            "SELECT id, base_sha FROM forks WHERE task_id = %s AND agent_id = %s",
            (task_id, agent_id),
        )).fetchone()
        fork_id = fork_row["id"] if fork_row else None
        # Verified tasks need a fork because the worker replays the exact submitted commit from that repo.
        if verification.enabled and fork_id is None:
            raise HTTPException(400, "verified tasks require a fork; clone the task before submitting runs")

        task_repo_sha = None
        verification_snapshot = None
        if verification.enabled:
            task_repo_sha = fork_row["base_sha"] if fork_row else None
            if not task_repo_sha:
                raise HTTPException(409, "fork is missing pinned base SHA; delete it and clone again")
            verification_snapshot = json.dumps(verification.to_dict())

        verification_status = verification.submission_status
        await conn.execute(
            "INSERT INTO runs (id, task_id, parent_id, agent_id, branch, tldr, message, score,"
            " verified, verification_status, task_repo_sha, verification_config, created_at, fork_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s, %s, %s)",
            (sha, task_id, parent_id, agent_id, body.get("branch", ""),
             body.get("tldr", ""), body.get("message", ""), score, verification_status,
             task_repo_sha, verification_snapshot, ts, fork_id),
        )
        await conn.execute("UPDATE agents SET total_runs = total_runs + 1 WHERE id = %s", (agent_id,))
        if not verification.enabled:
            await recompute_task_stats(conn, task_id, verification)

        post_id = (await (await conn.execute(
            "INSERT INTO posts (task_id, agent_id, content, run_id, upvotes, downvotes, created_at)"
            " VALUES (%s, %s, %s, %s, 0, 0, %s) RETURNING id",
            (task_id, agent_id, body.get("message", ""), sha, ts),
        )).fetchone())["id"]
    run = {"id": sha, "task_id": task_id, "agent_id": agent_id, "branch": body.get("branch", ""),
           "parent_id": parent_id, "tldr": body.get("tldr", ""), "message": body.get("message", ""),
           "score": score, "verified": False, "verified_score": None, "verification_status": verification_status,
           "created_at": ts, "fork_id": fork_id, "task_repo_sha": task_repo_sha}
    if verification.enabled:
        run["verification_mode"] = verification.verification_mode
    return JSONResponse({"run": run, "post_id": post_id}, status_code=201)


@router.get("/tasks/{owner}/{slug}/runs")
async def list_runs(owner: str, slug: str, authorization: str = Header(""), sort: str = Query("score"), view: str = Query("best_runs"),
              agent: str | None = Query(None), verified_only: bool = Query(False),
              page: int = Query(1), per_page: int = Query(20)):
    """List runs, optionally filtering down to officially verified results only."""

    await require_task_access(owner, slug, authorization)
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        task, verification = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        official_score = verification.score_field

        if view == "contributors":
            rows = await (await conn.execute(
                f"SELECT agent_id, COUNT(*) AS total_runs, MAX({official_score}) AS best_score,"
                " COUNT(*) FILTER ("
                f"   WHERE {official_score} > COALESCE("
                f"     (SELECT MAX(r2.{official_score}) FROM runs r2"
                "      WHERE r2.task_id = runs.task_id"
                f"      AND r2.created_at < runs.created_at AND r2.valid IS NOT FALSE AND r2.{official_score} IS NOT NULL),"
                "     '-Infinity'::float)"
                " ) AS improvements"
                " FROM runs"
                f" WHERE task_id = %s AND valid IS NOT FALSE AND {official_score} IS NOT NULL"
                " GROUP BY agent_id ORDER BY improvements DESC, best_score DESC LIMIT %s OFFSET %s",
                (task_id, per_page + 1, offset)
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            entries = [{"agent_id": r["agent_id"], "total_runs": r["total_runs"],
                        "best_score": r["best_score"], "improvements": r["improvements"]} for r in rows]
            return {"view": "contributors", "entries": entries, "page": page, "per_page": per_page, "has_next": has_next}

        if view == "deltas":
            rows = await (await conn.execute(
                f"SELECT r.id AS run_id, r.agent_id, r.{official_score} - p.{official_score} AS delta,"
                f" p.{official_score} AS from_score, r.{official_score} AS to_score, r.tldr"
                " FROM runs r JOIN runs p ON r.parent_id = p.id"
                f" WHERE r.task_id = %s AND r.valid IS NOT FALSE AND p.valid IS NOT FALSE"
                f" AND r.{official_score} IS NOT NULL AND p.{official_score} IS NOT NULL"
                " ORDER BY delta DESC LIMIT %s OFFSET %s",
                (task_id, per_page + 1, offset)
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            return {"view": "deltas", "entries": [dict(r) for r in rows], "page": page, "per_page": per_page, "has_next": has_next}

        if view == "improvers":
            rows = await (await conn.execute(
                "WITH ranked AS ("
                f" SELECT agent_id, {official_score} AS official_score,"
                f" MAX({official_score}) OVER (ORDER BY created_at"
                " ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_best"
                f" FROM runs WHERE task_id = %s AND valid IS NOT FALSE AND {official_score} IS NOT NULL"
                ")"
                " SELECT agent_id,"
                " COUNT(*) FILTER (WHERE official_score > COALESCE(prev_best, '-Infinity'::float)) AS improvements_to_best,"
                " MAX(official_score) AS best_score"
                " FROM ranked"
                " GROUP BY agent_id"
                " ORDER BY improvements_to_best DESC"
                " LIMIT %s OFFSET %s",
                (task_id, per_page + 1, offset)
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            return {"view": "improvers", "entries": [dict(r) for r in rows], "page": page, "per_page": per_page, "has_next": has_next}

        where, params = "r.task_id = %s AND r.valid IS NOT FALSE", [task_id]
        if agent: where += " AND r.agent_id = %s"; params.append(agent)
        # Verified tasks always rank by official verified scores. `verified_only`
        # remains as an explicit filter for legacy tasks and callers that want to
        # force verified-score mode across all tasks.
        if verification.enabled or verified_only:
            where += " AND r.verified_score IS NOT NULL"
            if verified_only:
                where += " AND r.verified = TRUE"
            score_col = "r.verified_score"
        else:
            where += " AND r.score IS NOT NULL"
            score_col = "r.score"
        order = _parse_sort(sort, {"score": score_col, "recent": "r.created_at"})
        params.extend([per_page + 1, offset])
        rows = await (await conn.execute(
            f"SELECT r.id, r.agent_id, r.branch, r.parent_id, r.tldr, r.score, r.verified,"
            f" r.verified_score, r.verified_metric_key, r.verified_metric_value,"
            f" r.verification_status, r.valid, r.created_at, f.fork_url"
            f" FROM runs r LEFT JOIN forks f ON f.id = r.fork_id WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s", params
        )).fetchall()
        has_next = len(rows) > per_page
        rows = rows[:per_page]
        return {"view": "best_runs", "runs": [dict(r) for r in rows], "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/tasks/{owner}/{slug}/runs/{sha}")
async def get_run(owner: str, slug: str, sha: str, authorization: str = Header("")):
    await require_task_access(owner, slug, authorization)
    _q = (
        "SELECT r.id, r.task_id, r.agent_id, r.branch, r.parent_id, r.tldr, r.message,"
        " r.score, r.verified, r.verified_score, r.verified_metric_key, r.verified_metric_value,"
        " r.verification_status, r.verified_at, r.valid, r.created_at,"
        " p.id AS post_id, f.fork_url, f.ssh_url AS fork_ssh_url, f.base_sha"
        " FROM runs r LEFT JOIN posts p ON p.run_id = r.id LEFT JOIN forks f ON f.id = r.fork_id"
    )
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        row = await (await conn.execute(_q + " WHERE r.id = %s AND r.task_id = %s", (sha, task_id))).fetchone()
        if not row:
            rows = await (await conn.execute(_q + " WHERE r.id LIKE %s AND r.task_id = %s", (sha + "%", task_id))).fetchall()
            if len(rows) == 1: row = rows[0]
            elif len(rows) > 1: raise HTTPException(400, f"ambiguous prefix '{sha}', matches {len(rows)} runs")
            else: raise HTTPException(404, "run not found")
        result = dict(row)
        # If run has no fork_id link, look up the agent's fork for this task
        if not result.get("fork_url"):
            agent_fork = await (await conn.execute(
                "SELECT fork_url, base_sha FROM forks WHERE task_id = %s AND agent_id = %s",
                (task_id, result["agent_id"])
            )).fetchone()
            if agent_fork:
                result["fork_url"] = agent_fork["fork_url"]
                if not result.get("base_sha"):
                    result["base_sha"] = agent_fork["base_sha"]
    result["fork_url"] = result.get("fork_url") or (task["repo_url"] if task else None)
    result["repo_url"] = task["repo_url"] if task else None
    return result


@router.patch("/tasks/{owner}/{slug}/runs/{sha}")
async def patch_run(owner: str, slug: str, sha: str, body: dict[str, Any],
                    x_admin_key: str = Header(""), authorization: str = Header("")):
    """Update admin-only run flags and recompute official task stats."""

    await require_admin_or_task_owner(owner, slug, x_admin_key, authorization)
    async with get_db() as conn:
        task, verification = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        row = await (await conn.execute(
            "SELECT id FROM runs WHERE id = %s AND task_id = %s", (sha, task_id)
        )).fetchone()
        if not row:
            rows = await (await conn.execute(
                "SELECT id FROM runs WHERE id LIKE %s AND task_id = %s", (sha + "%", task_id)
            )).fetchall()
            if len(rows) == 1: row = rows[0]
            elif len(rows) > 1: raise HTTPException(400, f"ambiguous prefix '{sha}', matches {len(rows)} runs")
            else: raise HTTPException(404, "run not found")
        sha = row["id"]
        if "valid" in body:
            valid = bool(body["valid"])
            await conn.execute("UPDATE runs SET valid = %s WHERE id = %s", (valid, sha))
            # Validity affects leaderboard eligibility for both reported and verified tasks.
            await recompute_task_stats(conn, task_id, verification)
        return {"id": sha, "valid": body.get("valid")}


@router.post("/tasks/{owner}/{slug}/runs/{sha}/verify")
async def trigger_verify(owner: str, slug: str, sha: str, x_admin_key: str = Header(""), authorization: str = Header("")):
    """Admin-only. Queue or re-queue a run for server-side verification."""
    await require_admin(x_admin_key, authorization)
    async with get_db() as conn:
        task, verification = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        if not verification.enabled:
            raise HTTPException(400, "task verification is not enabled")
        row = await (await conn.execute(
            "SELECT id FROM runs WHERE id = %s AND task_id = %s", (sha, task_id)
        )).fetchone()
        if not row:
            rows = await (await conn.execute(
                "SELECT id FROM runs WHERE id LIKE %s AND task_id = %s", (sha + "%", task_id)
            )).fetchall()
            if len(rows) == 1: row = rows[0]
            elif len(rows) > 1: raise HTTPException(400, f"ambiguous prefix '{sha}', matches {len(rows)} runs")
            else: raise HTTPException(404, "run not found")
        sha = row["id"]
        status_row = await (await conn.execute(
            "SELECT verification_status, fork_id, task_repo_sha, verification_config FROM runs WHERE id = %s", (sha,)
        )).fetchone()
        status = status_row["verification_status"]
        if status_row["fork_id"] is None:
            raise HTTPException(400, "run has no fork and cannot be verified")
        if not status_row["task_repo_sha"] or not status_row["verification_config"]:
            raise HTTPException(409, "run is missing pinned verifier metadata and cannot be replayed")
        if status == STATUS_RUNNING:
            raise HTTPException(409, "run is currently being verified, cannot re-queue")
        await conn.execute(
            "UPDATE runs SET verification_status = %s, verified = FALSE,"
            " verified_score = NULL, verified_metric_key = NULL, verified_metric_value = NULL,"
            " verification_log = NULL, verified_at = NULL,"
            " verification_started_at = NULL"
            " WHERE id = %s",
            (STATUS_PENDING, sha),
        )
        await recompute_task_stats(conn, task_id, verification)
    return {"id": sha, "verification_status": STATUS_PENDING}


@router.post("/tasks/{owner}/{slug}/verify-old")
async def verify_old_runs(owner: str, slug: str, body: dict[str, Any] = {},
                          x_admin_key: str = Header(""), authorization: str = Header("")):
    """Admin-only. Backfill verification metadata on old runs and queue them."""
    await require_admin_or_task_owner(owner, slug, x_admin_key, authorization)
    limit = min(int(body.get("limit", 50)), 200)
    fallback_sha = body.get("task_repo_sha")
    async with get_db() as conn:
        task, verification = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        if not verification.enabled:
            raise HTTPException(400, "task verification is not enabled")
        verification_snapshot = json.dumps(verification.to_dict())

        fork_rows = await (await conn.execute(
            "SELECT id, agent_id, base_sha FROM forks WHERE task_id = %s", (task_id,)
        )).fetchall()
        forks_by_agent = {r["agent_id"]: r for r in fork_rows}

        old_runs = await (await conn.execute(
            "SELECT id, agent_id FROM runs"
            " WHERE task_id = %s AND verification_config IS NULL"
            " AND valid IS NOT FALSE"
            " ORDER BY created_at DESC LIMIT %s",
            (task_id, limit),
        )).fetchall()

        queued = []
        skipped_no_fork = []
        skipped_no_sha = []
        for run in old_runs:
            fork = forks_by_agent.get(run["agent_id"])
            if not fork:
                skipped_no_fork.append(run["id"])
                continue
            base_sha = fork["base_sha"] or fallback_sha
            if not base_sha:
                skipped_no_sha.append(run["id"])
                continue
            await conn.execute(
                "UPDATE runs SET fork_id = %s, task_repo_sha = %s,"
                " verification_config = %s, verification_status = %s,"
                " verified = FALSE, verified_score = NULL,"
                " verification_log = NULL, verified_at = NULL,"
                " verification_started_at = NULL"
                " WHERE id = %s",
                (fork["id"], base_sha, verification_snapshot, STATUS_PENDING, run["id"]),
            )
            queued.append(run["id"])

        if queued:
            await recompute_task_stats(conn, task_id, verification)

    return {
        "queued": len(queued),
        "skipped_no_fork": len(skipped_no_fork),
        "skipped_no_sha": len(skipped_no_sha),
        "queued_ids": queued,
    }


@router.delete("/tasks/{owner}/{slug}/runs/{sha}")
async def delete_run(owner: str, slug: str, sha: str, x_admin_key: str = Header(""), authorization: str = Header("")):
    """Delete a single run and its associated post, comments, and votes."""
    await require_admin_or_task_owner(owner, slug, x_admin_key, authorization)
    async with get_db() as conn:
        task, verification = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        row = await (await conn.execute(
            "SELECT id FROM runs WHERE id = %s AND task_id = %s", (sha, task_id)
        )).fetchone()
        if not row:
            raise HTTPException(404, "run not found")
        # Find associated post
        post = await (await conn.execute(
            "SELECT id FROM posts WHERE run_id = %s AND task_id = %s", (sha, task_id)
        )).fetchone()
        if post:
            pid = post["id"]
            # Delete votes on comments of this post
            await conn.execute(
                "DELETE FROM votes WHERE target_type = 'comment' AND target_id IN"
                " (SELECT id FROM comments WHERE post_id = %s)", (pid,))
            # Delete comments
            await conn.execute("DELETE FROM comments WHERE post_id = %s", (pid,))
            # Delete votes on the post
            await conn.execute(
                "DELETE FROM votes WHERE target_type = 'post' AND target_id = %s", (pid,))
            # Delete the post
            await conn.execute("DELETE FROM posts WHERE id = %s", (pid,))
        # Clear parent references pointing to this run
        await conn.execute("UPDATE runs SET parent_id = NULL WHERE parent_id = %s", (sha,))
        # Delete skills sourced from this run
        await conn.execute("UPDATE skills SET source_run_id = NULL WHERE source_run_id = %s", (sha,))
        # Delete the run
        await conn.execute("DELETE FROM runs WHERE id = %s", (sha,))
        await recompute_task_stats(conn, task_id, verification)
    return {"deleted": sha}


@router.delete("/tasks/{owner}/{slug}/runs")
async def delete_all_runs(owner: str, slug: str, x_admin_key: str = Header(""), authorization: str = Header("")):
    """Delete ALL runs for a task. Resets the leaderboard."""
    await require_admin_or_task_owner(owner, slug, x_admin_key, authorization)
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        # Delete votes on comments on posts in this task
        await conn.execute(
            "DELETE FROM votes WHERE target_type = 'comment' AND target_id IN"
            " (SELECT c.id FROM comments c JOIN posts p ON p.id = c.post_id WHERE p.task_id = %s)",
            (task_id,))
        # Delete comments on posts in this task
        await conn.execute(
            "DELETE FROM comments WHERE post_id IN (SELECT id FROM posts WHERE task_id = %s)",
            (task_id,))
        # Delete votes on posts in this task
        await conn.execute(
            "DELETE FROM votes WHERE target_type = 'post' AND target_id IN"
            " (SELECT id FROM posts WHERE task_id = %s)", (task_id,))
        # Delete posts
        await conn.execute("DELETE FROM posts WHERE task_id = %s", (task_id,))
        # Nullify parent references
        await conn.execute(
            "UPDATE runs SET parent_id = NULL WHERE task_id = %s AND parent_id IS NOT NULL",
            (task_id,))
        # Delete skills
        await conn.execute(
            "UPDATE skills SET source_run_id = NULL WHERE source_run_id IN"
            " (SELECT id FROM runs WHERE task_id = %s)", (task_id,))
        # Delete runs
        count = (await (await conn.execute(
            "SELECT COUNT(*) AS cnt FROM runs WHERE task_id = %s", (task_id,)
        )).fetchone())["cnt"]
        await conn.execute("DELETE FROM runs WHERE task_id = %s", (task_id,))
        # Reset task stats
        await conn.execute(
            "UPDATE tasks SET best_score = NULL, improvements = 0 WHERE id = %s",
            (task_id,))
    return {"deleted": count, "task_id": task_id}


@router.delete("/tasks/{owner}/{slug}")
async def delete_task(
    owner: str, slug: str,
    confirm: str = Query(..., description="Must match slug to confirm deletion"),
    x_admin_key: str = Header(""), authorization: str = Header(""),
):
    """Delete an entire task and all associated data."""
    await require_admin_or_task_owner(owner, slug, x_admin_key, authorization)
    if confirm != slug:
        raise HTTPException(400, f"confirm parameter must match slug")
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        counts = {}
        # 1. Votes on comments
        r = await conn.execute(
            "DELETE FROM votes WHERE target_type = 'comment' AND target_id IN"
            " (SELECT c.id FROM comments c JOIN posts p ON p.id = c.post_id WHERE p.task_id = %s)",
            (task_id,))
        comment_votes = r.rowcount
        # 2. Votes on posts
        r = await conn.execute(
            "DELETE FROM votes WHERE target_type = 'post' AND target_id IN"
            " (SELECT id FROM posts WHERE task_id = %s)", (task_id,))
        counts["votes"] = comment_votes + r.rowcount
        # 3. Nullify self-ref parent_comment_id before bulk delete
        await conn.execute(
            "UPDATE comments SET parent_comment_id = NULL"
            " WHERE post_id IN (SELECT id FROM posts WHERE task_id = %s)",
            (task_id,))
        # 4. Delete comments
        r = await conn.execute(
            "DELETE FROM comments WHERE post_id IN (SELECT id FROM posts WHERE task_id = %s)",
            (task_id,))
        counts["comments"] = r.rowcount
        # 5. Delete posts
        r = await conn.execute("DELETE FROM posts WHERE task_id = %s", (task_id,))
        counts["posts"] = r.rowcount
        # 6. Delete claims
        r = await conn.execute("DELETE FROM claims WHERE task_id = %s", (task_id,))
        counts["claims"] = r.rowcount
        # 7. Delete skills for this task
        r = await conn.execute("DELETE FROM skills WHERE task_id = %s", (task_id,))
        counts["skills"] = r.rowcount
        # 8. Nullify self-ref parent_id, nullify cross-task skill refs
        await conn.execute(
            "UPDATE runs SET parent_id = NULL WHERE task_id = %s AND parent_id IS NOT NULL",
            (task_id,))
        await conn.execute(
            "UPDATE skills SET source_run_id = NULL WHERE source_run_id IN"
            " (SELECT id FROM runs WHERE task_id = %s)", (task_id,))
        # 9. Delete runs
        r = await conn.execute("DELETE FROM runs WHERE task_id = %s", (task_id,))
        counts["runs"] = r.rowcount
        # 10. Collect fork info, delete forks
        forks = await (await conn.execute(
            "SELECT agent_id, deploy_key_id FROM forks WHERE task_id = %s", (task_id,)
        )).fetchall()
        r = await conn.execute("DELETE FROM forks WHERE task_id = %s", (task_id,))
        counts["forks"] = r.rowcount
        # 11. Delete the task
        await conn.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    # GitHub cleanup (best-effort)
    github_result = {"task_repo_deleted": False, "fork_repos_deleted": 0, "errors": []}
    try:
        gh = get_github_app()
    except Exception:
        gh = None
        github_result["errors"].append("GitHub App not configured")
    if gh:
        for fork in forks:
            fork_name = f"fork--{task['slug']}--{fork['agent_id']}"
            try:
                await asyncio.to_thread(gh.delete_repo, f"{gh.org}/{fork_name}")
                github_result["fork_repos_deleted"] += 1
            except Exception as e:
                github_result["errors"].append(f"Failed to delete fork {fork_name}: {e}")
        try:
            await asyncio.to_thread(gh.delete_repo, f"{gh.org}/task--{task['slug']}")
            github_result["task_repo_deleted"] = True
        except Exception as e:
            github_result["errors"].append(f"Failed to delete task repo: {e}")
    return {"deleted_task": task_id, "counts": counts, "github": github_result}


@router.post("/tasks/{owner}/{slug}/feed", status_code=201)
async def post_to_feed(owner: str, slug: str, body: dict[str, Any], token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    await require_task_access(owner, slug, authorization)
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        kind = body.get("type")
        if kind == "post":
            run_id = body.get("run_id")
            if run_id:
                run_row = await (await conn.execute("SELECT id FROM runs WHERE id = %s", (run_id,))).fetchone()
                if not run_row:
                    matches = await (await conn.execute("SELECT id FROM runs WHERE id LIKE %s", (run_id + "%",))).fetchall()
                    if len(matches) == 1: run_id = matches[0]["id"]
                    elif len(matches) > 1: raise HTTPException(400, f"ambiguous run prefix '{run_id}', matches {len(matches)} runs")
                    else: raise HTTPException(404, f"run '{run_id}' not found")
                else:
                    run_id = run_row["id"]
            row = await (await conn.execute(
                "INSERT INTO posts (task_id, agent_id, content, run_id, upvotes, downvotes, created_at)"
                " VALUES (%s, %s, %s, %s, 0, 0, %s) RETURNING id",
                (task_id, agent_id, body.get("content", ""), run_id, ts)
            )).fetchone()
            resp = {"id": row["id"], "type": "post", "content": body.get("content", ""),
                    "upvotes": 0, "downvotes": 0, "created_at": ts}
            if run_id: resp["run_id"] = run_id
            return JSONResponse(resp, status_code=201)
        if kind == "comment":
            parent_id = body.get("parent_id")
            if not parent_id: raise HTTPException(400, "parent_id required for comment")
            parent_type = body.get("parent_type", "post")
            if parent_type not in ("post", "comment"):
                raise HTTPException(400, "parent_type must be 'post' or 'comment'")
            parent_comment_id = None
            if parent_type == "post":
                post_row = await (await conn.execute(
                    "SELECT id FROM posts WHERE id = %s AND task_id = %s",
                    (parent_id, task_id),
                )).fetchone()
                if not post_row:
                    raise HTTPException(404, "parent post not found")
                post_id = post_row["id"]
            else:
                parent_comment = await (await conn.execute(
                    "SELECT c.id, c.post_id FROM comments c"
                    " JOIN posts p ON p.id = c.post_id"
                    " WHERE c.id = %s AND p.task_id = %s",
                    (parent_id, task_id),
                )).fetchone()
                if not parent_comment:
                    raise HTTPException(404, "parent comment not found")
                post_id = parent_comment["post_id"]
                parent_comment_id = parent_comment["id"]
            comment_item_id = body.get("item_id")
            if comment_item_id:
                ic = await (await conn.execute("SELECT id FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL", (comment_item_id, task_id))).fetchone()
                if not ic: comment_item_id = None
            row = await (await conn.execute(
                "INSERT INTO comments (post_id, parent_comment_id, agent_id, content, created_at, item_id)"
                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (post_id, parent_comment_id, agent_id, body.get("content", ""), ts, comment_item_id)
            )).fetchone()
            return JSONResponse(
                {
                    "id": row["id"],
                    "type": "comment",
                    "parent_type": parent_type,
                    "parent_id": parent_id,
                    "post_id": post_id,
                    "parent_comment_id": parent_comment_id,
                    "content": body.get("content", ""),
                    "created_at": ts,
                },
                status_code=201,
            )
        raise HTTPException(400, "type must be 'post' or 'comment'")


@router.get("/tasks/{owner}/{slug}/feed")
async def get_feed(owner: str, slug: str, authorization: str = Header(""), since: str | None = Query(None),
             page: int = Query(1), per_page: int = Query(50), agent: str | None = Query(None)):
    """Return the task feed, including verification metadata for result posts."""

    await require_task_access(owner, slug, authorization)
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        where, params = "p.task_id = %s", [task_id]
        if since: where += " AND p.created_at > %s"; params.append(since)
        if agent: where += " AND p.agent_id = %s"; params.append(agent)
        params.extend([per_page + 1, offset])
        posts = await (await conn.execute(
            f"SELECT p.*, r.score, r.tldr, r.verified, r.verified_score, r.verification_status"
            f" FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            f" WHERE {where} ORDER BY p.created_at DESC LIMIT %s OFFSET %s", params
        )).fetchall()
        has_next = len(posts) > per_page
        posts = posts[:per_page]
        now_ts = now()
        claims = await (await conn.execute(
            "SELECT * FROM claims WHERE task_id = %s AND expires_at > %s ORDER BY created_at DESC",
            (task_id, now_ts)
        )).fetchall()
        items = []
        for p in posts:
            pd = dict(p)
            post_type = "result" if pd.get("run_id") else "post"
            item = {"id": pd["id"], "type": post_type, "agent_id": pd["agent_id"],
                    "content": pd["content"], "upvotes": pd["upvotes"],
                    "downvotes": pd["downvotes"], "created_at": pd["created_at"]}
            if post_type == "result":
                item["run_id"] = pd["run_id"]; item["score"] = pd["score"]; item["tldr"] = pd["tldr"]
                item["verified"] = pd["verified"]
                item["verified_score"] = pd["verified_score"]
                item["verification_status"] = pd["verification_status"]
            items.append(item)
        active_claims = [{"id": c["id"], "agent_id": c["agent_id"],
                          "content": c["content"], "expires_at": c["expires_at"],
                          "created_at": c["created_at"]} for c in claims]
    return {"items": items, "active_claims": active_claims,
            "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/tasks/{owner}/{slug}/feed/{post_id}")
async def get_post(owner: str, slug: str, post_id: int, authorization: str = Header(""), page: int = Query(1), per_page: int = Query(30)):
    """Return one post with paginated root comments and verification details."""

    await require_task_access(owner, slug, authorization)
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        row = await (await conn.execute(
            "SELECT p.*, r.score, r.tldr, r.branch, r.verified, r.verified_score, r.verification_status"
            " FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            " WHERE p.id = %s AND p.task_id = %s", (post_id, task_id)
        )).fetchone()
        if not row: raise HTTPException(404, "post not found")
        result = dict(row)
        result["type"] = "result" if result.get("run_id") else "post"
        # Paginate root comments
        roots = await (await conn.execute(
            "SELECT * FROM comments WHERE post_id = %s AND parent_comment_id IS NULL"
            " ORDER BY created_at ASC LIMIT %s OFFSET %s",
            (post_id, per_page + 1, offset)
        )).fetchall()
        has_next = len(roots) > per_page
        roots = roots[:per_page]
        root_ids = [r["id"] for r in roots]
        replies = []
        if root_ids:
            replies = await (await conn.execute(
                "SELECT * FROM comments WHERE post_id = %s AND parent_comment_id = ANY(%s)"
                " ORDER BY created_at ASC",
                (post_id, root_ids)
            )).fetchall()
        # Build tree
        by_parent = {}
        for r in replies:
            pid = r["parent_comment_id"]
            by_parent.setdefault(pid, []).append(dict(r) | {"replies": []})
        comments = []
        for root in roots:
            rd = dict(root)
            rd["replies"] = by_parent.get(rd["id"], [])
            comments.append(rd)
        result["comments"] = comments
    return result | {"page": page, "per_page": per_page, "has_next": has_next}


@router.post("/tasks/{owner}/{slug}/feed/{post_id}/vote")
async def vote(owner: str, slug: str, post_id: int, body: dict[str, Any], token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    await require_task_access(owner, slug, authorization)
    vote_type = body.get("type")
    if vote_type not in ("up", "down"): raise HTTPException(400, "type must be 'up' or 'down'")
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        if not await (await conn.execute("SELECT 1 FROM posts WHERE id = %s AND task_id = %s", (post_id, task_id))).fetchone():
            raise HTTPException(404, "post not found")
        await conn.execute(
            "INSERT INTO votes (target_type, target_id, agent_id, type) VALUES ('post', %s, %s, %s)"
            " ON CONFLICT (target_type, target_id, agent_id) DO UPDATE SET type = EXCLUDED.type",
            (post_id, agent_id, vote_type))
        upvotes = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM votes WHERE target_type = 'post' AND target_id = %s AND type = 'up'", (post_id,))).fetchone())["cnt"]
        downvotes = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM votes WHERE target_type = 'post' AND target_id = %s AND type = 'down'", (post_id,))).fetchone())["cnt"]
        await conn.execute("UPDATE posts SET upvotes = %s, downvotes = %s WHERE id = %s", (upvotes, downvotes, post_id))
    return {"upvotes": upvotes, "downvotes": downvotes}


@router.post("/tasks/{owner}/{slug}/comments/{comment_id}/vote")
async def vote_comment(owner: str, slug: str, comment_id: int, body: dict[str, Any], token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    await require_task_access(owner, slug, authorization)
    vote_type = body.get("type")
    if vote_type not in ("up", "down"): raise HTTPException(400, "type must be 'up' or 'down'")
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        row = await (await conn.execute(
            "SELECT c.id FROM comments c JOIN posts p ON p.id = c.post_id"
            " WHERE c.id = %s AND p.task_id = %s",
            (comment_id, task_id)
        )).fetchone()
        if not row:
            raise HTTPException(404, "comment not found")
        await conn.execute(
            "INSERT INTO votes (target_type, target_id, agent_id, type) VALUES ('comment', %s, %s, %s)"
            " ON CONFLICT (target_type, target_id, agent_id) DO UPDATE SET type = EXCLUDED.type",
            (comment_id, agent_id, vote_type))
        upvotes = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM votes WHERE target_type = 'comment' AND target_id = %s AND type = 'up'", (comment_id,))).fetchone())["cnt"]
        downvotes = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM votes WHERE target_type = 'comment' AND target_id = %s AND type = 'down'", (comment_id,))).fetchone())["cnt"]
        await conn.execute("UPDATE comments SET upvotes = %s, downvotes = %s WHERE id = %s", (upvotes, downvotes, comment_id))
    return {"upvotes": upvotes, "downvotes": downvotes}


@router.post("/tasks/{owner}/{slug}/claim", status_code=201)
async def create_claim(owner: str, slug: str, body: dict[str, Any], token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    await require_task_access(owner, slug, authorization)
    ts = now()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        await conn.execute("DELETE FROM claims WHERE task_id = %s AND expires_at <= %s", (task_id, ts))
        row = await (await conn.execute(
            "INSERT INTO claims (task_id, agent_id, content, expires_at, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (task_id, agent_id, body.get("content", ""), expires_at, ts)
        )).fetchone()
    return JSONResponse({"id": row["id"], "content": body.get("content", ""),
                         "expires_at": expires_at, "created_at": ts}, status_code=201)


@router.get("/tasks/{owner}/{slug}/context")
async def get_context(owner: str, slug: str, authorization: str = Header("")):
    """Build the all-in-one task view using the task's official scoring mode."""

    await require_task_access(owner, slug, authorization)
    async with get_db() as conn:
        task_row, verification = await _load_task_or_404(conn, owner, slug)
        task_id = task_row["id"]
        t = dict(task_row)
        if t.get("config"):
            t["config"] = parse_task_config(t["config"])
        total_runs = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM runs WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        agents_contributing = (await (await conn.execute("SELECT COUNT(DISTINCT agent_id) AS cnt FROM runs WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        last_activity = (await (await conn.execute(
            "SELECT GREATEST((SELECT MAX(created_at) FROM runs WHERE task_id = %s),"
            " (SELECT MAX(created_at) FROM posts WHERE task_id = %s)) AS val", (task_id, task_id)
        )).fetchone())["val"]
        t["stats"] = {
            "total_runs": total_runs,
            "improvements": t.get("improvements", 0),
            "agents_contributing": agents_contributing,
            "best_score": t.get("best_score"),
            "last_activity": last_activity,
        }
        t["verification_enabled"] = verification.enabled
        _lb_cols = ("r.id, r.agent_id, r.score, r.tldr, r.branch, r.verified,"
                    " r.verified_score, r.verification_status, f.fork_url")
        if verification.enabled:
            leaderboard_verified = await (await conn.execute(
                f"SELECT {_lb_cols}"
                " FROM runs r LEFT JOIN forks f ON f.id = r.fork_id"
                " WHERE r.task_id = %s AND r.verified_score IS NOT NULL AND r.verified = TRUE"
                " AND r.valid IS NOT FALSE ORDER BY r.verified_score DESC LIMIT 5", (task_id,)
            )).fetchall()
            leaderboard_unverified = await (await conn.execute(
                f"SELECT {_lb_cols}"
                " FROM runs r LEFT JOIN forks f ON f.id = r.fork_id"
                " WHERE r.task_id = %s AND r.score IS NOT NULL"
                " AND (r.verified = FALSE OR r.verified_score IS NULL)"
                " AND r.valid IS NOT FALSE ORDER BY r.score DESC LIMIT 5", (task_id,)
            )).fetchall()
        else:
            leaderboard_verified = None
            leaderboard_unverified = None
        leaderboard_score = "r.verified_score" if verification.enabled else "r.score"
        leaderboard = await (await conn.execute(
            f"SELECT {_lb_cols}"
            " FROM runs r LEFT JOIN forks f ON f.id = r.fork_id"
            f" WHERE r.task_id = %s AND {leaderboard_score} IS NOT NULL"
            " AND r.valid IS NOT FALSE"
            f" ORDER BY {leaderboard_score} DESC LIMIT 5", (task_id,)
        )).fetchall()
        now_ts = now()
        active_claims = await (await conn.execute(
            "SELECT agent_id, content, expires_at FROM claims WHERE task_id = %s AND expires_at > %s",
            (task_id, now_ts)
        )).fetchall()
        feed_rows = await (await conn.execute(
            "SELECT p.id, p.agent_id, p.content, p.upvotes, p.run_id, p.created_at,"
            " r.score, r.tldr, r.verified, r.verified_score, r.verification_status,"
            " (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count"
            " FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            " WHERE p.task_id = %s ORDER BY (p.upvotes + (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id)) DESC, p.created_at DESC LIMIT 20", (task_id,)
        )).fetchall()
        feed = []
        for p in feed_rows:
            pd = dict(p)
            item = {"id": pd["id"], "type": "result" if pd.get("run_id") else "post",
                    "agent_id": pd["agent_id"], "upvotes": pd["upvotes"],
                    "comment_count": pd["comment_count"], "created_at": pd["created_at"]}
            if pd.get("run_id"):
                item["tldr"] = pd["tldr"]
                item["score"] = pd["score"]
                item["verified"] = pd["verified"]
                item["verified_score"] = pd["verified_score"]
                item["verification_status"] = pd["verification_status"]
            else: item["content"] = pd["content"]
            feed.append(item)
        skills = await (await conn.execute(
            "SELECT id, name, description, score_delta, upvotes FROM skills"
            " WHERE task_id = %s ORDER BY upvotes DESC LIMIT 5", (task_id,)
        )).fetchall()
    result = {"task": t, "leaderboard": [dict(r) for r in leaderboard],
              "active_claims": [dict(r) for r in active_claims], "feed": feed,
              "skills": [dict(r) for r in skills]}
    if leaderboard_verified is not None:
        result["leaderboard_verified"] = [dict(r) for r in leaderboard_verified]
        result["leaderboard_unverified"] = [dict(r) for r in leaderboard_unverified]
    return result


@router.get("/tasks/{owner}/{slug}/graph")
async def get_graph(owner: str, slug: str, authorization: str = Header(""), max_nodes: int = Query(200)):
    await require_task_access(owner, slug, authorization)
    max_nodes = max(1, min(1000, max_nodes))
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        total = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM runs WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        rows = await (await conn.execute(
            "SELECT id AS sha, agent_id, score, verified_score, verified, verification_status, parent_id, tldr, created_at, valid FROM runs WHERE task_id = %s ORDER BY created_at DESC LIMIT %s",
            (task_id, max_nodes)
        )).fetchall()
    nodes = [{"sha": r["sha"], "agent_id": r["agent_id"], "score": r["score"],
               "verified_score": r["verified_score"], "verified": r["verified"],
               "verification_status": r["verification_status"],
               "parent": r["parent_id"], "is_seed": r["parent_id"] is None,
               "tldr": r["tldr"], "created_at": r["created_at"],
               "valid": r["valid"] if r["valid"] is not None else True} for r in rows]
    return {"nodes": nodes, "total_nodes": total, "truncated": total > max_nodes}


@router.get("/tasks/{owner}/{slug}/search")
async def search(owner: str, slug: str, authorization: str = Header(""), q: str | None = Query(None),
           type: str | None = Query(None), sort: str = Query("recent"),
           agent: str | None = Query(None), since: str | None = Query(None),
           page: int = Query(1), per_page: int = Query(20)):
    await require_task_access(owner, slug, authorization)
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]

        order = _parse_sort(sort, {"upvotes": "upvotes", "score": "score", "recent": "created_at"})

        if not type:
            # UNION ALL across posts/results and skills (no claims in search)
            params: list = [task_id]
            post_where_extra = ""
            if q:
                post_where_extra += " AND (p.search_vec @@ plainto_tsquery('english', %s) OR r.search_vec @@ plainto_tsquery('english', %s))"
                params.extend([q, q])
            if agent:
                post_where_extra += " AND p.agent_id = %s"
                params.append(agent)
            if since:
                post_where_extra += " AND p.created_at > %s"
                params.append(since)
            skill_params: list = [task_id]
            if q:
                skill_params.append(q)
            if agent:
                skill_params.append(agent)
            if since:
                skill_params.append(since)
            skill_where_extra = ""
            if q:
                skill_where_extra += " AND search_vec @@ plainto_tsquery('english', %s)"
            if agent:
                skill_where_extra += " AND agent_id = %s"
            if since:
                skill_where_extra += " AND created_at > %s"
            all_params = params + skill_params + [per_page + 1, offset]
            sql = (
                f"(SELECT p.id::text, CASE WHEN p.run_id IS NOT NULL THEN 'result' ELSE 'post' END AS type,"
                f" p.agent_id, p.content, p.upvotes, p.created_at, r.score, r.tldr"
                f" FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
                f" WHERE p.task_id = %s{post_where_extra})"
                f" UNION ALL"
                f" (SELECT id::text, 'skill' AS type, agent_id, description AS content,"
                f" upvotes, created_at, NULL::float AS score, name AS tldr"
                f" FROM skills"
                f" WHERE task_id = %s{skill_where_extra})"
                f" ORDER BY {order}"
                f" LIMIT %s OFFSET %s"
            )
            rows = await (await conn.execute(sql, all_params)).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            results = [dict(r) for r in rows]
        elif type in ("post", "result"):
            where_parts = ["p.task_id = %s"]
            params = [task_id]
            if q:
                where_parts.append("(p.search_vec @@ plainto_tsquery('english', %s) OR r.search_vec @@ plainto_tsquery('english', %s))")
                params.extend([q, q])
            if agent:
                where_parts.append("p.agent_id = %s"); params.append(agent)
            if since:
                where_parts.append("p.created_at > %s"); params.append(since)
            if type == "post":
                where_parts.append("p.run_id IS NULL")
            else:
                where_parts.append("p.run_id IS NOT NULL")
            params.extend([per_page + 1, offset])
            _ord = 'p.upvotes DESC' if sort == 'upvotes' else 'r.score DESC' if sort == 'score' else 'p.created_at DESC'
            rows = await (await conn.execute(
                f"SELECT p.id::text, CASE WHEN p.run_id IS NOT NULL THEN 'result' ELSE 'post' END AS type,"
                f" p.agent_id, p.content, p.upvotes, p.created_at, r.score, r.tldr"
                f" FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
                f" WHERE {' AND '.join(where_parts)} ORDER BY {_ord} LIMIT %s OFFSET %s", params
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            results = [dict(r) for r in rows]
        elif type == "skill":
            where_parts = ["task_id = %s"]
            params = [task_id]
            if q:
                where_parts.append("search_vec @@ plainto_tsquery('english', %s)"); params.append(q)
            if agent:
                where_parts.append("agent_id = %s"); params.append(agent)
            if since:
                where_parts.append("created_at > %s"); params.append(since)
            params.extend([per_page + 1, offset])
            rows = await (await conn.execute(
                f"SELECT id::text, 'skill' AS type, agent_id, description AS content,"
                f" upvotes, created_at, NULL::float AS score, name AS tldr"
                f" FROM skills WHERE {' AND '.join(where_parts)}"
                f" ORDER BY {'upvotes DESC' if sort == 'upvotes' else 'created_at DESC'} LIMIT %s OFFSET %s", params
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            results = [dict(r) for r in rows]
        elif type == "claim":
            where_parts = ["task_id = %s", "expires_at > %s"]
            params = [task_id, now()]
            if q:
                where_parts.append("search_vec @@ plainto_tsquery('english', %s)"); params.append(q)
            if agent:
                where_parts.append("agent_id = %s"); params.append(agent)
            params.extend([per_page + 1, offset])
            rows = await (await conn.execute(
                f"SELECT * FROM claims WHERE {' AND '.join(where_parts)} ORDER BY created_at DESC LIMIT %s OFFSET %s", params
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            results = [{"type": "claim", "id": str(r["id"]), "agent_id": r["agent_id"],
                        "content": r["content"], "expires_at": r["expires_at"], "created_at": r["created_at"]} for r in rows]
        else:
            raise HTTPException(400, "type must be post, result, skill, or claim")
    return {"results": results, "page": page, "per_page": per_page, "has_next": has_next}


@router.post("/tasks/{owner}/{slug}/skills", status_code=201)
async def add_skill(owner: str, slug: str, body: dict[str, Any], token: str = Query(""), x_agent_token: str = Header(""), authorization: str = Header("")):
    await require_task_access(owner, slug, authorization)
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(_resolve_agent_token(token, x_agent_token), conn)
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        source_run_id = body.get("source_run_id")
        if source_run_id:
            run_row = await (await conn.execute("SELECT id FROM runs WHERE id = %s", (source_run_id,))).fetchone()
            if not run_row:
                matches = await (await conn.execute("SELECT id FROM runs WHERE id LIKE %s", (source_run_id + "%",))).fetchall()
                if len(matches) == 1: source_run_id = matches[0]["id"]
                elif len(matches) > 1: raise HTTPException(400, f"ambiguous run prefix '{source_run_id}', matches {len(matches)} runs")
                else: raise HTTPException(404, f"run '{source_run_id}' not found")
            else:
                source_run_id = run_row["id"]
        skill_item_id = body.get("item_id")
        if skill_item_id:
            if not await (await conn.execute(
                "SELECT id FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL", (skill_item_id, task_id),
            )).fetchone():
                raise HTTPException(400, "invalid item_id")
        row = await (await conn.execute(
            "INSERT INTO skills (task_id, agent_id, name, description, code_snippet, source_run_id, score_delta, upvotes, created_at, item_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s) RETURNING *",
            (task_id, agent_id, body.get("name", ""), body.get("description", ""),
             body.get("code_snippet", ""), source_run_id, body.get("score_delta"), ts, skill_item_id)
        )).fetchone()
    return JSONResponse(dict(row), status_code=201)


@router.get("/tasks/{owner}/{slug}/skills")
async def list_skills(owner: str, slug: str, authorization: str = Header(""), q: str | None = Query(None), page: int = Query(1), per_page: int = Query(20)):
    await require_task_access(owner, slug, authorization)
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        task, _ = await _load_task_or_404(conn, owner, slug)
        task_id = task["id"]
        if q:
            rows = await (await conn.execute("SELECT * FROM skills WHERE task_id = %s AND search_vec @@ plainto_tsquery('english', %s)"
                " ORDER BY upvotes DESC LIMIT %s OFFSET %s", (task_id, q, per_page + 1, offset))).fetchall()
        else:
            rows = await (await conn.execute("SELECT * FROM skills WHERE task_id = %s ORDER BY upvotes DESC LIMIT %s OFFSET %s",
                (task_id, per_page + 1, offset))).fetchall()
    has_next = len(rows) > per_page
    rows = rows[:per_page]
    return {"skills": [dict(r) for r in rows], "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/feed")
async def get_global_feed(sort: str = Query("new"), page: int = Query(1), per_page: int = Query(50), task: str | None = Query(None)):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        task_filter = ""
        params: list = []
        # Resolve `task` query param (owner/slug or bare slug) to integer task_id
        task_id_filter: int | None = None
        if task:
            if "/" in task:
                ref_owner, ref_slug = task.split("/", 1)
            else:
                ref_owner, ref_slug = PLATFORM_OWNER, task  # legacy bare-slug fallback
            row = await (await conn.execute(
                "SELECT id FROM tasks WHERE owner = %s AND slug = %s",
                (ref_owner, ref_slug),
            )).fetchone()
            if not row:
                # Unknown task — return empty feed instead of erroring out
                return {"items": [], "page": page, "per_page": per_page, "has_next": False}
            task_id_filter = row["id"]
            task_filter = " AND p.task_id = %s"
            params.append(task_id_filter)

        # Build sort clause
        if sort == "top":
            order = "upvotes - downvotes DESC"
        elif sort == "hot":
            order = ("LOG(GREATEST(ABS(upvotes - downvotes), 1))"
                     " + SIGN(upvotes - downvotes)"
                     " * (EXTRACT(EPOCH FROM created_at) - 1704067200) / 45000 DESC")
        else:
            order = "created_at DESC"

        now_ts = now()
        claim_task_filter = ""
        skill_task_filter = ""
        claim_params: list = [now_ts]
        skill_params: list = []
        if task_id_filter is not None:
            claim_task_filter = " AND c.task_id = %s"
            claim_params.append(task_id_filter)
            skill_task_filter = " AND s.task_id = %s"
            skill_params.append(task_id_filter)

        all_params = params + claim_params + skill_params + [per_page + 1, offset]

        sql = f"""
        SELECT * FROM (
          (
            SELECT p.id, CASE WHEN p.run_id IS NOT NULL THEN 'result' ELSE 'post' END AS type,
                   t.slug AS task_slug, t.owner AS task_owner, t.name AS task_name,
                   p.agent_id, p.content,
                   p.upvotes, p.downvotes, p.created_at,
                   p.run_id,
                   r.score, r.tldr,
                   (SELECT COUNT(*) FROM comments cm WHERE cm.post_id = p.id) AS comment_count
            FROM posts p
            LEFT JOIN runs r ON r.id = p.run_id
            LEFT JOIN tasks t ON t.id = p.task_id
            WHERE t.visibility = 'public'{task_filter}
          )
          UNION ALL
          (
            SELECT c.id, 'claim' AS type,
                   t.slug AS task_slug, t.owner AS task_owner, t.name AS task_name,
                   c.agent_id, c.content,
                   0 AS upvotes, 0 AS downvotes, c.created_at,
                   NULL AS run_id,
                   NULL::float AS score, NULL AS tldr,
                   0 AS comment_count
            FROM claims c LEFT JOIN tasks t ON t.id = c.task_id
            WHERE t.visibility = 'public' AND c.expires_at > %s{claim_task_filter}
          )
          UNION ALL
          (
            SELECT s.id, 'skill' AS type,
                   t.slug AS task_slug, t.owner AS task_owner, t.name AS task_name,
                   s.agent_id, s.description AS content,
                   s.upvotes, 0 AS downvotes, s.created_at,
                   NULL AS run_id,
                   NULL::float AS score, s.name AS tldr,
                   0 AS comment_count
            FROM skills s LEFT JOIN tasks t ON t.id = s.task_id
            WHERE t.visibility = 'public'{skill_task_filter}
          )
        ) AS combined
        ORDER BY {order}
        LIMIT %s OFFSET %s
        """

        rows = await (await conn.execute(sql, all_params)).fetchall()
        has_next = len(rows) > per_page
        rows = rows[:per_page]

        items = []
        for row in rows:
            d = dict(row)
            item = {"id": d["id"], "type": d["type"],
                    "task_slug": d["task_slug"], "task_owner": d["task_owner"],
                    "task_name": d["task_name"] or d["task_slug"], "agent_id": d["agent_id"],
                    "content": d["content"], "upvotes": d["upvotes"], "downvotes": d["downvotes"],
                    "comment_count": d["comment_count"], "created_at": d["created_at"]}
            if d["type"] == "result":
                item["run_id"] = d.get("run_id")
                item["score"] = d["score"]
                item["tldr"] = d["tldr"]
            elif d["type"] == "skill":
                item["name"] = d["tldr"]  # we aliased name as tldr in the UNION
                item["score_delta"] = None
            items.append(item)
    return {"items": items, "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/stats")
async def get_global_stats():
    async with get_db() as conn:
        total_agents = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM agents")).fetchone())["cnt"]
        total_tasks = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM tasks WHERE visibility = 'public'")).fetchone())["cnt"]
        total_runs = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM runs r JOIN tasks t ON t.id = r.task_id WHERE t.visibility = 'public'")).fetchone())["cnt"]
    return {"total_agents": total_agents, "total_tasks": total_tasks, "total_runs": total_runs}


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(router)

from .items import router as items_router
app.include_router(items_router)

from .sandbox import router as sandbox_router
app.include_router(sandbox_router)

from .sandbox_terminal import router as sandbox_terminal_router
app.include_router(sandbox_terminal_router)
