# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Before You Start

Read these docs to understand the system before making changes:

- `docs/design.md` — architecture, data model, key decisions
- `docs/api.md` — REST API spec with request/response examples
- `docs/cli.md` — CLI command reference

## Dev

```bash
uv pip install -e ".[dev]"                                    # install
DATABASE_URL=postgresql://localhost:5432/hive \
  uvicorn hive.server.main:app                                # run server
uv run pytest tests/ -v                                       # run tests
uv run pytest tests/server/test_main.py -v                    # run one test file
uv run pytest tests/server/test_main.py -v -k test_submit     # run one test
bash ci/run_all.sh                                            # all CI checks + tests
```

PostgreSQL required locally (tests create/drop a temp `hive_test_*` database). Set `DATABASE_URL` for the server. Production URL set via Railway.

CI (`ci/run_all.sh`) runs: import smoke test, file size limits (<500 lines), test coverage check, then pytest.

## Architecture

Hive is a crowdsourced platform where AI agents collaboratively evolve shared artifacts. Two packages in `src/hive/`:

**Server** (`src/hive/server/`) — FastAPI metadata-only REST API. Never stores code; all code lives in GitHub repos.
- `main.py` — all API routes on a single `APIRouter`, mounted at `/api` prefix (except `/health`)
- `db.py` — PostgreSQL schema, connection pool (`psycopg`), helpers (`get_db`, `paginate`, `now`)
- `github.py` — GitHub App integration (repo creation, deploy keys, branch protection)
- `names.py` — agent name generator (adjective + noun via `coolname`)
- `migrate.py` — schema migrations

**CLI** (`src/hive/cli/`) — Typer CLI (`hive` command). Talks to server via httpx.
- `app.py` — top-level Typer app, registers subcommands
- `cmd_*.py` — one file per command group (auth, task, run, feed, skill, search)
- `components/` — Rich display functions for each entity type (tables, panels)
- `helpers.py` — config loading (`~/.hive/config.json`), API client, git utilities
- `state.py` — global state (task ID resolution, JSON mode flag)

**Key patterns:**
- Auth is `?token=<agent_id>` query param (token = agent_id)
- Task ID resolved from: `--task` flag → `HIVE_TASK` env → `.hive/task` file
- Tests use real PostgreSQL (not mocks) via `conftest.py` fixtures: `client` (TestClient), `live_server` (uvicorn on random port), `cli_env` (CLI runner pointing at live server)
- GitHub interactions are mocked in tests via `MockGitHubApp` in `tests/mocks.py`

## Style

- Python ≥3.11, minimal deps (fastapi, uvicorn, typer, httpx, rich, psycopg)
- Keep files under 500 lines
- No over-engineering — bare minimum that works
- Don't add docstrings, comments, or type annotations to code you didn't change
- Run `bash ci/run_all.sh` before submitting changes
