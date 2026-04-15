# Hive

## Before You Start

Read these docs to understand the system before making changes:

- `docs/design.md` — architecture, data model, key decisions
- `docs/api.md` — REST API spec with request/response examples
- `docs/cli.md` — CLI command reference

## Dev

### Quick start

```bash
bash scripts/dev.sh
```

Prompts for setup mode:
- **Mode 1** (default): Frontend only — connects to hosted backend, just needs Node.js
- **Mode 2**: Full local — installs PostgreSQL, backend, frontend, seeds demo data

Frontend: http://localhost:3000

### Tests

```bash
uv run pytest tests/cli/ tests/server/test_main.py tests/server/test_mentions.py -x
bash ci/run_all.sh                                            # full CI
```

## Style

- Python, minimal deps (fastapi, uvicorn, click, httpx, psycopg)
- Keep files under 500 lines
- No over-engineering — bare minimum that works
- Don't add docstrings, comments, or type annotations to code you didn't change
- Run `bash ci/run_all.sh` before submitting changes
