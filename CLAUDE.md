# Hive

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
bash ci/run_all.sh                                            # all CI checks + tests
```

PostgreSQL required. Set `DATABASE_URL` env var. Production URL set via Railway.

## Style

- Python, minimal deps (fastapi, uvicorn, click, httpx, psycopg)
- Keep files under 500 lines
- No over-engineering — bare minimum that works
- Don't add docstrings, comments, or type annotations to code you didn't change
- Run `bash ci/run_all.sh` before submitting changes
