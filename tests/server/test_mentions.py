import pytest

from hive.server.mentions import _MENTION_RE, parse_mentions


class _StubCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows


class _StubConn:
    def __init__(self, known_agents, known_users=None):
        self._known_agents = set(known_agents)
        self._known_users = set(known_users or [])

    async def execute(self, query, params):
        if "users" in query:
            handles = [p for p in params if p in self._known_users]
            return _StubCursor([{"handle": h} for h in handles])
        ids = [p for p in params if p in self._known_agents]
        return _StubCursor([{"id": aid} for aid in ids])


class TestMentionRegex:
    def test_matches_basic(self):
        assert [m.group(1) for m in _MENTION_RE.finditer("hi @agent-a")] == ["agent-a"]

    def test_case_insensitive(self):
        assert [m.group(1) for m in _MENTION_RE.finditer("@AgentB")] == ["AgentB"]

    def test_multiple(self):
        names = [m.group(1).lower() for m in _MENTION_RE.finditer("@a and @b-1 and @c")]
        assert names == ["a", "b-1", "c"]

    def test_rejects_leading_hyphen(self):
        assert [m.group(1) for m in _MENTION_RE.finditer("@-bad")] == []


class TestParseMentions:
    @pytest.mark.asyncio
    async def test_returns_known_agents_in_order(self):
        conn = _StubConn({"agent-a", "agent-b"})
        result = await parse_mentions("ping @agent-b then @agent-a", conn)
        assert result == ["agent-b", "agent-a"]

    @pytest.mark.asyncio
    async def test_drops_unknown(self):
        conn = _StubConn({"agent-a"})
        result = await parse_mentions("@agent-a @agent-typo", conn)
        assert result == ["agent-a"]

    @pytest.mark.asyncio
    async def test_dedupes(self):
        conn = _StubConn({"agent-a"})
        result = await parse_mentions("@agent-a hi @agent-a", conn)
        assert result == ["agent-a"]

    @pytest.mark.asyncio
    async def test_no_mentions_skips_db(self):
        conn = _StubConn(set())
        assert await parse_mentions("plain text", conn) == []

    @pytest.mark.asyncio
    async def test_lowercases_before_lookup(self):
        conn = _StubConn({"agentb"})
        result = await parse_mentions("@AgentB", conn)
        assert result == ["agentb"]
