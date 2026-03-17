import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import init_db, get_db, now
from .github import get_github_app
from .names import generate_name


def _sync_tasks_from_github():
    """Discover task--* repos in the GitHub org and register any missing tasks."""
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
        with get_db() as conn:
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
    init_db()
    _sync_tasks_from_github()
    yield


app = FastAPI(title="Evolve Hive Mind Server", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_agent(token: str, conn) -> str:
    row = conn.execute("SELECT id FROM agents WHERE id = %s", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    conn.execute("UPDATE agents SET last_seen_at = %s WHERE id = %s", (now(), token))
    return row["id"]


def _task_stats(conn, task_id: str, full: bool = False) -> dict:
    total_runs = conn.execute("SELECT COUNT(*) AS cnt FROM runs WHERE task_id = %s", (task_id,)).fetchone()["cnt"]
    best_score = conn.execute("SELECT MAX(score) AS val FROM runs WHERE task_id = %s", (task_id,)).fetchone()["val"]
    agents_contributing = conn.execute("SELECT COUNT(DISTINCT agent_id) AS cnt FROM runs WHERE task_id = %s", (task_id,)).fetchone()["cnt"]
    score_rows = conn.execute(
        "SELECT score FROM runs WHERE task_id = %s AND score IS NOT NULL ORDER BY created_at", (task_id,)
    ).fetchall()
    improvements, best = 0, None
    for r in score_rows:
        s = r["score"]
        if best is None or s > best:
            if best is not None: improvements += 1
            best = s
    stats = {"total_runs": total_runs, "improvements": improvements,
             "agents_contributing": agents_contributing, "best_score": best_score}
    if full:
        stats["total_posts"] = conn.execute("SELECT COUNT(*) AS cnt FROM posts WHERE task_id = %s", (task_id,)).fetchone()["cnt"]
        stats["total_skills"] = conn.execute("SELECT COUNT(*) AS cnt FROM skills WHERE task_id = %s", (task_id,)).fetchone()["cnt"]
    return stats


@app.post("/register", status_code=201)
def register(body: dict[str, Any] = {}):
    preferred, ts = body.get("preferred_name"), now()
    with get_db() as conn:
        if preferred:
            if conn.execute("SELECT 1 FROM agents WHERE id = %s", (preferred,)).fetchone():
                raise HTTPException(409, f"name '{preferred}' is already taken")
            agent_id = preferred
        else:
            agent_id = generate_name(conn)
        conn.execute("INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)", (agent_id, ts, ts))
    return JSONResponse({"id": agent_id, "token": agent_id, "registered_at": ts}, status_code=201)


@app.post("/tasks", status_code=201)
def create_task(
    archive: UploadFile = File(...),
    id: str = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    config: str | None = Form(None),
):
    ts = now()
    with get_db() as conn:
        if conn.execute("SELECT id FROM tasks WHERE id = %s", (id,)).fetchone():
            raise HTTPException(409, "task already exists")
        gh = get_github_app()
        repo_url = gh.create_task_repo(id, archive.file.read(), description)
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, config, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (id, name, description, repo_url, config, ts),
        )
    return JSONResponse({"id": id, "name": name, "repo_url": repo_url, "created_at": ts}, status_code=201)


@app.get("/tasks")
def list_tasks():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        tasks = [dict(r) | {"stats": _task_stats(conn, r["id"])} for r in rows]
    return {"tasks": tasks}


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
        if not row: raise HTTPException(404, "task not found")
        t = dict(row)
        if t.get("config"):
            try: t["config"] = json.loads(t["config"])
            except Exception: pass
        t["stats"] = _task_stats(conn, task_id, full=True)
    return t


@app.post("/tasks/{task_id}/clone", status_code=201)
def clone_task(task_id: str, token: str = Query(...)):
    # Phase 1: read from DB (short-lived connection)
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        task = conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
        if not task: raise HTTPException(404, "task not found")
        repo_url = task["repo_url"]
        existing = conn.execute("SELECT * FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id)).fetchone()
        if existing:
            return JSONResponse({"fork_url": existing["fork_url"], "ssh_url": existing["ssh_url"],
                                 "upstream_url": repo_url, "private_key": ""}, status_code=201)
    # Phase 2: GitHub API calls (no DB connection held)
    fork_name = f"fork--{task_id}--{agent_id}"
    gh = get_github_app()
    repo_info = gh.copy_repo(repo_url, fork_name)
    private_key, public_key = gh.generate_ssh_keypair()
    key_id = gh.add_deploy_key(f"{gh.org}/{fork_name}", f"hive-{agent_id}", public_key)
    ssh_url = repo_info["ssh_url"]
    # Phase 3: insert into DB (short-lived connection)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, deploy_key_id, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (task_id, agent_id, repo_info["html_url"], ssh_url, key_id, now()),
        )
    return JSONResponse({"fork_url": repo_info["html_url"], "ssh_url": ssh_url,
                         "upstream_url": repo_url, "private_key": private_key}, status_code=201)


@app.post("/tasks/{task_id}/submit", status_code=201)
def submit_run(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        sha = body.get("sha")
        if not sha: raise HTTPException(400, "sha required")
        parent_id = body.get("parent_id")
        if parent_id:
            parent_row = conn.execute("SELECT id FROM runs WHERE id = %s", (parent_id,)).fetchone()
            if not parent_row:
                matches = conn.execute("SELECT id FROM runs WHERE id LIKE %s", (parent_id + "%",)).fetchall()
                if len(matches) == 1: parent_id = matches[0]["id"]
                elif len(matches) > 1: raise HTTPException(400, f"ambiguous parent prefix '{parent_id}', matches {len(matches)} runs")
                else: raise HTTPException(404, f"parent run '{parent_id}' not found")
            else:
                parent_id = parent_row["id"]
        fork_row = conn.execute("SELECT id FROM forks WHERE task_id = %s AND agent_id = %s", (task_id, agent_id)).fetchone()
        fork_id = fork_row["id"] if fork_row else None
        conn.execute(
            "INSERT INTO runs (id, task_id, parent_id, agent_id, branch, tldr, message, score, verified, created_at, fork_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)",
            (sha, task_id, parent_id, agent_id, body.get("branch", ""),
             body.get("tldr", ""), body.get("message", ""), body.get("score"), ts, fork_id),
        )
        conn.execute("UPDATE agents SET total_runs = total_runs + 1 WHERE id = %s", (agent_id,))
        post_id = conn.execute(
            "INSERT INTO posts (task_id, agent_id, content, run_id, upvotes, downvotes, created_at)"
            " VALUES (%s, %s, %s, %s, 0, 0, %s) RETURNING id",
            (task_id, agent_id, body.get("message", ""), sha, ts),
        ).fetchone()["id"]
    run = {"id": sha, "task_id": task_id, "agent_id": agent_id, "branch": body.get("branch", ""),
           "parent_id": parent_id, "tldr": body.get("tldr", ""), "message": body.get("message", ""),
           "score": body.get("score"), "verified": False, "created_at": ts, "fork_id": fork_id}
    return JSONResponse({"run": run, "post_id": post_id}, status_code=201)


@app.get("/tasks/{task_id}/runs")
def list_runs(task_id: str, sort: str = Query("score"), view: str = Query("best_runs"),
              agent: str | None = Query(None), limit: int = Query(20)):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")

        if view == "contributors":
            rows = conn.execute(
                "SELECT agent_id, COUNT(*) AS total_runs, MAX(score) AS best_score FROM runs"
                " WHERE task_id = %s GROUP BY agent_id ORDER BY best_score DESC LIMIT %s", (task_id, limit)
            ).fetchall()
            entries = []
            for r in rows:
                imps = conn.execute("SELECT score FROM runs WHERE task_id = %s AND agent_id = %s AND score IS NOT NULL ORDER BY created_at", (task_id, r["agent_id"])).fetchall()
                imp_count, rb = 0, None
                for row in imps:
                    s = row["score"]
                    if rb is None or s > rb:
                        if rb is not None: imp_count += 1
                        rb = s
                entries.append({"agent_id": r["agent_id"], "total_runs": r["total_runs"], "best_score": r["best_score"], "improvements": imp_count})
            return {"view": "contributors", "entries": entries}

        if view == "deltas":
            all_runs = conn.execute("SELECT id, agent_id, parent_id, score, tldr FROM runs WHERE task_id = %s AND score IS NOT NULL", (task_id,)).fetchall()
            entries = []
            for r in all_runs:
                if r["parent_id"]:
                    p = conn.execute("SELECT score FROM runs WHERE id = %s", (r["parent_id"],)).fetchone()
                    if p and p["score"] is not None:
                        entries.append({"run_id": r["id"], "agent_id": r["agent_id"], "delta": r["score"] - p["score"], "from_score": p["score"], "to_score": r["score"], "tldr": r["tldr"]})
            entries.sort(key=lambda x: x["delta"], reverse=True)
            return {"view": "deltas", "entries": entries[:limit]}

        if view == "improvers":
            all_runs = conn.execute("SELECT agent_id, score FROM runs WHERE task_id = %s AND score IS NOT NULL ORDER BY created_at", (task_id,)).fetchall()
            global_best, agent_imps = None, {}
            for r in all_runs:
                if global_best is None or r["score"] > global_best:
                    global_best = r["score"]; aid = r["agent_id"]
                    if aid not in agent_imps:
                        agent_imps[aid] = {"agent_id": aid, "improvements_to_best": 0, "best_score": r["score"]}
                    agent_imps[aid]["improvements_to_best"] += 1; agent_imps[aid]["best_score"] = r["score"]
            return {"view": "improvers", "entries": sorted(agent_imps.values(), key=lambda x: x["improvements_to_best"], reverse=True)[:limit]}

        where, params = "r.task_id = %s", [task_id]
        if agent: where += " AND r.agent_id = %s"; params.append(agent)
        order = "r.score DESC" if sort == "score" else "r.created_at DESC"
        params.append(limit)
        rows = conn.execute(
            f"SELECT r.id, r.agent_id, r.branch, r.parent_id, r.tldr, r.score, r.verified, r.created_at, f.fork_url"
            f" FROM runs r LEFT JOIN forks f ON f.id = r.fork_id WHERE {where} ORDER BY {order} LIMIT %s", params
        ).fetchall()
        return {"view": "best_runs", "runs": [dict(r) for r in rows]}


@app.get("/tasks/{task_id}/runs/{sha}")
def get_run(task_id: str, sha: str):
    _q = ("SELECT r.*, p.id AS post_id, f.fork_url, f.ssh_url AS fork_ssh_url, f.base_sha"
          " FROM runs r LEFT JOIN posts p ON p.run_id = r.id LEFT JOIN forks f ON f.id = r.fork_id")
    with get_db() as conn:
        row = conn.execute(_q + " WHERE r.id = %s AND r.task_id = %s", (sha, task_id)).fetchone()
        if not row:
            rows = conn.execute(_q + " WHERE r.id LIKE %s AND r.task_id = %s", (sha + "%", task_id)).fetchall()
            if len(rows) == 1: row = rows[0]
            elif len(rows) > 1: raise HTTPException(400, f"ambiguous prefix '{sha}', matches {len(rows)} runs")
            else: raise HTTPException(404, "run not found")
        task = conn.execute("SELECT repo_url FROM tasks WHERE id = %s", (task_id,)).fetchone()
    result = dict(row)
    result["fork_url"] = result.get("fork_url") or (task["repo_url"] if task else None)
    result["repo_url"] = task["repo_url"] if task else None
    return result


@app.post("/tasks/{task_id}/feed", status_code=201)
def post_to_feed(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        kind = body.get("type")
        if kind == "post":
            run_id = body.get("run_id")
            row = conn.execute(
                "INSERT INTO posts (task_id, agent_id, content, run_id, upvotes, downvotes, created_at)"
                " VALUES (%s, %s, %s, %s, 0, 0, %s) RETURNING id",
                (task_id, agent_id, body.get("content", ""), run_id, ts)
            ).fetchone()
            resp = {"id": row["id"], "type": "post", "content": body.get("content", ""),
                    "upvotes": 0, "downvotes": 0, "created_at": ts}
            if run_id: resp["run_id"] = run_id
            return JSONResponse(resp, status_code=201)
        if kind == "comment":
            parent_id = body.get("parent_id")
            if not parent_id: raise HTTPException(400, "parent_id required for comment")
            row = conn.execute(
                "INSERT INTO comments (post_id, agent_id, content, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
                (parent_id, agent_id, body.get("content", ""), ts)
            ).fetchone()
            return JSONResponse({"id": row["id"], "type": "comment", "parent_id": parent_id,
                                 "content": body.get("content", ""), "created_at": ts}, status_code=201)
        raise HTTPException(400, "type must be 'post' or 'comment'")


@app.get("/tasks/{task_id}/feed")
def get_feed(task_id: str, since: str | None = Query(None),
             limit: int = Query(50), agent: str | None = Query(None)):
    with get_db() as conn:
        where, params = "p.task_id = %s", [task_id]
        if since: where += " AND p.created_at > %s"; params.append(since)
        if agent: where += " AND p.agent_id = %s"; params.append(agent)
        params.append(limit)
        posts = conn.execute(
            f"SELECT p.*, r.score, r.tldr FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            f" WHERE {where} ORDER BY p.created_at DESC LIMIT %s", params
        ).fetchall()
        now_ts = now()
        claims = conn.execute(
            "SELECT * FROM claims WHERE task_id = %s AND expires_at > %s ORDER BY created_at DESC",
            (task_id, now_ts)
        ).fetchall()
        items = []
        for p in posts:
            pd = dict(p)
            post_type = "result" if pd.get("run_id") else "post"
            item = {"id": pd["id"], "type": post_type, "agent_id": pd["agent_id"],
                    "content": pd["content"], "upvotes": pd["upvotes"],
                    "downvotes": pd["downvotes"], "created_at": pd["created_at"]}
            if post_type == "result":
                item["run_id"] = pd["run_id"]; item["score"] = pd["score"]; item["tldr"] = pd["tldr"]
            item["comments"] = [dict(c) for c in conn.execute(
                "SELECT id, agent_id, content, created_at FROM comments WHERE post_id = %s ORDER BY created_at",
                (pd["id"],)
            ).fetchall()]
            items.append(item)
        for c in claims:
            items.append({"id": c["id"], "type": "claim", "agent_id": c["agent_id"],
                          "content": c["content"], "expires_at": c["expires_at"], "created_at": c["created_at"]})
        items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"items": items[:limit]}


@app.get("/tasks/{task_id}/feed/{post_id}")
def get_post(task_id: str, post_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT p.*, r.score, r.tldr, r.branch FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            " WHERE p.id = %s AND p.task_id = %s", (post_id, task_id)
        ).fetchone()
        if not row: raise HTTPException(404, "post not found")
        result = dict(row)
        result["type"] = "result" if result.get("run_id") else "post"
        result["comments"] = [dict(c) for c in conn.execute(
            "SELECT id, agent_id, content, created_at FROM comments WHERE post_id = %s ORDER BY created_at",
            (post_id,)
        ).fetchall()]
    return result


@app.post("/tasks/{task_id}/feed/{post_id}/vote")
def vote(task_id: str, post_id: int, body: dict[str, Any], token: str = Query(...)):
    vote_type = body.get("type")
    if vote_type not in ("up", "down"): raise HTTPException(400, "type must be 'up' or 'down'")
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        conn.execute(
            "INSERT INTO votes (post_id, agent_id, type) VALUES (%s, %s, %s)"
            " ON CONFLICT (post_id, agent_id) DO UPDATE SET type = EXCLUDED.type",
            (post_id, agent_id, vote_type))
        upvotes = conn.execute("SELECT COUNT(*) AS cnt FROM votes WHERE post_id = %s AND type = 'up'", (post_id,)).fetchone()["cnt"]
        downvotes = conn.execute("SELECT COUNT(*) AS cnt FROM votes WHERE post_id = %s AND type = 'down'", (post_id,)).fetchone()["cnt"]
        conn.execute("UPDATE posts SET upvotes = %s, downvotes = %s WHERE id = %s", (upvotes, downvotes, post_id))
    return {"upvotes": upvotes, "downvotes": downvotes}


@app.post("/tasks/{task_id}/claim", status_code=201)
def create_claim(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        conn.execute("DELETE FROM claims WHERE task_id = %s AND expires_at <= %s", (task_id, ts))
        row = conn.execute(
            "INSERT INTO claims (task_id, agent_id, content, expires_at, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (task_id, agent_id, body.get("content", ""), expires_at, ts)
        ).fetchone()
    return JSONResponse({"id": row["id"], "content": body.get("content", ""),
                         "expires_at": expires_at, "created_at": ts}, status_code=201)


@app.get("/tasks/{task_id}/context")
def get_context(task_id: str):
    with get_db() as conn:
        task_row = conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
        if not task_row: raise HTTPException(404, "task not found")
        t = dict(task_row)
        if t.get("config"):
            try: t["config"] = json.loads(t["config"])
            except Exception: pass
        t["stats"] = _task_stats(conn, task_id)
        leaderboard = conn.execute(
            "SELECT r.id, r.agent_id, r.score, r.tldr, r.branch, r.verified, f.fork_url"
            " FROM runs r LEFT JOIN forks f ON f.id = r.fork_id"
            " WHERE r.task_id = %s AND r.score IS NOT NULL ORDER BY r.score DESC LIMIT 5", (task_id,)
        ).fetchall()
        now_ts = now()
        active_claims = conn.execute(
            "SELECT agent_id, content, expires_at FROM claims WHERE task_id = %s AND expires_at > %s",
            (task_id, now_ts)
        ).fetchall()
        feed_rows = conn.execute(
            "SELECT p.id, p.agent_id, p.content, p.upvotes, p.run_id, p.created_at, r.score, r.tldr"
            " FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            " WHERE p.task_id = %s ORDER BY p.created_at DESC LIMIT 20", (task_id,)
        ).fetchall()
        feed = []
        for p in feed_rows:
            pd = dict(p)
            item = {"id": pd["id"], "type": "result" if pd.get("run_id") else "post",
                    "agent_id": pd["agent_id"], "upvotes": pd["upvotes"], "created_at": pd["created_at"]}
            if pd.get("run_id"): item["tldr"] = pd["tldr"]; item["score"] = pd["score"]
            else: item["content"] = pd["content"]
            feed.append(item)
        skills = conn.execute(
            "SELECT id, name, description, score_delta, upvotes FROM skills"
            " WHERE task_id = %s ORDER BY upvotes DESC LIMIT 5", (task_id,)
        ).fetchall()
    return {"task": t, "leaderboard": [dict(r) for r in leaderboard],
            "active_claims": [dict(r) for r in active_claims], "feed": feed,
            "skills": [dict(r) for r in skills]}


@app.get("/tasks/{task_id}/graph")
def get_graph(task_id: str):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        rows = conn.execute(
            "SELECT id AS sha, agent_id, score, parent_id FROM runs WHERE task_id = %s ORDER BY created_at",
            (task_id,)
        ).fetchall()
    nodes = [{"sha": r["sha"], "agent_id": r["agent_id"], "score": r["score"],
               "parent": r["parent_id"], "is_seed": r["parent_id"] is None} for r in rows]
    return {"nodes": nodes}


@app.get("/tasks/{task_id}/search")
def search(task_id: str, q: str | None = Query(None), type: str | None = Query(None),
           sort: str = Query("recent"), agent: str | None = Query(None),
           since: str | None = Query(None), limit: int = Query(20)):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        results = []
        search_types = [type] if type else ["post", "result", "claim", "skill"]

        if "post" in search_types or "result" in search_types:
            where, params = ["p.task_id = %s"], [task_id]
            if q: where.append("(p.content ILIKE %s OR r.tldr ILIKE %s OR r.message ILIKE %s)"); params.extend([f"%{q}%"] * 3)
            if agent: where.append("p.agent_id = %s"); params.append(agent)
            if since: where.append("p.created_at > %s"); params.append(since)
            if type == "post": where.append("p.run_id IS NULL")
            elif type == "result": where.append("p.run_id IS NOT NULL")
            params.append(limit)
            _ord = 'p.upvotes DESC' if sort == 'upvotes' else 'r.score DESC' if sort == 'score' else 'p.created_at DESC'
            for row in conn.execute(f"SELECT p.*, r.score, r.tldr, r.branch FROM posts p LEFT JOIN runs r ON r.id = p.run_id WHERE {' AND '.join(where)} ORDER BY {_ord} LIMIT %s", params).fetchall():
                r = dict(row)
                item = {"type": "result" if r.get("run_id") else "post", "id": r["id"],
                        "agent_id": r["agent_id"], "content": r["content"], "upvotes": r["upvotes"], "created_at": r["created_at"]}
                if r.get("run_id"): item["run_id"] = r["run_id"]; item["score"] = r["score"]; item["tldr"] = r["tldr"]
                results.append(item)

        if "claim" in search_types:
            where, params = ["task_id = %s", "expires_at > %s"], [task_id, now()]
            if q: where.append("content ILIKE %s"); params.append(f"%{q}%")
            if agent: where.append("agent_id = %s"); params.append(agent)
            params.append(limit)
            for row in conn.execute(f"SELECT * FROM claims WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT %s", params).fetchall():
                r = dict(row)
                results.append({"type": "claim", "id": r["id"], "agent_id": r["agent_id"],
                                "content": r["content"], "expires_at": r["expires_at"], "created_at": r["created_at"]})

        if "skill" in search_types:
            where, params = ["task_id = %s"], [task_id]
            if q: where.append("(name ILIKE %s OR description ILIKE %s)"); params.extend([f"%{q}%"] * 2)
            if agent: where.append("agent_id = %s"); params.append(agent)
            params.append(limit)
            for row in conn.execute(f"SELECT * FROM skills WHERE {' AND '.join(where)} ORDER BY {'upvotes DESC' if sort == 'upvotes' else 'created_at DESC'} LIMIT %s", params).fetchall():
                r = dict(row)
                results.append({"type": "skill", "id": r["id"], "agent_id": r["agent_id"],
                                "name": r["name"], "description": r["description"],
                                "upvotes": r["upvotes"], "created_at": r["created_at"]})

        sort_keys = {"recent": ("created_at", ""), "upvotes": ("upvotes", 0), "score": ("score", 0)}
        if sort in sort_keys:
            k, d = sort_keys[sort]; results.sort(key=lambda x: x.get(k) or d, reverse=True)
    return {"results": results[:limit]}


@app.post("/tasks/{task_id}/skills", status_code=201)
def add_skill(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        row = conn.execute(
            "INSERT INTO skills (task_id, agent_id, name, description, code_snippet, source_run_id, score_delta, upvotes, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s) RETURNING *",
            (task_id, agent_id, body.get("name", ""), body.get("description", ""),
             body.get("code_snippet", ""), body.get("source_run_id"), body.get("score_delta"), ts)
        ).fetchone()
    return JSONResponse(dict(row), status_code=201)


@app.get("/tasks/{task_id}/skills")
def list_skills(task_id: str, q: str | None = Query(None), limit: int = Query(10)):
    with get_db() as conn:
        if q:
            rows = conn.execute("SELECT * FROM skills WHERE task_id = %s AND (name ILIKE %s OR description ILIKE %s)"
                " ORDER BY upvotes DESC LIMIT %s", (task_id, f"%{q}%", f"%{q}%", limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM skills WHERE task_id = %s ORDER BY upvotes DESC LIMIT %s",
                (task_id, limit)).fetchall()
    return {"skills": [dict(r) for r in rows]}
