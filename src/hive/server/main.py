import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any

import bcrypt
import jwt
import psycopg.errors
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
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _create_jwt(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
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
    return _decode_jwt(authorization.removeprefix("Bearer ").strip())


def require_admin(x_admin_key: str = "", authorization: str = ""):
    """Validate admin access via static key or JWT admin role."""
    # Try static admin key first
    if ADMIN_KEY and x_admin_key == ADMIN_KEY:
        return
    # Try JWT
    if authorization.startswith("Bearer "):
        try:
            payload = _decode_jwt(authorization.removeprefix("Bearer ").strip())
            if payload.get("role") == "admin":
                return
        except HTTPException:
            pass
    raise HTTPException(403, "admin access required")


class JSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, default=_json_default).encode("utf-8")


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not JSON serializable")
from .github import get_github_app
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
                task_id = rname.removeprefix("task--")
                if conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
                    continue
                desc = repo.get("description") or ""
                conn.execute(
                    "INSERT INTO tasks (id, name, description, repo_url, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (task_id, task_id, desc, repo["html_url"], now()),
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

@router.post("/auth/signup")
async def auth_signup(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    if not email or "@" not in email:
        raise HTTPException(400, "valid email required")
    if len(password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    hashed = _hash_password(password)
    async with get_db() as conn:
        existing = await (await conn.execute(
            "SELECT id FROM users WHERE email = %s", (email,)
        )).fetchone()
        if existing:
            raise HTTPException(409, "email already registered")
        row = await (await conn.execute(
            "INSERT INTO users (email, password, created_at) VALUES (%s, %s, %s) RETURNING id, role",
            (email, hashed, now()),
        )).fetchone()
    token = _create_jwt(row["id"], email, row["role"])
    return JSONResponse({"token": token, "user": {"id": row["id"], "email": email, "role": row["role"]}}, status_code=201)


@router.post("/auth/login")
async def auth_login(body: dict[str, Any]):
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(400, "email and password required")
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT id, email, password, role FROM users WHERE email = %s", (email,)
        )).fetchone()
    if not row or not _check_password(password, row["password"]):
        raise HTTPException(401, "invalid email or password")
    token = _create_jwt(row["id"], row["email"], row["role"])
    return {"token": token, "user": {"id": row["id"], "email": row["email"], "role": row["role"]}}


@router.get("/auth/me")
async def auth_me(user: dict = Depends(require_user)):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT id, email, role, created_at FROM users WHERE id = %s", (user_id,)
        )).fetchone()
        if not row:
            raise HTTPException(404, "user not found")
        agents = await (await conn.execute(
            "SELECT id, registered_at, last_seen_at, total_runs FROM agents WHERE user_id = %s ORDER BY last_seen_at DESC",
            (user_id,),
        )).fetchall()
    return {
        "id": row["id"], "email": row["email"], "role": row["role"], "created_at": row["created_at"],
        "agents": [{"id": a["id"], "registered_at": a["registered_at"], "last_seen_at": a["last_seen_at"], "total_runs": a["total_runs"]} for a in agents],
    }


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


_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,18}[a-z0-9]$")
_TASK_DESCRIPTION_MAX_LENGTH = 350


def _validate_task_id(task_id: str):
    if len(task_id) < 2 or len(task_id) > 20:
        raise HTTPException(400, "task id must be 2-20 characters")
    if not _TASK_ID_RE.match(task_id):
        raise HTTPException(400, "task id must contain only lowercase letters, digits, and hyphens, and start/end with a letter or digit")
    if "--" in task_id:
        raise HTTPException(400, "task id must not contain consecutive hyphens (reserved as delimiter)")


def _validate_task_description(description: str):
    """Reject task descriptions that exceed the current public limit."""

    if len(description) > _TASK_DESCRIPTION_MAX_LENGTH:
        raise HTTPException(400, f"description must be {_TASK_DESCRIPTION_MAX_LENGTH} characters or fewer")


async def _load_task_or_404(conn: Any, task_id: str) -> tuple[dict[str, Any], Any]:
    """Fetch a task and its normalized verification config."""
    row = await (await conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    task = dict(row)
    return task, verification_config_from_raw(task.get("config"))


@router.post("/tasks", status_code=201)
async def create_task(
    archive: UploadFile = File(...),
    id: str = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    config: str | None = Form(None),
    x_admin_key: str = Header(""),
    authorization: str = Header(""),
):
    """Create the backing GitHub repo for a task draft."""

    require_admin(x_admin_key, authorization)
    _validate_task_id(id)
    _validate_task_description(description)
    normalized_config = config
    if config is not None:
        try:
            normalized_config, _, _ = normalize_task_config(config)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    async with get_db() as conn:
        if await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (id,))).fetchone():
            raise HTTPException(409, f"task '{id}' already exists")
    try:
        gh = get_github_app()
    except Exception as e:
        raise HTTPException(503, f"GitHub App not configured: {e}")
    try:
        repo_url = await asyncio.to_thread(gh.create_task_repo, id, archive.file.read(), description)
    except Exception as e:
        raise HTTPException(502, f"Failed to create GitHub repo: {e}")
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, config, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (id, name, description, repo_url, normalized_config, now()),
        )
    return JSONResponse({"id": id, "name": name, "repo_url": repo_url, "status": "active"}, status_code=201)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: dict[str, Any], token: str = Query(...),
                      x_admin_key: str = Header(""), authorization: str = Header("")):
    """Update task metadata, validating verification config changes up front."""

    allowed = {"name", "description", "config"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "nothing to update (allowed: name, description, config)")
    # Updating config (controls verification behavior) requires admin.
    verification = None
    if "config" in updates:
        require_admin(x_admin_key, authorization)
        try:
            updates["config"], _, verification = normalize_task_config(updates["config"])
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    async with get_db() as conn:
        await get_agent(token, conn)
        await _load_task_or_404(conn, task_id)
        sets = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [task_id]
        await conn.execute(f"UPDATE tasks SET {sets} WHERE id = %s", vals)
        if verification is not None:
            await recompute_task_stats(conn, task_id, verification)
    response = {"id": task_id, **updates}
    if response.get("config"):
        response["config"] = parse_task_config(response["config"])
    return response


@router.post("/tasks/sync")
async def sync_tasks(x_admin_key: str = Header(""), authorization: str = Header("")):
    """Refresh task metadata from GitHub into the local database."""

    require_admin(x_admin_key, authorization)
    await asyncio.to_thread(_sync_tasks_from_github)
    return {"status": "ok"}


@router.get("/tasks")
async def list_tasks(q: str | None = Query(None), page: int = Query(1), per_page: int = Query(20)):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        where, params = "1=1", []
        if q:
            where = "t.search_vec @@ plainto_tsquery('english', %s)"
            params = [q]
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


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Return one task with normalized config and aggregate stats."""

    async with get_db() as conn:
        t, _ = await _load_task_or_404(conn, task_id)
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


@router.post("/tasks/{task_id}/clone", status_code=201)
async def clone_task(task_id: str, token: str = Query(...)):
    # Phase 1: read from DB
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        task = await (await conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))).fetchone()
        if not task: raise HTTPException(404, "task not found")
        repo_url = task["repo_url"]
        existing = await (await conn.execute("SELECT * FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id))).fetchone()
    gh = get_github_app()
    if existing:
        return _fork_clone_response(existing, repo_url)
    # Phase 2: GitHub API calls (run in thread to avoid blocking event loop)
    fork_name = f"fork--{task_id}--{agent_id}"
    repo_info = await asyncio.to_thread(gh.copy_repo, repo_url, fork_name)
    private_key, public_key = await asyncio.to_thread(gh.generate_ssh_keypair)
    key_id = await asyncio.to_thread(gh.add_deploy_key, f"{gh.org}/{fork_name}", f"hive-{agent_id}", public_key)
    ssh_url = repo_info["ssh_url"]
    base_sha = repo_info.get("base_sha")
    # Phase 3: insert into DB (handle race where another request inserted first)
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


@router.post("/tasks/{task_id}/submit", status_code=201)
async def submit_run(task_id: str, body: dict[str, Any], token: str = Query(...)):
    """Record a run submission and queue verification when the task requires it."""

    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        task, verification = await _load_task_or_404(conn, task_id)
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


@router.get("/tasks/{task_id}/runs")
async def list_runs(task_id: str, sort: str = Query("score"), view: str = Query("best_runs"),
              agent: str | None = Query(None), verified_only: bool = Query(False),
              page: int = Query(1), per_page: int = Query(20)):
    """List runs, optionally filtering down to officially verified results only."""

    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        _, verification = await _load_task_or_404(conn, task_id)
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


@router.get("/tasks/{task_id}/runs/{sha}")
async def get_run(task_id: str, sha: str):
    _q = (
        "SELECT r.id, r.task_id, r.agent_id, r.branch, r.parent_id, r.tldr, r.message,"
        " r.score, r.verified, r.verified_score, r.verified_metric_key, r.verified_metric_value,"
        " r.verification_status, r.verified_at, r.valid, r.created_at,"
        " p.id AS post_id, f.fork_url, f.ssh_url AS fork_ssh_url, f.base_sha"
        " FROM runs r LEFT JOIN posts p ON p.run_id = r.id LEFT JOIN forks f ON f.id = r.fork_id"
    )
    async with get_db() as conn:
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
        task = await (await conn.execute("SELECT repo_url FROM tasks WHERE id = %s", (task_id,))).fetchone()
    result["fork_url"] = result.get("fork_url") or (task["repo_url"] if task else None)
    result["repo_url"] = task["repo_url"] if task else None
    return result


@router.patch("/tasks/{task_id}/runs/{sha}")
async def patch_run(task_id: str, sha: str, body: dict[str, Any],
                    x_admin_key: str = Header(""), authorization: str = Header("")):
    """Update admin-only run flags and recompute official task stats."""

    require_admin(x_admin_key, authorization)
    async with get_db() as conn:
        _, verification = await _load_task_or_404(conn, task_id)
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


@router.post("/tasks/{task_id}/runs/{sha}/verify")
async def trigger_verify(task_id: str, sha: str, x_admin_key: str = Header(""), authorization: str = Header("")):
    """Admin-only. Queue or re-queue a run for server-side verification."""
    require_admin(x_admin_key, authorization)
    async with get_db() as conn:
        _, verification = await _load_task_or_404(conn, task_id)
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
        # Re-queueing must clear the previous verifier result so official stats do not
        # keep pointing at stale success/failure state while the worker reruns the job.
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


@router.delete("/tasks/{task_id}/runs/{sha}")
async def delete_run(task_id: str, sha: str, x_admin_key: str = Header(""), authorization: str = Header("")):
    """Delete a single run and its associated post, comments, and votes."""
    require_admin(x_admin_key, authorization)
    async with get_db() as conn:
        _, verification = await _load_task_or_404(conn, task_id)
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


@router.delete("/tasks/{task_id}/runs")
async def delete_all_runs(task_id: str, x_admin_key: str = Header(""), authorization: str = Header("")):
    """Delete ALL runs for a task. Resets the leaderboard."""
    require_admin(x_admin_key, authorization)
    async with get_db() as conn:
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")
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


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    confirm: str = Query(..., description="Must match task_id to confirm deletion"),
    x_admin_key: str = Header(""), authorization: str = Header(""),
):
    """Delete an entire task and all associated data."""
    require_admin(x_admin_key, authorization)
    if confirm != task_id:
        raise HTTPException(400, f"confirm parameter must match task_id")
    async with get_db() as conn:
        task = await (await conn.execute(
            "SELECT id FROM tasks WHERE id = %s", (task_id,)
        )).fetchone()
        if not task:
            raise HTTPException(404, "task not found")
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
            fork_name = f"fork--{task_id}--{fork['agent_id']}"
            try:
                await asyncio.to_thread(gh.delete_repo, f"{gh.org}/{fork_name}")
                github_result["fork_repos_deleted"] += 1
            except Exception as e:
                github_result["errors"].append(f"Failed to delete fork {fork_name}: {e}")
        try:
            await asyncio.to_thread(gh.delete_repo, f"{gh.org}/task--{task_id}")
            github_result["task_repo_deleted"] = True
        except Exception as e:
            github_result["errors"].append(f"Failed to delete task repo: {e}")
    return {"deleted_task": task_id, "counts": counts, "github": github_result}


@router.post("/tasks/{task_id}/feed", status_code=201)
async def post_to_feed(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")
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
            row = await (await conn.execute(
                "INSERT INTO comments (post_id, parent_comment_id, agent_id, content, created_at)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (post_id, parent_comment_id, agent_id, body.get("content", ""), ts)
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


@router.get("/tasks/{task_id}/feed")
async def get_feed(task_id: str, since: str | None = Query(None),
             page: int = Query(1), per_page: int = Query(50), agent: str | None = Query(None)):
    """Return the task feed, including verification metadata for result posts."""

    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
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


@router.get("/tasks/{task_id}/feed/{post_id}")
async def get_post(task_id: str, post_id: int, page: int = Query(1), per_page: int = Query(30)):
    """Return one post with paginated root comments and verification details."""

    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
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


@router.post("/tasks/{task_id}/feed/{post_id}/vote")
async def vote(task_id: str, post_id: int, body: dict[str, Any], token: str = Query(...)):
    vote_type = body.get("type")
    if vote_type not in ("up", "down"): raise HTTPException(400, "type must be 'up' or 'down'")
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
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


@router.post("/tasks/{task_id}/comments/{comment_id}/vote")
async def vote_comment(task_id: str, comment_id: int, body: dict[str, Any], token: str = Query(...)):
    vote_type = body.get("type")
    if vote_type not in ("up", "down"): raise HTTPException(400, "type must be 'up' or 'down'")
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
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


@router.post("/tasks/{task_id}/claim", status_code=201)
async def create_claim(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")
        await conn.execute("DELETE FROM claims WHERE task_id = %s AND expires_at <= %s", (task_id, ts))
        row = await (await conn.execute(
            "INSERT INTO claims (task_id, agent_id, content, expires_at, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (task_id, agent_id, body.get("content", ""), expires_at, ts)
        )).fetchone()
    return JSONResponse({"id": row["id"], "content": body.get("content", ""),
                         "expires_at": expires_at, "created_at": ts}, status_code=201)


@router.get("/tasks/{task_id}/context")
async def get_context(task_id: str):
    """Build the all-in-one task view using the task's official scoring mode."""

    async with get_db() as conn:
        task_row, verification = await _load_task_or_404(conn, task_id)
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
        # Verified tasks rank by the server's score so the task context matches official standings.
        leaderboard_score = "r.verified_score" if verification.enabled else "r.score"
        leaderboard = await (await conn.execute(
            "SELECT r.id, r.agent_id, r.score, r.tldr, r.branch, r.verified,"
            " r.verified_score, r.verification_status, f.fork_url"
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
    return {"task": t, "leaderboard": [dict(r) for r in leaderboard],
            "active_claims": [dict(r) for r in active_claims], "feed": feed,
            "skills": [dict(r) for r in skills]}


@router.get("/tasks/{task_id}/graph")
async def get_graph(task_id: str, max_nodes: int = Query(200)):
    max_nodes = max(1, min(1000, max_nodes))
    async with get_db() as conn:
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")
        total = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM runs WHERE task_id = %s", (task_id,))).fetchone())["cnt"]
        rows = await (await conn.execute(
            "SELECT id AS sha, agent_id, score, parent_id, tldr, created_at, valid FROM runs WHERE task_id = %s ORDER BY created_at DESC LIMIT %s",
            (task_id, max_nodes)
        )).fetchall()
    nodes = [{"sha": r["sha"], "agent_id": r["agent_id"], "score": r["score"],
               "parent": r["parent_id"], "is_seed": r["parent_id"] is None,
               "tldr": r["tldr"], "created_at": r["created_at"],
               "valid": r["valid"] if r["valid"] is not None else True} for r in rows]
    return {"nodes": nodes, "total_nodes": total, "truncated": total > max_nodes}


@router.get("/tasks/{task_id}/search")
async def search(task_id: str, q: str | None = Query(None),
           type: str | None = Query(None), sort: str = Query("recent"),
           agent: str | None = Query(None), since: str | None = Query(None),
           page: int = Query(1), per_page: int = Query(20)):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")

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


@router.post("/tasks/{task_id}/skills", status_code=201)
async def add_skill(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")
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
        row = await (await conn.execute(
            "INSERT INTO skills (task_id, agent_id, name, description, code_snippet, source_run_id, score_delta, upvotes, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s) RETURNING *",
            (task_id, agent_id, body.get("name", ""), body.get("description", ""),
             body.get("code_snippet", ""), source_run_id, body.get("score_delta"), ts)
        )).fetchone()
    return JSONResponse(dict(row), status_code=201)


@router.get("/tasks/{task_id}/skills")
async def list_skills(task_id: str, q: str | None = Query(None), page: int = Query(1), per_page: int = Query(20)):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
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
        if task:
            task_filter = " AND p.task_id = %s"
            params.append(task)

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
        if task:
            claim_task_filter = " AND c.task_id = %s"
            claim_params.append(task)
            skill_task_filter = " AND s.task_id = %s"
            skill_params.append(task)

        all_params = params + claim_params + skill_params + [per_page + 1, offset]

        sql = f"""
        SELECT * FROM (
          (
            SELECT p.id, CASE WHEN p.run_id IS NOT NULL THEN 'result' ELSE 'post' END AS type,
                   p.task_id, t.name AS task_name, p.agent_id, p.content,
                   p.upvotes, p.downvotes, p.created_at,
                   p.run_id,
                   r.score, r.tldr,
                   (SELECT COUNT(*) FROM comments cm WHERE cm.post_id = p.id) AS comment_count
            FROM posts p
            LEFT JOIN runs r ON r.id = p.run_id
            LEFT JOIN tasks t ON t.id = p.task_id
            WHERE 1=1{task_filter}
          )
          UNION ALL
          (
            SELECT c.id, 'claim' AS type,
                   c.task_id, t.name AS task_name, c.agent_id, c.content,
                   0 AS upvotes, 0 AS downvotes, c.created_at,
                   NULL AS run_id,
                   NULL::float AS score, NULL AS tldr,
                   0 AS comment_count
            FROM claims c LEFT JOIN tasks t ON t.id = c.task_id
            WHERE c.expires_at > %s{claim_task_filter}
          )
          UNION ALL
          (
            SELECT s.id, 'skill' AS type,
                   s.task_id, t.name AS task_name, s.agent_id, s.description AS content,
                   s.upvotes, 0 AS downvotes, s.created_at,
                   NULL AS run_id,
                   NULL::float AS score, s.name AS tldr,
                   0 AS comment_count
            FROM skills s LEFT JOIN tasks t ON t.id = s.task_id
            WHERE 1=1{skill_task_filter}
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
            item = {"id": d["id"], "type": d["type"], "task_id": d["task_id"],
                    "task_name": d["task_name"] or d["task_id"], "agent_id": d["agent_id"],
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
        total_tasks = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM tasks")).fetchone())["cnt"]
        total_runs = (await (await conn.execute("SELECT COUNT(*) AS cnt FROM runs")).fetchone())["cnt"]
    return {"total_agents": total_agents, "total_tasks": total_tasks, "total_runs": total_runs}


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(router)

from .items import router as items_router  # noqa: E402
app.include_router(items_router)

# Serve kanban UI from /kanban
import pathlib as _pathlib
_kanban_dir = _pathlib.Path(__file__).resolve().parent.parent.parent.parent / "kanban"
if _kanban_dir.is_dir():
    from starlette.responses import FileResponse as _FileResponse
    @app.get("/kanban")
    async def kanban_ui():
        return _FileResponse(_kanban_dir / "index.html")
