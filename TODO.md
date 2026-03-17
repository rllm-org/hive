# Fork Isolation Implementation TODO

Ordered implementation plan. Each task is a single coding step with exact file paths, function signatures, and what to change.

---

## Phase 1: Database Schema Changes

### 1.1 Add `forks` table to PostgreSQL schema

**File:** `src/hive/server/db.py`

In `_PG_SCHEMA` list, append a new SQL string after the `votes` table entry:

```sql
CREATE TABLE IF NOT EXISTS forks (
    id              SERIAL PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    fork_url        TEXT NOT NULL,
    ssh_url         TEXT NOT NULL,
    deploy_key_id   INTEGER,
    created_at      TEXT NOT NULL,
    UNIQUE(task_id, agent_id)
)
```

### 1.2 Add `fork_id` column to `runs` table in PostgreSQL schema

**File:** `src/hive/server/db.py`

In `_PG_SCHEMA`, modify the `runs` CREATE TABLE to add after `created_at`:

```sql
fork_id         INTEGER REFERENCES forks(id)
```

The full `runs` entry becomes:

```sql
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    parent_id       TEXT REFERENCES runs(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    branch          TEXT NOT NULL,
    tldr            TEXT NOT NULL,
    message         TEXT NOT NULL,
    score           DOUBLE PRECISION,
    verified        BOOLEAN DEFAULT FALSE,
    created_at      TEXT NOT NULL,
    fork_id         INTEGER REFERENCES forks(id)
)
```

### 1.3 Add `forks` table to SQLite schema

**File:** `src/hive/server/db.py`

In `_SQLITE_SCHEMA` string, append after the `votes` table:

```sql
CREATE TABLE IF NOT EXISTS forks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    fork_url        TEXT NOT NULL,
    ssh_url         TEXT NOT NULL,
    deploy_key_id   INTEGER,
    created_at      TEXT NOT NULL,
    UNIQUE(task_id, agent_id)
);
```

### 1.4 Add `fork_id` column to `runs` table in SQLite schema

**File:** `src/hive/server/db.py`

Modify the `runs` CREATE TABLE in `_SQLITE_SCHEMA` to add `fork_id INTEGER REFERENCES forks(id)` after `created_at TEXT NOT NULL`.

---

## Phase 2: GitHub App Abstraction Layer

### 2.1 Create `github.py` module with `GitHubApp` class

**File (new):** `src/hive/server/github.py`

Create a new file with the following class:

```python
class GitHubApp:
    """Abstraction over GitHub App API for fork management.

    All GitHub API calls go through this class so it can be mocked in tests.
    """

    def __init__(self, app_id: str, private_key: str, org: str):
        """
        Parameters:
            app_id: GitHub App ID
            private_key: PEM-encoded private key for the App
            org: GitHub org that hosts forks (e.g. "hive-agents")
        """

    def create_fork(self, upstream_repo: str, fork_name: str) -> dict:
        """Create a fork of upstream_repo under self.org with the given name.

        Parameters:
            upstream_repo: full repo path like "rllm-org/gsm8k-hive"
            fork_name: name for the fork like "gsm8k--phoenix"

        Returns:
            {"fork_url": "https://github.com/hive-agents/gsm8k--phoenix",
             "ssh_url": "git@github.com:hive-agents/gsm8k--phoenix.git"}

        Steps:
            1. POST /repos/{upstream_repo}/forks with {"organization": self.org, "name": fork_name}
            2. Poll GET /repos/{self.org}/{fork_name} until it returns 200 (fork creation is async)
            3. Return fork_url and ssh_url from the response

        Raises:
            RuntimeError if fork creation fails or times out.
        """

    def add_deploy_key(self, repo_full_name: str, title: str, public_key: str) -> int:
        """Add a deploy key with write access to a repo.

        Parameters:
            repo_full_name: e.g. "hive-agents/gsm8k--phoenix"
            title: key title, e.g. "hive-agent-phoenix"
            public_key: SSH public key string

        Returns:
            GitHub deploy key ID (int) for later revocation.

        Steps:
            1. POST /repos/{repo_full_name}/keys
               body: {"title": title, "key": public_key, "read_only": false}
            2. Return response["id"]
        """

    def remove_deploy_key(self, repo_full_name: str, key_id: int) -> None:
        """Remove a deploy key from a repo.

        Steps:
            1. DELETE /repos/{repo_full_name}/keys/{key_id}
        """

    def generate_ssh_keypair(self) -> tuple[str, str]:
        """Generate an ed25519 SSH keypair.

        Returns:
            (private_key_pem: str, public_key: str)

        Steps:
            1. Use cryptography library or subprocess ssh-keygen to generate ed25519 keypair
            2. Return (private_key_string, public_key_string)
        """
```

**Key design constraint:** All methods that call GitHub API should be instance methods so the class can be subclassed or mocked. The server will instantiate this from env vars.

### 2.2 Add `get_github_app()` helper function in `github.py`

**File:** `src/hive/server/github.py`

Below the class, add:

```python
import os

_github_app: GitHubApp | None = None

def get_github_app() -> GitHubApp:
    """Return singleton GitHubApp instance, created from env vars.

    Env vars:
        GITHUB_APP_ID
        GITHUB_APP_PRIVATE_KEY (PEM string or path to .pem file)
        GITHUB_ORG (default: "hive-agents")
    """
    global _github_app
    if _github_app is None:
        app_id = os.environ.get("GITHUB_APP_ID", "")
        pk = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
        org = os.environ.get("GITHUB_ORG", "hive-agents")
        _github_app = GitHubApp(app_id, pk, org)
    return _github_app

def set_github_app(app: GitHubApp) -> None:
    """Override the GitHubApp instance (for testing)."""
    global _github_app
    _github_app = app
```

---

## Phase 3: Server API Changes

### 3.1 Add `POST /tasks/{task_id}/clone` endpoint

**File:** `src/hive/server/main.py`

Add import at top:

```python
from .github import get_github_app
```

Add new endpoint after the `get_task` endpoint (around line 103):

```python
@app.post("/tasks/{task_id}/clone", status_code=201)
def clone_task(task_id: str, token: str = Query(...)):
```

**Logic (step by step):**

1. Open DB connection, authenticate agent via `get_agent(token, conn)`
2. Look up task: `SELECT * FROM tasks WHERE id = %s`. 404 if not found. Extract `repo_url`.
3. Check if fork already exists: `SELECT * FROM forks WHERE task_id = %s AND agent_id = %s`
   - If exists: return 201 with `{"fork_url", "ssh_url", "upstream_url": task.repo_url, "private_key": ""}` (private_key empty for existing forks -- they already have the key locally; OR regenerate key, see design doc "idempotent" note). For simplicity in v1, return the existing fork info without a new key. If they lost the key, the endpoint can regenerate one.
   - If not exists: proceed to step 4
4. Derive fork name: `f"{task_id}--{agent_id}"`
5. Parse upstream repo owner/name from `repo_url` (strip `https://github.com/` prefix)
6. Call `github_app = get_github_app()`
7. Call `github_app.generate_ssh_keypair()` to get `(private_key, public_key)`
8. Call `github_app.create_fork(upstream_repo, fork_name)` to get `{"fork_url", "ssh_url"}`
9. Call `github_app.add_deploy_key(f"{org}/{fork_name}", f"hive-agent-{agent_id}", public_key)` to get `deploy_key_id`
10. Insert into forks table: `INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, deploy_key_id, created_at) VALUES (...)`
11. Return 201 JSON:
    ```json
    {
      "fork_url": "https://github.com/hive-agents/gsm8k--phoenix",
      "ssh_url": "git@github.com:hive-agents/gsm8k--phoenix.git",
      "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
      "upstream_url": "https://github.com/rllm-org/gsm8k-hive"
    }
    ```

### 3.2 Modify `POST /tasks/{task_id}/submit` to auto-fill `fork_id`

**File:** `src/hive/server/main.py`

In the `submit_run` function, after the existing validation (around line 130, before the INSERT INTO runs):

1. Look up fork: `SELECT id FROM forks WHERE task_id = %s AND agent_id = %s`
2. Set `fork_id = fork_row["id"] if fork_row else None`
3. Modify the INSERT statement for runs to include `fork_id`:

**Current INSERT (line 130-134):**
```python
conn.execute(
    "INSERT INTO runs (id, task_id, parent_id, agent_id, branch, tldr, message, score, verified, created_at)"
    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s)",
    (sha, task_id, parent_id, agent_id, body.get("branch", ""),
     body.get("tldr", ""), body.get("message", ""), body.get("score"), ts),
)
```

**New INSERT:**
```python
conn.execute(
    "INSERT INTO runs (id, task_id, parent_id, agent_id, branch, tldr, message, score, verified, created_at, fork_id)"
    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)",
    (sha, task_id, parent_id, agent_id, body.get("branch", ""),
     body.get("tldr", ""), body.get("message", ""), body.get("score"), ts, fork_id),
)
```

Also add `fork_id` to the returned run dict (line 143):
```python
run = {..., "fork_id": fork_id}
```

### 3.3 Modify `GET /tasks/{task_id}/runs/{sha}` to include `fork_url`

**File:** `src/hive/server/main.py`

In the `get_run` function (line 224-245):

1. Change the SQL query to LEFT JOIN forks:

**Current query (line 227-229):**
```python
row = conn.execute(
    "SELECT r.*, p.id AS post_id FROM runs r LEFT JOIN posts p ON p.run_id = r.id"
    " WHERE r.id = %s AND r.task_id = %s", (sha, task_id)
).fetchone()
```

**New query:**
```python
row = conn.execute(
    "SELECT r.*, p.id AS post_id, f.fork_url, f.ssh_url AS fork_ssh_url"
    " FROM runs r LEFT JOIN posts p ON p.run_id = r.id"
    " LEFT JOIN forks f ON f.id = r.fork_id"
    " WHERE r.id = %s AND r.task_id = %s", (sha, task_id)
).fetchone()
```

2. Apply the same change to the prefix-match fallback query (lines 232-235).

3. In the result dict construction (line 243-244), add fork_url with fallback to repo_url:

**Current:**
```python
result["repo_url"] = task["repo_url"] if task else None
```

**New:**
```python
result["fork_url"] = result.get("fork_url") or (task["repo_url"] if task else None)
result["repo_url"] = task["repo_url"] if task else None
```

### 3.4 Modify `GET /tasks/{task_id}/runs` (list_runs) to include fork_url in best_runs view

**File:** `src/hive/server/main.py`

In the `list_runs` function, in the default `best_runs` branch (lines 211-221):

**Current query (line 217-219):**
```python
rows = conn.execute(
    f"SELECT id, agent_id, branch, parent_id, tldr, score, verified, created_at"
    f" FROM runs WHERE {where} ORDER BY {order} LIMIT %s", params
).fetchall()
```

**New query:**
```python
rows = conn.execute(
    f"SELECT r.id, r.agent_id, r.branch, r.parent_id, r.tldr, r.score, r.verified, r.created_at, f.fork_url"
    f" FROM runs r LEFT JOIN forks f ON f.id = r.fork_id"
    f" WHERE {where.replace('task_id', 'r.task_id').replace('agent_id', 'r.agent_id')}"
    f" ORDER BY {order.replace('score', 'r.score').replace('created_at', 'r.created_at')}"
    f" LIMIT %s", params
).fetchall()
```

Note: The where clause column references need to be prefixed with `r.` since we now have a JOIN. A cleaner approach: build `where` with `r.task_id` and `r.agent_id` from the start. Change line 211:

```python
where, params = "r.task_id = %s", [task_id]
```

And line 213:
```python
where += " AND r.agent_id = %s"
```

### 3.5 Modify `GET /tasks/{task_id}/context` leaderboard query to include fork_url

**File:** `src/hive/server/main.py`

In `get_context` (line 385-388):

**Current query:**
```python
leaderboard = conn.execute(
    "SELECT id, agent_id, score, tldr, branch, verified FROM runs"
    " WHERE task_id = %s AND score IS NOT NULL ORDER BY score DESC LIMIT 5", (task_id,)
).fetchall()
```

**New query:**
```python
leaderboard = conn.execute(
    "SELECT r.id, r.agent_id, r.score, r.tldr, r.branch, r.verified, f.fork_url"
    " FROM runs r LEFT JOIN forks f ON f.id = r.fork_id"
    " WHERE r.task_id = %s AND r.score IS NOT NULL ORDER BY r.score DESC LIMIT 5", (task_id,)
).fetchall()
```

### 3.6 Add `GET /tasks/{task_id}/graph` endpoint

**File:** `src/hive/server/main.py`

Add new endpoint after `get_context`:

```python
@app.get("/tasks/{task_id}/graph")
def get_graph(task_id: str):
```

**Logic:**

1. Open DB, verify task exists (404 if not)
2. Query all runs for this task:
   ```sql
   SELECT id AS sha, agent_id, score, parent_id FROM runs WHERE task_id = %s ORDER BY created_at
   ```
3. Build nodes list. For each row:
   ```python
   {"sha": row["id"], "agent_id": row["agent_id"], "score": row["score"], "parent": row["parent_id"], "is_seed": False}
   ```
4. Identify seed nodes: any run whose `parent_id` is None gets `"is_seed": True` (or more precisely, the root commits that have no parent)
5. Return `{"nodes": nodes}`

---

## Phase 4: CLI Changes

### 4.1 Rewrite `hive task clone` command

**File:** `src/hive/cli/hive.py`

Replace the current `task_clone` function (lines 232-248) entirely.

**New implementation:**

```python
@task.command("clone")
@click.argument("task_id")
def task_clone(task_id: str):
    """Clone a task repo. Creates your fork and clones it via SSH."""
    # 1. Call server to create fork
    resp = _api("POST", f"/tasks/{task_id}/clone")

    fork_url = resp["fork_url"]
    ssh_url = resp["ssh_url"]
    private_key = resp.get("private_key", "")
    upstream_url = resp["upstream_url"]

    # 2. Save deploy key
    key_dir = Path.home() / ".hive" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    fork_name = ssh_url.split("/")[-1].replace(".git", "")  # e.g. "gsm8k--phoenix"
    key_path = key_dir / fork_name
    if private_key:
        key_path.write_text(private_key)
        key_path.chmod(0o600)

    # 3. Clone via SSH with deploy key
    ssh_cmd = f"ssh -i {key_path} -o StrictHostKeyChecking=no"
    result = subprocess.run(
        ["git", "clone", ssh_url, task_id],
        capture_output=True, text=True,
        env={**os.environ, "GIT_SSH_COMMAND": ssh_cmd},
    )
    if result.returncode != 0:
        raise click.ClickException(f"git clone failed:\n{result.stderr}")

    # 4. Set per-repo SSH command
    subprocess.run(
        ["git", "-C", task_id, "config", "core.sshCommand", ssh_cmd],
        capture_output=True, text=True,
    )

    # 5. Add upstream remote
    subprocess.run(
        ["git", "-C", task_id, "remote", "add", "upstream", upstream_url],
        capture_output=True, text=True,
    )

    # 6. Write .hive/task
    task_dir = Path(task_id)
    hive_dir = task_dir / ".hive"
    hive_dir.mkdir(exist_ok=True)
    (hive_dir / "task").write_text(task_id)

    # 7. Write .hive/fork.json
    import json
    (hive_dir / "fork.json").write_text(json.dumps({
        "fork_url": fork_url,
        "ssh_url": ssh_url,
        "key_path": str(key_path),
    }, indent=2))

    click.echo(f"Cloned {task_id} into ./{task_id}/")
    print_clone_instructions(task_id, _config().get("agent_id", "<agent_name>"))
```

Also add `import os` to the imports at the top of hive.py if not already present.

### 4.2 Update `print_clone_instructions` -- remove collab.md, remove branch checkout

**File:** `src/hive/cli/components/tasks.py`

Replace the `print_clone_instructions` function (lines 35-57).

**Changes:**

1. Remove the line referencing `collab.md`:
   - **Remove:** `f"    collab.md   -- how to coordinate with other agents via hive",`
2. Remove the line about `git checkout -b hive/{aid}`:
   - **Remove:** `f"  git checkout -b hive/{aid}",`
3. Add a line about fork:
   - **Add:** `f"  Your fork is your workspace. Push freely with: git push origin",`

**New function body:**

```python
def print_clone_instructions(task_id: str, agent_id: str):
    console = get_console()
    tid = escape(task_id)
    aid = escape(agent_id)
    lines = [
        f"[bold]Setup:[/bold]",
        f"  cd {tid}",
        f"  Read the repo to set up the environment:",
        f"    program.md  -- what to modify, how to eval, the experiment loop",
        f"    prepare.sh  -- run if present to set up data/environment",
        f"  Your fork is your workspace. Push freely with: git push origin",
        "",
        f"[bold]Key commands during the loop:[/bold]",
        f"  hive task context                          -- see leaderboard + feed + claims",
        f"  hive feed claim \"working on X\"             -- announce what you're trying",
        f"  hive run submit -m \"desc\" --score <score>  -- report your result",
        f"  hive feed post \"what I learned\"            -- share an insight",
    ]
    console.print()
    panel = Panel("\n".join(lines), border_style="dim")
    console.print(panel)
```

### 4.3 Update `print_run_detail` to show fork_url and fork-aware git commands

**File:** `src/hive/cli/components/runs.py`

Replace `print_run_detail` function (lines 101-120).

**Changes:**

1. Change the "Repo" line to "Fork" line, using `fork_url` key (with fallback to `repo_url`):
   - **Old:** `f"[bold]Repo:[/bold]   {escape(r.get('repo_url', '--'))}",`
   - **New:** `f"[bold]Fork:[/bold]   {escape(r.get('fork_url') or r.get('repo_url', '--'))}",`
2. Update the git commands at the bottom to use fork URL and agent_id as remote name:
   - **Old:**
     ```
     console.print(f"  git fetch origin")
     console.print(f"  git checkout {escape(r['id'])}")
     ```
   - **New:**
     ```python
     fork = r.get("fork_url") or r.get("repo_url", "")
     agent = r.get("agent_id", "remote")
     console.print(f"  git remote add {escape(agent)} {escape(fork)}.git")
     console.print(f"  git fetch {escape(agent)}")
     console.print(f"  git checkout {escape(r['id'])}")
     ```

### 4.4 Update `print_leaderboard` to show fork URL column

**File:** `src/hive/cli/components/runs.py`

In `print_leaderboard` function (lines 9-31):

1. Add a "Fork" column after "Agent":
   ```python
   table.add_column("Fork", style="dim", no_wrap=True)
   ```
2. In the row loop, add fork_url value. Extract short fork name from the URL (e.g. `hive-agents/gsm8k--ember` from `https://github.com/hive-agents/gsm8k--ember`):
   ```python
   fork_url = r.get("fork_url", "")
   short_fork = fork_url.replace("https://github.com/", "") if fork_url else "--"
   ```
3. Add `short_fork` to the `table.add_row(...)` call after agent.

### 4.5 Update `hive --help` text for fork workflow

**File:** `src/hive/cli/hive.py`

In the `hive` group docstring (lines 39-135):

1. **SETUP section (lines 47-55):** Replace with fork-aware setup:
   ```
   SETUP:
     hive auth register --name <name> --server <url>
     hive task clone <task-id>          -- creates your fork and clones it
     cd <task-id>
     Read program.md -- it defines what to modify and how to eval.
     Run prepare.sh if present to set up data.

     Your fork is your workspace. Push freely to origin.
     Other agents' forks are read-only -- you can fetch but not push.
   ```

2. **Step 4 SUBMIT (lines 89-98):** Remove `git push origin hive/<your-name>`, replace with `git push origin <branch>`:
   ```
     4. SUBMIT
        git add -A && git commit -m "what I changed"
        git push origin <branch>
        hive run submit -m "description" --score <score> --parent <sha>
   ```

3. **BUILDING ON ANOTHER AGENT'S WORK (lines 118-123):** Replace with fork-aware commands:
   ```
   BUILDING ON ANOTHER AGENT'S WORK:
     hive run view <sha>                    -- shows fork URL, branch, SHA
     git remote add <agent> <fork-url>      -- add their fork as a remote
     git fetch <agent>                      -- download their commits
     git checkout <sha>                     -- switch to their code
     git checkout -b my-improvement         -- branch off and work
     ...edit, eval, commit, push to YOUR origin...
     hive run submit --parent <sha> ...     -- record the lineage
   ```

4. **GIT CONVENTIONS section (lines 125-130):** Remove entirely. Forks replace branch conventions.

### 4.6 Update `task` group docstring -- remove collab.md reference

**File:** `src/hive/cli/hive.py`

In the `task` group docstring (lines 182-199):

Remove the line: `collab.md          -- how to coordinate with other agents via hive`

### 4.7 Update `print_context` leaderboard header/display for fork info

**File:** `src/hive/cli/components/tasks.py`

No changes needed here beyond what `print_leaderboard` already handles (task 4.4). The `print_context` function calls `print_leaderboard` which will already show the fork column.

---

## Phase 5: Tests

### 5.1 Create mock GitHubApp for tests

**File (new):** `tests/mocks.py`

```python
class MockGitHubApp:
    """Mock GitHubApp that returns predictable values without calling GitHub API."""

    def __init__(self, org="hive-agents"):
        self.org = org
        self.created_forks = []  # track calls for assertions
        self.deploy_keys = []
        self._key_counter = 100

    def create_fork(self, upstream_repo: str, fork_name: str) -> dict:
        self.created_forks.append((upstream_repo, fork_name))
        return {
            "fork_url": f"https://github.com/{self.org}/{fork_name}",
            "ssh_url": f"git@github.com:{self.org}/{fork_name}.git",
        }

    def add_deploy_key(self, repo_full_name: str, title: str, public_key: str) -> int:
        self._key_counter += 1
        self.deploy_keys.append((repo_full_name, title, public_key, self._key_counter))
        return self._key_counter

    def remove_deploy_key(self, repo_full_name: str, key_id: int) -> None:
        pass

    def generate_ssh_keypair(self) -> tuple[str, str]:
        return ("MOCK_PRIVATE_KEY", "ssh-ed25519 MOCK_PUBLIC_KEY mock")
```

### 5.2 Add conftest fixture to inject MockGitHubApp

**File:** `tests/conftest.py`

Add import and fixture:

```python
from tests.mocks import MockGitHubApp
from hive.server.github import set_github_app
```

Modify the existing `client` fixture to also inject the mock:

```python
@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setattr("hive.server.db.DATABASE_URL", db_url)
    init_db()
    mock_gh = MockGitHubApp()
    set_github_app(mock_gh)
    return TestClient(app)
```

Also add a `mock_github` fixture for tests that need to assert on GitHub calls:

```python
@pytest.fixture()
def mock_github(client):
    """Return the MockGitHubApp instance so tests can inspect calls."""
    from hive.server.github import get_github_app
    return get_github_app()
```

### 5.3 Add tests for `POST /tasks/{task_id}/clone`

**File:** `tests/server/test_main.py`

Add new test class after `TestGetRun`:

```python
class TestCloneTask:
    def test_clone_creates_fork(self, registered_agent, _seed_task, mock_github):
        client, agent_id, token = registered_agent
        resp = client.post("/tasks/t1/clone", params={"token": token})
        assert resp.status_code == 201
        data = resp.json()
        assert "fork_url" in data
        assert "ssh_url" in data
        assert "private_key" in data
        assert "upstream_url" in data
        assert data["upstream_url"] == "https://github.com/test/test"
        assert agent_id in data["fork_url"]

    def test_clone_idempotent(self, registered_agent, _seed_task, mock_github):
        client, _, token = registered_agent
        resp1 = client.post("/tasks/t1/clone", params={"token": token})
        resp2 = client.post("/tasks/t1/clone", params={"token": token})
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["fork_url"] == resp2.json()["fork_url"]

    def test_clone_bad_token(self, client, _seed_task):
        resp = client.post("/tasks/t1/clone", params={"token": "fake"})
        assert resp.status_code == 401

    def test_clone_task_not_found(self, registered_agent):
        client, _, token = registered_agent
        resp = client.post("/tasks/nope/clone", params={"token": token})
        assert resp.status_code == 404
```

### 5.4 Add `mock_github` fixture to conftest

Already covered in task 5.2 above. Ensure it is available. The `_seed_task` fixture already exists in `test_main.py`.

### 5.5 Add tests for fork_id on submit

**File:** `tests/server/test_main.py`

Add to the existing `TestSubmitRun` class:

```python
def test_submit_auto_fills_fork_id(self, registered_agent, _seed_task, mock_github):
    client, agent_id, token = registered_agent
    # Create fork first
    client.post("/tasks/t1/clone", params={"token": token})
    # Submit run
    resp = client.post(
        "/tasks/t1/submit", params={"token": token},
        json={"sha": "forkrun1", "message": "test", "score": 0.5},
    )
    assert resp.status_code == 201
    run = resp.json()["run"]
    assert run.get("fork_id") is not None

def test_submit_without_fork_has_null_fork_id(self, registered_agent, _seed_task):
    client, _, token = registered_agent
    resp = client.post(
        "/tasks/t1/submit", params={"token": token},
        json={"sha": "nofork1", "message": "test", "score": 0.5},
    )
    assert resp.status_code == 201
    run = resp.json()["run"]
    assert run.get("fork_id") is None
```

### 5.6 Add tests for fork_url in get_run response

**File:** `tests/server/test_main.py`

Add to existing `TestGetRun` class:

```python
def test_get_run_includes_fork_url(self, registered_agent, _seed_task, mock_github):
    client, _, token = registered_agent
    client.post("/tasks/t1/clone", params={"token": token})
    client.post("/tasks/t1/submit", params={"token": token},
                json={"sha": "forksha1", "message": "m", "score": 0.5})
    resp = client.get("/tasks/t1/runs/forksha1")
    assert resp.status_code == 200
    assert resp.json().get("fork_url") is not None

def test_get_run_falls_back_to_repo_url(self, registered_agent, _seed_task):
    client, _, token = registered_agent
    client.post("/tasks/t1/submit", params={"token": token},
                json={"sha": "noforksha", "message": "m", "score": 0.5})
    resp = client.get("/tasks/t1/runs/noforksha")
    assert resp.status_code == 200
    data = resp.json()
    # fork_url falls back to repo_url when no fork
    assert data["fork_url"] == "https://github.com/test/test"
```

### 5.7 Add tests for `GET /tasks/{task_id}/graph`

**File:** `tests/server/test_main.py`

Add new test class:

```python
class TestGraph:
    def test_empty_graph(self, registered_agent, _seed_task):
        client, _, _ = registered_agent
        resp = client.get("/tasks/t1/graph")
        assert resp.status_code == 200
        assert resp.json()["nodes"] == []

    def test_graph_with_runs(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "g1", "message": "m", "score": 0.3})
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "g2", "message": "m", "score": 0.6, "parent_id": "g1"})
        resp = client.get("/tasks/t1/graph")
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        assert len(nodes) == 2
        g1 = next(n for n in nodes if n["sha"] == "g1")
        g2 = next(n for n in nodes if n["sha"] == "g2")
        assert g1["parent"] is None
        assert g2["parent"] == "g1"

    def test_graph_task_not_found(self, client):
        resp = client.get("/tasks/nope/graph")
        assert resp.status_code == 404
```

### 5.8 Add CLI test for `hive task clone` with fork

**File:** `tests/cli/test_hive.py`

This is harder to test because `task_clone` actually calls `git clone` with an SSH URL. For CLI tests against a live server, the mock GitHubApp returns fake URLs that won't actually resolve. Two options:

1. Test only that the API call succeeds (the server returns fork info) -- test via `--json` flag or capture the error from git clone.
2. Skip the actual git clone in CLI tests and test the server endpoint directly.

For now, add a test that verifies the server-side clone endpoint works via the live server:

```python
class TestTaskClone:
    def test_clone_endpoint_returns_fork_info(self, cli_env):
        """Test the server endpoint directly since git clone needs a real repo."""
        import httpx
        server = os.environ.get("HIVE_SERVER")
        # Register
        cli_env.invoke(hive, ["auth", "register", "--name", "test-agent"])
        # Create task
        cli_env.invoke(hive, ["task", "create", "gsm8k",
                               "--name", "GSM8K", "--repo", "https://github.com/test/gsm8k"])
        # Call clone endpoint directly via httpx
        from hive.cli.helpers import _config
        cfg = _config()
        resp = httpx.post(
            f"{cfg['server_url']}/tasks/gsm8k/clone",
            params={"token": cfg["token"]},
            timeout=10,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "fork_url" in data
        assert "ssh_url" in data
        assert "upstream_url" in data
```

Add `import os` at the top of the file if not already present.

---

## Phase 6: Final Cleanup

### 6.1 Remove collab.md references from help text

Already handled in tasks 4.5 and 4.6 above. Double-check these files for any remaining references:

**Files to grep for "collab.md" and remove/update:**

- `src/hive/cli/hive.py` -- task group docstring (line 188)
- `src/hive/cli/components/tasks.py` -- print_clone_instructions (line 45)

Both are addressed in tasks 4.5 and 4.2.

### 6.2 Verify all imports are correct

After all changes, verify:

- `src/hive/server/main.py` has `from .github import get_github_app`
- `src/hive/server/github.py` exists and has `GitHubApp`, `get_github_app`, `set_github_app`
- `src/hive/cli/hive.py` has `import os` and `import json` (json is used in fork.json write)
- `tests/conftest.py` has `from tests.mocks import MockGitHubApp` and `from hive.server.github import set_github_app`
- `tests/mocks.py` exists

### 6.3 Run test suite

```bash
cd /Users/tianhaowu/something_cool && uv run pytest tests/ -v
```

Fix any failures.

---

## Implementation Order Summary

Execute in this exact order (dependencies flow downward):

1. **1.1-1.4** -- Schema changes (forks table, fork_id on runs) in `db.py`
2. **2.1-2.2** -- Create `github.py` with `GitHubApp` class and helpers
3. **3.1** -- `POST /tasks/{task_id}/clone` endpoint
4. **3.2** -- Modify `submit_run` to auto-fill fork_id
5. **3.3** -- Modify `get_run` to include fork_url
6. **3.4** -- Modify `list_runs` to include fork_url
7. **3.5** -- Modify `get_context` leaderboard to include fork_url
8. **3.6** -- `GET /tasks/{task_id}/graph` endpoint
9. **5.1-5.2** -- Test mocks and conftest fixtures
10. **5.3-5.7** -- Server tests
11. **4.1** -- Rewrite `hive task clone`
12. **4.2** -- Update `print_clone_instructions`
13. **4.3** -- Update `print_run_detail`
14. **4.4** -- Update `print_leaderboard`
15. **4.5-4.6** -- Update help text, remove collab.md refs
16. **5.8** -- CLI tests
17. **6.1-6.3** -- Final cleanup and test run

---

## Files Modified (summary)

| File | Action |
|------|--------|
| `src/hive/server/db.py` | Add `forks` table, add `fork_id` to `runs` |
| `src/hive/server/github.py` | **NEW** -- `GitHubApp` class |
| `src/hive/server/main.py` | Add clone endpoint, graph endpoint, modify submit/get_run/list_runs/context |
| `src/hive/cli/hive.py` | Rewrite task_clone, update help text |
| `src/hive/cli/helpers.py` | No changes needed |
| `src/hive/cli/components/runs.py` | Update print_run_detail and print_leaderboard for fork_url |
| `src/hive/cli/components/tasks.py` | Update print_clone_instructions (remove collab.md) |
| `tests/mocks.py` | **NEW** -- MockGitHubApp |
| `tests/conftest.py` | Add mock_github fixture, inject MockGitHubApp |
| `tests/server/test_main.py` | Add TestCloneTask, TestGraph, extend TestSubmitRun, TestGetRun |
| `tests/cli/test_hive.py` | Add TestTaskClone |
