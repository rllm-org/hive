import pytest
import pytest_asyncio

from hive.server.db import init_db, get_db, init_pool, close_pool, now
from hive.server.names import generate_name


@pytest_asyncio.fixture()
async def async_db(monkeypatch, _pg_test_url):
    """Async DB fixture: init schema, start pool, truncate, yield, close pool."""
    if _pg_test_url is None:
        pytest.skip("PostgreSQL not available")
    monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
    init_db()
    import psycopg
    with psycopg.connect(_pg_test_url, autocommit=True) as conn:
        conn.execute("TRUNCATE votes, comments, claims, skills, posts, runs, forks, agents, tasks RESTART IDENTITY CASCADE")
    await init_pool()
    yield
    await close_pool()


class TestGenerateName:
    @pytest.mark.asyncio
    async def test_returns_adjective_noun(self, async_db):
        async with get_db() as conn:
            name = await generate_name(conn)
        assert "-" in name

    @pytest.mark.asyncio
    async def test_unique(self, async_db):
        names = set()
        async with get_db() as conn:
            for _ in range(20):
                n = await generate_name(conn)
                await conn.execute(
                    "INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)",
                    (n, now(), now()),
                )
                names.add(n)
        assert len(names) == 20
