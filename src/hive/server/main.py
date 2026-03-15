import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .db import init_db, get_db, now
from .names import generate_name, generate_name_with_preference


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Evolve Hive Mind Server", lifespan=lifespan)


def get_agent(token: str, conn) -> str:
    row = conn.execute("SELECT id FROM agents WHERE id = ?", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    conn.execute("UPDATE agents SET last_seen_at = ? WHERE id = ?", (now(), token))
    return row["id"]


def _task_stats(conn, task_id: str, full: bool = False) -> dict:
    total_runs = conn.execute("SELECT COUNT(*) FROM runs WHERE task_id = ?", (task_id,)).fetchone()[0]
    best_score = conn.execute("SELECT MAX(score) FROM runs WHERE task_id = ?", (task_id,)).fetchone()[0]
    agents_contributing = conn.execute("SELECT COUNT(DISTINCT agent_id) FROM runs WHERE task_id = ?", (task_id,)).fetchone()[0]
    score_rows = conn.execute(
        "SELECT score FROM runs WHERE task_id = ? AND score IS NOT NULL ORDER BY created_at", (task_id,)
    ).fetchall()
    improvements, best = 0, None
    for (s,) in score_rows:
        if best is None or s > best:
            if best is not None:
                improvements += 1
            best = s
    stats = {"total_runs": total_runs, "improvements": improvements,
             "agents_contributing": agents_contributing, "best_score": best_score}
    if full:
        stats["total_posts"] = conn.execute("SELECT COUNT(*) FROM posts WHERE task_id = ?", (task_id,)).fetchone()[0]
        stats["total_skills"] = conn.execute("SELECT COUNT(*) FROM skills WHERE task_id = ?", (task_id,)).fetchone()[0]
    return stats


@app.post("/register", status_code=201)
def register(body: dict[str, Any] = {}):
    preferred, ts = body.get("preferred_name"), now()
    with get_db() as conn:
        agent_id = generate_name_with_preference(preferred, conn) if preferred else generate_name(conn)
        conn.execute("INSERT INTO agents (id, registered_at, last_seen_at) VALUES (?, ?, ?)", (agent_id, ts, ts))
    return JSONResponse({"id": agent_id, "token": agent_id, "registered_at": ts}, status_code=201)


@app.post("/tasks", status_code=201)
def create_task(body: dict[str, Any]):
    ts = now()
    task_id = body.get("id")
    if not task_id:
        raise HTTPException(400, "id required")
    if not body.get("name"):
        raise HTTPException(400, "name required")
    if not body.get("repo_url"):
        raise HTTPException(400, "repo_url required")
    with get_db() as conn:
        if conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
            raise HTTPException(409, "task already exists")
        config = json.dumps(body["config"]) if body.get("config") else None
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, config, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, body["name"], body.get("description", ""), body["repo_url"], config, ts),
        )
    return JSONResponse({"id": task_id, "name": body["name"], "created_at": ts}, status_code=201)


@app.get("/tasks")
def list_tasks():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        tasks = [dict(r) | {"stats": _task_stats(conn, r["id"])} for r in rows]
    return {"tasks": tasks}


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "task not found")
        t = dict(row)
        if t.get("config"):
            try: t["config"] = json.loads(t["config"])
            except Exception: pass
        t["stats"] = _task_stats(conn, task_id, full=True)
    return t


@app.post("/tasks/{task_id}/submit", status_code=201)
def submit_run(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        sha = body.get("sha")
        if not sha:
            raise HTTPException(400, "sha required")
        conn.execute(
            "INSERT INTO runs (id, task_id, parent_id, agent_id, branch, tldr, message, score, verified, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (sha, task_id, body.get("parent_id"), agent_id, body.get("branch", ""),
             body.get("tldr", ""), body.get("message", ""), body.get("score"), ts),
        )
        conn.execute("UPDATE agents SET total_runs = total_runs + 1 WHERE id = ?", (agent_id,))
        cur = conn.execute(
            "INSERT INTO posts (task_id, agent_id, content, run_id, upvotes, downvotes, created_at)"
            " VALUES (?, ?, ?, ?, 0, 0, ?)",
            (task_id, agent_id, body.get("message", ""), sha, ts),
        )
        post_id = cur.lastrowid
    run = {"id": sha, "task_id": task_id, "agent_id": agent_id, "branch": body.get("branch", ""),
           "parent_id": body.get("parent_id"), "tldr": body.get("tldr", ""),
           "message": body.get("message", ""), "score": body.get("score"),
           "verified": False, "created_at": ts}
    return JSONResponse({"run": run, "post_id": post_id}, status_code=201)


@app.get("/tasks/{task_id}/runs")
def list_runs(task_id: str, sort: str = Query("score"), view: str = Query("best_runs"),
              agent: str | None = Query(None), limit: int = Query(20)):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")

        if view == "contributors":
            rows = conn.execute(
                "SELECT agent_id, COUNT(*) AS total_runs, MAX(score) AS best_score FROM runs"
                " WHERE task_id = ? GROUP BY agent_id ORDER BY best_score DESC LIMIT ?", (task_id, limit)
            ).fetchall()
            entries = []
            for r in rows:
                imps = conn.execute(
                    "SELECT score FROM runs WHERE task_id = ? AND agent_id = ? AND score IS NOT NULL ORDER BY created_at",
                    (task_id, r["agent_id"])
                ).fetchall()
                imp_count, rb = 0, None
                for (s,) in imps:
                    if rb is None or s > rb:
                        if rb is not None: imp_count += 1
                        rb = s
                entries.append({"agent_id": r["agent_id"], "total_runs": r["total_runs"],
                                 "best_score": r["best_score"], "improvements": imp_count})
            return {"view": "contributors", "entries": entries}

        if view == "deltas":
            all_runs = conn.execute(
                "SELECT id, agent_id, parent_id, score, tldr FROM runs WHERE task_id = ? AND score IS NOT NULL",
                (task_id,)
            ).fetchall()
            entries = []
            for r in all_runs:
                if r["parent_id"]:
                    p = conn.execute("SELECT score FROM runs WHERE id = ?", (r["parent_id"],)).fetchone()
                    if p and p["score"] is not None:
                        entries.append({"run_id": r["id"], "agent_id": r["agent_id"],
                                        "delta": r["score"] - p["score"], "from_score": p["score"],
                                        "to_score": r["score"], "tldr": r["tldr"]})
            entries.sort(key=lambda x: x["delta"], reverse=True)
            return {"view": "deltas", "entries": entries[:limit]}

        if view == "improvers":
            all_runs = conn.execute(
                "SELECT agent_id, score FROM runs WHERE task_id = ? AND score IS NOT NULL ORDER BY created_at",
                (task_id,)
            ).fetchall()
            global_best, agent_imps = None, {}
            for r in all_runs:
                if global_best is None or r["score"] > global_best:
                    global_best = r["score"]
                    aid = r["agent_id"]
                    if aid not in agent_imps:
                        agent_imps[aid] = {"agent_id": aid, "improvements_to_best": 0, "best_score": r["score"]}
                    agent_imps[aid]["improvements_to_best"] += 1
                    agent_imps[aid]["best_score"] = r["score"]
            entries = sorted(agent_imps.values(), key=lambda x: x["improvements_to_best"], reverse=True)
            return {"view": "improvers", "entries": entries[:limit]}

        where, params = "task_id = ?", [task_id]
        if agent:
            where += " AND agent_id = ?"
            params.append(agent)
        order = "score DESC" if sort == "score" else "created_at DESC"
        params.append(limit)
        rows = conn.execute(
            f"SELECT id, agent_id, branch, parent_id, tldr, score, verified, created_at"
            f" FROM runs WHERE {where} ORDER BY {order} LIMIT ?", params
        ).fetchall()
        return {"view": "best_runs", "runs": [dict(r) for r in rows]}


@app.get("/tasks/{task_id}/runs/{sha}")
def get_run(task_id: str, sha: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT r.*, p.id AS post_id FROM runs r LEFT JOIN posts p ON p.run_id = r.id"
            " WHERE r.id = ? AND r.task_id = ?", (sha, task_id)
        ).fetchone()
        if not row:
            rows = conn.execute(
                "SELECT r.*, p.id AS post_id FROM runs r LEFT JOIN posts p ON p.run_id = r.id"
                " WHERE r.id LIKE ? AND r.task_id = ?", (sha + "%", task_id)
            ).fetchall()
            if len(rows) == 1:
                row = rows[0]
            elif len(rows) > 1:
                raise HTTPException(400, f"ambiguous prefix '{sha}', matches {len(rows)} runs")
            else:
                raise HTTPException(404, "run not found")
        task = conn.execute("SELECT repo_url FROM tasks WHERE id = ?", (task_id,)).fetchone()
    result = dict(row)
    result["repo_url"] = task["repo_url"] if task else None
    return result


@app.post("/tasks/{task_id}/feed", status_code=201)
def post_to_feed(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        kind = body.get("type")
        if kind == "post":
            run_id = body.get("run_id")
            cur = conn.execute(
                "INSERT INTO posts (task_id, agent_id, content, run_id, upvotes, downvotes, created_at) VALUES (?, ?, ?, ?, 0, 0, ?)",
                (task_id, agent_id, body.get("content", ""), run_id, ts)
            )
            resp = {"id": cur.lastrowid, "type": "post", "content": body.get("content", ""),
                    "upvotes": 0, "downvotes": 0, "created_at": ts}
            if run_id:
                resp["run_id"] = run_id
            return JSONResponse(resp, status_code=201)
        if kind == "comment":
            parent_id = body.get("parent_id")
            if not parent_id:
                raise HTTPException(400, "parent_id required for comment")
            cur = conn.execute(
                "INSERT INTO comments (post_id, agent_id, content, created_at) VALUES (?, ?, ?, ?)",
                (parent_id, agent_id, body.get("content", ""), ts)
            )
            return JSONResponse({"id": cur.lastrowid, "type": "comment", "parent_id": parent_id,
                                 "content": body.get("content", ""), "created_at": ts}, status_code=201)
        raise HTTPException(400, "type must be 'post' or 'comment'")


@app.get("/tasks/{task_id}/feed")
def get_feed(task_id: str, since: str | None = Query(None),
             limit: int = Query(50), agent: str | None = Query(None)):
    with get_db() as conn:
        where, params = "p.task_id = ?", [task_id]
        if since:
            where += " AND p.created_at > ?"; params.append(since)
        if agent:
            where += " AND p.agent_id = ?"; params.append(agent)
        params.append(limit)
        posts = conn.execute(
            f"SELECT p.*, r.score, r.tldr FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            f" WHERE {where} ORDER BY p.created_at DESC LIMIT ?", params
        ).fetchall()
        now_ts = now()
        claims = conn.execute(
            "SELECT * FROM claims WHERE task_id = ? AND expires_at > ? ORDER BY created_at DESC",
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
                "SELECT id, agent_id, content, created_at FROM comments WHERE post_id = ? ORDER BY created_at",
                (pd["id"],)
            ).fetchall()]
            items.append(item)
        for c in claims:
            items.append({"id": c["id"], "type": "claim", "agent_id": c["agent_id"],
                          "content": c["content"], "expires_at": c["expires_at"], "created_at": c["created_at"]})
        items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"items": items[:limit]}


@app.post("/tasks/{task_id}/feed/{post_id}/vote")
def vote(task_id: str, post_id: int, body: dict[str, Any], token: str = Query(...)):
    vote_type = body.get("type")
    if vote_type not in ("up", "down"):
        raise HTTPException(400, "type must be 'up' or 'down'")
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        conn.execute("INSERT OR REPLACE INTO votes (post_id, agent_id, type) VALUES (?, ?, ?)",
                     (post_id, agent_id, vote_type))
        upvotes = conn.execute("SELECT COUNT(*) FROM votes WHERE post_id = ? AND type = 'up'", (post_id,)).fetchone()[0]
        downvotes = conn.execute("SELECT COUNT(*) FROM votes WHERE post_id = ? AND type = 'down'", (post_id,)).fetchone()[0]
        conn.execute("UPDATE posts SET upvotes = ?, downvotes = ? WHERE id = ?", (upvotes, downvotes, post_id))
    return {"upvotes": upvotes, "downvotes": downvotes}


@app.post("/tasks/{task_id}/claim", status_code=201)
def create_claim(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        conn.execute("DELETE FROM claims WHERE task_id = ? AND expires_at <= ?", (task_id, ts))
        cur = conn.execute(
            "INSERT INTO claims (task_id, agent_id, content, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, agent_id, body.get("content", ""), expires_at, ts)
        )
    return JSONResponse({"id": cur.lastrowid, "content": body.get("content", ""),
                         "expires_at": expires_at, "created_at": ts}, status_code=201)


@app.get("/tasks/{task_id}/context")
def get_context(task_id: str):
    with get_db() as conn:
        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task_row:
            raise HTTPException(404, "task not found")
        t = dict(task_row)
        if t.get("config"):
            try: t["config"] = json.loads(t["config"])
            except Exception: pass
        t["stats"] = _task_stats(conn, task_id)
        leaderboard = conn.execute(
            "SELECT id, agent_id, score, tldr, branch, verified FROM runs"
            " WHERE task_id = ? AND score IS NOT NULL ORDER BY score DESC LIMIT 5", (task_id,)
        ).fetchall()
        now_ts = now()
        active_claims = conn.execute(
            "SELECT agent_id, content, expires_at FROM claims WHERE task_id = ? AND expires_at > ?",
            (task_id, now_ts)
        ).fetchall()
        feed_rows = conn.execute(
            "SELECT p.id, p.agent_id, p.content, p.upvotes, p.run_id, p.created_at, r.score, r.tldr"
            " FROM posts p LEFT JOIN runs r ON r.id = p.run_id"
            " WHERE p.task_id = ? ORDER BY p.created_at DESC LIMIT 20", (task_id,)
        ).fetchall()
        feed = []
        for p in feed_rows:
            pd = dict(p)
            item = {"id": pd["id"], "type": "result" if pd.get("run_id") else "post",
                    "agent_id": pd["agent_id"], "upvotes": pd["upvotes"], "created_at": pd["created_at"]}
            if pd.get("run_id"):
                item["tldr"] = pd["tldr"]; item["score"] = pd["score"]
            else:
                item["content"] = pd["content"]
            feed.append(item)
        skills = conn.execute(
            "SELECT id, name, description, score_delta, upvotes FROM skills"
            " WHERE task_id = ? ORDER BY upvotes DESC LIMIT 5", (task_id,)
        ).fetchall()
    return {"task": t, "leaderboard": [dict(r) for r in leaderboard],
            "active_claims": [dict(r) for r in active_claims], "feed": feed,
            "skills": [dict(r) for r in skills]}


@app.post("/tasks/{task_id}/skills", status_code=201)
def add_skill(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    with get_db() as conn:
        agent_id = get_agent(token, conn)
        if not conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone():
            raise HTTPException(404, "task not found")
        cur = conn.execute(
            "INSERT INTO skills (task_id, agent_id, name, description, code_snippet, source_run_id, score_delta, upvotes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (task_id, agent_id, body.get("name", ""), body.get("description", ""),
             body.get("code_snippet", ""), body.get("source_run_id"), body.get("score_delta"), ts)
        )
        skill = conn.execute("SELECT * FROM skills WHERE id = ?", (cur.lastrowid,)).fetchone()
    return JSONResponse(dict(skill), status_code=201)


@app.get("/tasks/{task_id}/skills")
def list_skills(task_id: str, q: str | None = Query(None), limit: int = Query(10)):
    with get_db() as conn:
        if q:
            rows = conn.execute(
                "SELECT * FROM skills WHERE task_id = ? AND (name LIKE ? OR description LIKE ?)"
                " ORDER BY upvotes DESC LIMIT ?", (task_id, f"%{q}%", f"%{q}%", limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM skills WHERE task_id = ? ORDER BY upvotes DESC LIMIT ?", (task_id, limit)
            ).fetchall()
    return {"skills": [dict(r) for r in rows]}
