import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any

import psycopg.errors
from fastapi import APIRouter, FastAPI, File, Form, Header, HTTPException, Query, UploadFile

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
from fastapi.middleware.cors import CORSMiddleware


def require_admin(x_admin_key: str):
    """Validate admin key. Raises 403 if invalid."""
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(403, "invalid admin key")
from fastapi.responses import JSONResponse as _BaseJSONResponse

from .db import init_pool, close_pool, get_db, get_db_sync, now, paginate


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


async def get_agent(token: str, conn) -> str:
    row = await (await conn.execute("SELECT id FROM agents WHERE id = %s", (token,))).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    await conn.execute("UPDATE agents SET last_seen_at = %s WHERE id = %s", (now(), token))
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
    async with get_db() as conn:
        if preferred:
            _validate_agent_id(preferred)
            if await (await conn.execute("SELECT 1 FROM agents WHERE id = %s", (preferred,))).fetchone():
                raise HTTPException(409, f"name '{preferred}' is already taken")
            agent_id = preferred
        else:
            agent_id = await generate_name(conn)
        try:
            await conn.execute("INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)", (agent_id, ts, ts))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, f"name '{agent_id}' is already taken")
    return JSONResponse({"id": agent_id, "token": agent_id, "registered_at": ts}, status_code=201)


_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,18}[a-z0-9]$")


def _validate_task_id(task_id: str):
    if len(task_id) < 2 or len(task_id) > 20:
        raise HTTPException(400, "task id must be 2-20 characters")
    if not _TASK_ID_RE.match(task_id):
        raise HTTPException(400, "task id must contain only lowercase letters, digits, and hyphens, and start/end with a letter or digit")
    if "--" in task_id:
        raise HTTPException(400, "task id must not contain consecutive hyphens (reserved as delimiter)")


@router.post("/tasks", status_code=201)
async def create_task(
    archive: UploadFile = File(...),
    id: str = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    config: str | None = Form(None),
    x_admin_key: str = Header(...),
):
    require_admin(x_admin_key)
    _validate_task_id(id)
    try:
        gh = get_github_app()
    except Exception as e:
        raise HTTPException(503, f"GitHub App not configured: {e}")
    try:
        repo_url = await asyncio.to_thread(gh.create_task_repo, id, archive.file.read(), description)
    except Exception as e:
        raise HTTPException(502, f"Failed to create GitHub repo: {e}")
    return JSONResponse({"id": id, "name": name, "repo_url": repo_url, "status": "draft"}, status_code=201)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: dict[str, Any], token: str = Query(...)):
    allowed = {"name", "description", "config"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "nothing to update (allowed: name, description, config)")
    async with get_db() as conn:
        await get_agent(token, conn)
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")
        sets = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [task_id]
        await conn.execute(f"UPDATE tasks SET {sets} WHERE id = %s", vals)
    return {"id": task_id, **updates}


@router.post("/tasks/sync")
async def sync_tasks(x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
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
            f"SELECT t.*, COUNT(r.id) AS total_runs, MAX(r.score) AS best_score_calc,"
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
                "best_score": d.get("best_score") if d.get("best_score") is not None else d.pop("best_score_calc"),
                "agents_contributing": d.pop("agents_contributing"),
                "improvements": d.get("improvements", 0),
                "last_activity": d.pop("last_activity", None),
            }
            d.pop("best_score_calc", None)
            d["stats"] = stats
            tasks.append(d)
    return {"tasks": tasks, "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    async with get_db() as conn:
        row = await (await conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))).fetchone()
        if not row: raise HTTPException(404, "task not found")
        t = dict(row)
        if t.get("config"):
            try: t["config"] = json.loads(t["config"])
            except Exception: pass
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
        if existing:
            return JSONResponse({"fork_url": existing["fork_url"], "ssh_url": existing["ssh_url"],
                                 "upstream_url": repo_url, "private_key": ""}, status_code=201)
    # Phase 2: GitHub API calls (run in thread to avoid blocking event loop)
    fork_name = f"fork--{task_id}--{agent_id}"
    gh = get_github_app()
    repo_info = await asyncio.to_thread(gh.copy_repo, repo_url, fork_name)
    private_key, public_key = await asyncio.to_thread(gh.generate_ssh_keypair)
    key_id = await asyncio.to_thread(gh.add_deploy_key, f"{gh.org}/{fork_name}", f"hive-{agent_id}", public_key)
    ssh_url = repo_info["ssh_url"]
    # Phase 3: insert into DB (handle race where another request inserted first)
    async with get_db() as conn:
        try:
            await conn.execute(
                "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, deploy_key_id, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (task_id, agent_id, repo_info["html_url"], ssh_url, key_id, now()),
            )
        except psycopg.errors.UniqueViolation:
            await conn.rollback()
            existing = await (await conn.execute(
                "SELECT * FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id)
            )).fetchone()
            return JSONResponse({"fork_url": existing["fork_url"], "ssh_url": existing["ssh_url"],
                                 "upstream_url": repo_url, "private_key": ""}, status_code=201)
    return JSONResponse({"fork_url": repo_info["html_url"], "ssh_url": ssh_url,
                         "upstream_url": repo_url, "private_key": private_key}, status_code=201)


@router.post("/tasks/{task_id}/submit", status_code=201)
async def submit_run(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")
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
        fork_row = await (await conn.execute("SELECT id FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id))).fetchone()
        fork_id = fork_row["id"] if fork_row else None
        await conn.execute(
            "INSERT INTO runs (id, task_id, parent_id, agent_id, branch, tldr, message, score, verified, created_at, fork_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)",
            (sha, task_id, parent_id, agent_id, body.get("branch", ""),
             body.get("tldr", ""), body.get("message", ""), score, ts, fork_id),
        )
        await conn.execute("UPDATE agents SET total_runs = total_runs + 1 WHERE id = %s", (agent_id,))
        if score is not None:
            await conn.execute(
                "UPDATE tasks SET"
                " improvements = CASE WHEN %s > COALESCE(best_score, '-Infinity'::float) THEN improvements + 1 ELSE improvements END,"
                " best_score = GREATEST(COALESCE(best_score, '-Infinity'::float), %s)"
                " WHERE id = %s",
                (score, score, task_id),
            )
        post_id = (await (await conn.execute(
            "INSERT INTO posts (task_id, agent_id, content, run_id, upvotes, downvotes, created_at)"
            " VALUES (%s, %s, %s, %s, 0, 0, %s) RETURNING id",
            (task_id, agent_id, body.get("message", ""), sha, ts),
        )).fetchone())["id"]
    run = {"id": sha, "task_id": task_id, "agent_id": agent_id, "branch": body.get("branch", ""),
           "parent_id": parent_id, "tldr": body.get("tldr", ""), "message": body.get("message", ""),
           "score": score, "verified": False, "created_at": ts, "fork_id": fork_id}
    return JSONResponse({"run": run, "post_id": post_id}, status_code=201)


@router.get("/tasks/{task_id}/runs")
async def list_runs(task_id: str, sort: str = Query("score"), view: str = Query("best_runs"),
              agent: str | None = Query(None), page: int = Query(1), per_page: int = Query(20)):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
            raise HTTPException(404, "task not found")

        if view == "contributors":
            rows = await (await conn.execute(
                "SELECT agent_id, COUNT(*) AS total_runs, MAX(score) AS best_score,"
                " COUNT(*) FILTER ("
                "   WHERE score > COALESCE("
                "     (SELECT MAX(r2.score) FROM runs r2"
                "      WHERE r2.task_id = runs.task_id"
                "      AND r2.created_at < runs.created_at AND r2.score IS NOT NULL),"
                "     '-Infinity'::float)"
                " ) AS improvements"
                " FROM runs"
                " WHERE task_id = %s AND score IS NOT NULL"
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
                "SELECT r.id AS run_id, r.agent_id, r.score - p.score AS delta,"
                " p.score AS from_score, r.score AS to_score, r.tldr"
                " FROM runs r JOIN runs p ON r.parent_id = p.id"
                " WHERE r.task_id = %s AND r.score IS NOT NULL AND p.score IS NOT NULL"
                " ORDER BY delta DESC LIMIT %s OFFSET %s",
                (task_id, per_page + 1, offset)
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            return {"view": "deltas", "entries": [dict(r) for r in rows], "page": page, "per_page": per_page, "has_next": has_next}

        if view == "improvers":
            rows = await (await conn.execute(
                "WITH ranked AS ("
                " SELECT agent_id, score,"
                " MAX(score) OVER (ORDER BY created_at"
                " ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_best"
                " FROM runs WHERE task_id = %s AND score IS NOT NULL"
                ")"
                " SELECT agent_id,"
                " COUNT(*) FILTER (WHERE score > COALESCE(prev_best, '-Infinity'::float)) AS improvements_to_best,"
                " MAX(score) AS best_score"
                " FROM ranked"
                " GROUP BY agent_id"
                " ORDER BY improvements_to_best DESC"
                " LIMIT %s OFFSET %s",
                (task_id, per_page + 1, offset)
            )).fetchall()
            has_next = len(rows) > per_page
            rows = rows[:per_page]
            return {"view": "improvers", "entries": [dict(r) for r in rows], "page": page, "per_page": per_page, "has_next": has_next}

        where, params = "r.task_id = %s AND r.score IS NOT NULL AND r.valid IS NOT FALSE", [task_id]
        if agent: where += " AND r.agent_id = %s"; params.append(agent)
        order = _parse_sort(sort, {"score": "r.score", "recent": "r.created_at"})
        params.extend([per_page + 1, offset])
        rows = await (await conn.execute(
            f"SELECT r.id, r.agent_id, r.branch, r.parent_id, r.tldr, r.score, r.verified, r.valid, r.created_at, f.fork_url"
            f" FROM runs r LEFT JOIN forks f ON f.id = r.fork_id WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s", params
        )).fetchall()
        has_next = len(rows) > per_page
        rows = rows[:per_page]
        return {"view": "best_runs", "runs": [dict(r) for r in rows], "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/tasks/{task_id}/runs/{sha}")
async def get_run(task_id: str, sha: str):
    _q = ("SELECT r.*, p.id AS post_id, f.fork_url, f.ssh_url AS fork_ssh_url, f.base_sha"
          " FROM runs r LEFT JOIN posts p ON p.run_id = r.id LEFT JOIN forks f ON f.id = r.fork_id")
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
                    x_admin_key: str = Header(...)):
    require_admin(x_admin_key)
    async with get_db() as conn:
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
            # Recalculate best_score excluding invalid runs
            best = await (await conn.execute(
                "SELECT MAX(score) AS val FROM runs WHERE task_id = %s AND valid = TRUE", (task_id,)
            )).fetchone()
            await conn.execute("UPDATE tasks SET best_score = %s WHERE id = %s", (best["val"], task_id))
        return {"id": sha, "valid": body.get("valid")}


@router.delete("/tasks/{task_id}/runs/{sha}")
async def delete_run(task_id: str, sha: str, x_admin_key: str = Header(...)):
    """Delete a single run and its associated post, comments, and votes."""
    require_admin(x_admin_key)
    async with get_db() as conn:
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
        # Recalculate task stats (exclude invalid runs)
        best = await (await conn.execute(
            "SELECT MAX(score) AS val FROM runs WHERE task_id = %s AND valid IS NOT FALSE", (task_id,)
        )).fetchone()
        await conn.execute(
            "UPDATE tasks SET best_score = %s WHERE id = %s",
            (best["val"], task_id))
    return {"deleted": sha}


@router.delete("/tasks/{task_id}/runs")
async def delete_all_runs(task_id: str, x_admin_key: str = Header(...)):
    """Delete ALL runs for a task. Resets the leaderboard."""
    require_admin(x_admin_key)
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
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        where, params = "p.task_id = %s", [task_id]
        if since: where += " AND p.created_at > %s"; params.append(since)
        if agent: where += " AND p.agent_id = %s"; params.append(agent)
        params.extend([per_page + 1, offset])
        posts = await (await conn.execute(
            f"SELECT p.*, r.score, r.tldr FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
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
            items.append(item)
        active_claims = [{"id": c["id"], "agent_id": c["agent_id"],
                          "content": c["content"], "expires_at": c["expires_at"],
                          "created_at": c["created_at"]} for c in claims]
    return {"items": items, "active_claims": active_claims,
            "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/tasks/{task_id}/feed/{post_id}")
async def get_post(task_id: str, post_id: int, page: int = Query(1), per_page: int = Query(30)):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT p.*, r.score, r.tldr, r.branch FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
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
    async with get_db() as conn:
        task_row = await (await conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))).fetchone()
        if not task_row: raise HTTPException(404, "task not found")
        t = dict(task_row)
        if t.get("config"):
            try: t["config"] = json.loads(t["config"])
            except Exception: pass
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
        leaderboard = await (await conn.execute(
            "SELECT r.id, r.agent_id, r.score, r.tldr, r.branch, r.verified, f.fork_url"
            " FROM runs r LEFT JOIN forks f ON f.id = r.fork_id"
            " WHERE r.task_id = %s AND r.score IS NOT NULL AND r.valid IS NOT FALSE ORDER BY r.score DESC LIMIT 5", (task_id,)
        )).fetchall()
        now_ts = now()
        active_claims = await (await conn.execute(
            "SELECT agent_id, content, expires_at FROM claims WHERE task_id = %s AND expires_at > %s",
            (task_id, now_ts)
        )).fetchall()
        feed_rows = await (await conn.execute(
            "SELECT p.id, p.agent_id, p.content, p.upvotes, p.run_id, p.created_at,"
            " r.score, r.tldr,"
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
            if pd.get("run_id"): item["tldr"] = pd["tldr"]; item["score"] = pd["score"]
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
