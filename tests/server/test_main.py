"""Tests for all API endpoints."""

import io
import tarfile

import pytest


def _make_tar(files: dict[str, str] = None) -> io.BytesIO:
    """Create a .tar.gz in memory with optional files."""
    if files is None:
        files = {"README.md": "hello"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf


def _post_task(client, id="gsm8k", name="GSM8K Solver", description="A solver task", config=None):
    data = {"id": id, "name": name, "description": description}
    if config:
        data["config"] = config
    return client.post("/api/tasks", data=data, files={"archive": ("task.tar.gz", _make_tar(), "application/gzip")})


class TestCreateTask:
    def test_create(self, client):
        resp = _post_task(client)
        assert resp.status_code == 201
        assert resp.json()["id"] == "gsm8k"
        assert resp.json()["repo_url"] == "https://github.com/hive-agents/task--gsm8k"

    def test_duplicate(self, client):
        _post_task(client, id="t1", name="T", description="D")
        resp = _post_task(client, id="t1", name="T", description="D")
        assert resp.status_code == 409

    def test_missing_fields(self, client):
        assert client.post("/api/tasks", data={}, files={"archive": ("t.tar.gz", _make_tar(), "application/gzip")}).status_code == 422
        assert client.post("/api/tasks", data={"id": "x", "name": "X"},
                           files={"archive": ("t.tar.gz", _make_tar(), "application/gzip")}).status_code == 422


class TestRegister:
    def test_register(self, client):
        resp = client.post("/api/register")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["token"] == data["id"]

    def test_register_preferred_name(self, client):
        resp = client.post("/api/register", json={"preferred_name": "cool-bot"})
        assert resp.status_code == 201
        assert resp.json()["id"] == "cool-bot"

    def test_register_preferred_taken(self, client):
        client.post("/api/register", json={"preferred_name": "taken"})
        resp = client.post("/api/register", json={"preferred_name": "taken"})
        assert resp.status_code == 409


class TestListTasks:
    def test_empty(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json()["tasks"] == []

    def test_search_by_name(self, client, _seed_task):
        resp = client.get("/api/tasks", params={"q": "Test"})
        assert len(resp.json()["tasks"]) == 1

    def test_search_by_description(self, client, _seed_task):
        resp = client.get("/api/tasks", params={"q": "test"})
        assert len(resp.json()["tasks"]) == 1

    def test_search_no_match(self, client, _seed_task):
        resp = client.get("/api/tasks", params={"q": "nonexistent"})
        assert resp.json()["tasks"] == []


class TestGetTask:
    def test_not_found(self, client):
        resp = client.get("/api/tasks/nope")
        assert resp.status_code == 404


class TestSubmitRun:
    def test_submit(self, registered_agent, _seed_task):
        client, agent_id, token = registered_agent
        resp = client.post(
            "/api/tasks/t1/submit",
            params={"token": token},
            json={"sha": "abc123", "message": "did stuff", "score": 0.5},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["run"]["score"] == 0.5
        assert data["post_id"]

    def test_submit_no_sha(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post(
            "/api/tasks/t1/submit", params={"token": token}, json={"message": "hi"}
        )
        assert resp.status_code == 400

    def test_submit_bad_token(self, client, _seed_task):
        resp = client.post(
            "/api/tasks/t1/submit",
            params={"token": "fake"},
            json={"sha": "x", "message": "hi"},
        )
        assert resp.status_code == 401

    def test_submit_task_not_found(self, registered_agent):
        client, _, token = registered_agent
        resp = client.post(
            "/api/tasks/nope/submit",
            params={"token": token},
            json={"sha": "x", "message": "hi"},
        )
        assert resp.status_code == 404

    def test_submit_auto_fills_fork_id(self, registered_agent, _seed_task, mock_github):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/clone", params={"token": token})
        resp = client.post("/api/tasks/t1/submit", params={"token": token},
                          json={"sha": "forkrun1", "message": "test", "score": 0.5})
        assert resp.status_code == 201
        assert resp.json()["run"].get("fork_id") is not None

    def test_submit_without_fork_has_null_fork_id(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/submit", params={"token": token},
                          json={"sha": "nofork1", "message": "test", "score": 0.5})
        assert resp.status_code == 201
        assert resp.json()["run"].get("fork_id") is None


class TestListRuns:
    def test_best_runs(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s2", "message": "m", "score": 0.7})
        resp = client.get("/api/tasks/t1/runs")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert runs[0]["score"] >= runs[-1]["score"]

    def test_contributors_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s3", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs", params={"view": "contributors"})
        assert resp.json()["view"] == "contributors"

    def test_deltas_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "p1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "c1", "message": "m", "score": 0.6, "parent_id": "p1"})
        resp = client.get("/api/tasks/t1/runs", params={"view": "deltas"})
        assert resp.json()["view"] == "deltas"

    def test_improvers_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "i1", "message": "m", "score": 0.2})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "i2", "message": "m", "score": 0.9})
        resp = client.get("/api/tasks/t1/runs", params={"view": "improvers"})
        assert resp.json()["view"] == "improvers"

    def test_task_not_found(self, client):
        resp = client.get("/api/tasks/nope/runs")
        assert resp.status_code == 404


class TestGetRun:
    def test_get(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "r1", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs/r1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "r1"

    def test_not_found(self, client):
        resp = client.get("/api/tasks/t1/runs/nope")
        assert resp.status_code == 404

    def test_get_run_includes_fork_url(self, registered_agent, _seed_task, mock_github):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/clone", params={"token": token})
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "forksha1", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs/forksha1")
        assert resp.status_code == 200
        assert resp.json().get("fork_url") is not None

    def test_get_run_falls_back_to_repo_url(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "noforksha", "message": "m", "score": 0.5})
        resp = client.get("/api/tasks/t1/runs/noforksha")
        assert resp.status_code == 200
        assert resp.json()["fork_url"] == "https://github.com/test/test"


class TestFeed:
    def test_post_and_read(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "hello"})
        resp = client.get("/api/tasks/t1/feed")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(i["content"] == "hello" for i in items)

    def test_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "hi"}).json()
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "comment", "parent_id": post["id"], "content": "reply"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["parent_type"] == "post"
        assert data["post_id"] == post["id"]
        assert data["parent_comment_id"] is None

    def test_comment_on_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "root"}).json()
        parent = client.post("/api/tasks/t1/feed", params={"token": token},
                             json={"type": "comment", "parent_id": post["id"], "content": "first"}).json()
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "comment", "parent_type": "comment",
                                 "parent_id": parent["id"], "content": "nested"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["parent_type"] == "comment"
        assert data["post_id"] == post["id"]
        assert data["parent_comment_id"] == parent["id"]

    def test_comment_on_comment_bad_parent(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "comment", "parent_type": "comment",
                                 "parent_id": 999, "content": "nested"})
        assert resp.status_code == 404

    def test_feed_returns_nested_comments(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                           json={"type": "post", "content": "root"}).json()
        parent = client.post("/api/tasks/t1/feed", params={"token": token},
                             json={"type": "comment", "parent_id": post["id"], "content": "first"}).json()
        client.post("/api/tasks/t1/feed", params={"token": token},
                    json={"type": "comment", "parent_type": "comment",
                          "parent_id": parent["id"], "content": "nested"})
        resp = client.get("/api/tasks/t1/feed")
        assert resp.status_code == 200
        item = next(i for i in resp.json()["items"] if i["id"] == post["id"])
        assert len(item["comments"]) == 1
        assert item["comments"][0]["content"] == "first"
        assert item["comments"][0]["replies"][0]["content"] == "nested"

    def test_bad_type(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "invalid"})
        assert resp.status_code == 400


class TestVote:
    def test_upvote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/api/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "x"}).json()
        resp = client.post(f"/api/tasks/t1/feed/{post['id']}/vote",
                            params={"token": token}, json={"type": "up"})
        assert resp.status_code == 200
        assert resp.json()["upvotes"] == 1

    def test_bad_vote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/feed/1/vote",
                            params={"token": token}, json={"type": "invalid"})
        assert resp.status_code == 400


class TestClaim:
    def test_create(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/claim", params={"token": token},
                            json={"content": "working on X"})
        assert resp.status_code == 201
        assert "expires_at" in resp.json()


class TestContext:
    def test_get(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.get("/api/tasks/t1/context")
        assert resp.status_code == 200
        data = resp.json()
        assert "task" in data
        assert "leaderboard" in data
        assert "feed" in data

    def test_not_found(self, client):
        resp = client.get("/api/tasks/nope/context")
        assert resp.status_code == 404


class TestSkills:
    def test_add_and_list(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/t1/skills", params={"token": token},
                            json={"name": "retry", "description": "retry logic",
                                  "code_snippet": "while True: pass"})
        assert resp.status_code == 201
        resp = client.get("/api/tasks/t1/skills")
        assert len(resp.json()["skills"]) == 1

    def test_search(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/skills", params={"token": token},
                     json={"name": "retry", "description": "retry logic",
                           "code_snippet": "code"})
        resp = client.get("/api/tasks/t1/skills", params={"q": "retry"})
        assert len(resp.json()["skills"]) == 1
        resp = client.get("/api/tasks/t1/skills", params={"q": "zzzzz"})
        assert len(resp.json()["skills"]) == 0


class TestSearch:
    def test_search_posts(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "chain-of-thought helps"})
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "majority voting is better"})
        resp = client.get("/api/tasks/t1/search", params={"q": "chain"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert "chain" in results[0]["content"]

    def test_filter_by_type(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "an insight"})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "s1", "message": "a run", "score": 0.5})
        resp = client.get("/api/tasks/t1/search", params={"type": "post"})
        results = resp.json()["results"]
        assert all(r["type"] == "post" for r in results)
        resp = client.get("/api/tasks/t1/search", params={"type": "result"})
        results = resp.json()["results"]
        assert all(r["type"] == "result" for r in results)

    def test_sort_by_score(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "lo", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                     json={"sha": "hi", "message": "m", "score": 0.9})
        resp = client.get("/api/tasks/t1/search", params={"type": "result", "sort": "score"})
        results = resp.json()["results"]
        assert results[0]["score"] >= results[-1]["score"]

    def test_no_results(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.get("/api/tasks/t1/search", params={"q": "nonexistent_xyz"})
        assert resp.json()["results"] == []

    def test_task_not_found(self, client):
        resp = client.get("/api/tasks/nope/search", params={"q": "x"})
        assert resp.status_code == 404


class TestCloneTask:
    def test_clone_creates_copy(self, registered_agent, _seed_task, mock_github):
        client, agent_id, token = registered_agent
        resp = client.post("/api/tasks/t1/clone", params={"token": token})
        assert resp.status_code == 201
        data = resp.json()
        assert "fork_url" in data
        assert "ssh_url" in data
        assert "private_key" in data
        assert "upstream_url" in data
        assert data["upstream_url"] == "https://github.com/test/test"
        assert agent_id in data["fork_url"]
        assert data["private_key"] == "MOCK_PRIVATE_KEY"
        # Verify deploy key was added
        assert len(mock_github.deploy_keys) == 1

    def test_clone_idempotent(self, registered_agent, _seed_task, mock_github):
        client, _, token = registered_agent
        resp1 = client.post("/api/tasks/t1/clone", params={"token": token})
        resp2 = client.post("/api/tasks/t1/clone", params={"token": token})
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["fork_url"] == resp2.json()["fork_url"]
        # Second call returns empty private_key (already have it)
        assert resp2.json()["private_key"] == ""

    def test_clone_bad_token(self, client, _seed_task):
        resp = client.post("/api/tasks/t1/clone", params={"token": "fake"})
        assert resp.status_code == 401

    def test_clone_task_not_found(self, registered_agent):
        client, _, token = registered_agent
        resp = client.post("/api/tasks/nope/clone", params={"token": token})
        assert resp.status_code == 404


class TestGraph:
    def test_empty_graph(self, registered_agent, _seed_task):
        client, _, _ = registered_agent
        resp = client.get("/api/tasks/t1/graph")
        assert resp.status_code == 200
        assert resp.json()["nodes"] == []

    def test_graph_with_runs(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "g1", "message": "m", "score": 0.3})
        client.post("/api/tasks/t1/submit", params={"token": token},
                    json={"sha": "g2", "message": "m", "score": 0.6, "parent_id": "g1"})
        resp = client.get("/api/tasks/t1/graph")
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        assert len(nodes) == 2
        g1 = next(n for n in nodes if n["sha"] == "g1")
        g2 = next(n for n in nodes if n["sha"] == "g2")
        assert g1["parent"] is None
        assert g2["parent"] == "g1"

    def test_graph_task_not_found(self, client):
        resp = client.get("/api/tasks/nope/graph")
        assert resp.status_code == 404


@pytest.fixture()
def _seed_task(client):
    """Insert a task directly into DB for tests that need one."""
    from hive.server.db import get_db, now
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at) VALUES (%s, %s, %s, %s, %s)",
            ("t1", "Test Task", "A test", "https://github.com/test/test", now()),
        )
