import pytest

from hive.server.agent_sdk_client import AgentSdkClient


@pytest.mark.asyncio
async def test_create_session_posts_json_with_sandbox_id(monkeypatch):
    recorded: list[tuple] = []

    async def fake_json(self, method, path, **kw):
        recorded.append((method, path, kw.get("json") or {}))
        return {"session_id": "s1", "sandbox_id": "sb1", "connected": True}

    monkeypatch.setattr(AgentSdkClient, "_json", fake_json)
    client = AgentSdkClient("http://example", "", 1.0)
    out = await client.create_session("sb-xyz", name="agent-a", agent_type="claude")
    assert out["session_id"] == "s1"
    assert recorded[0][0] == "POST"
    assert recorded[0][1] == "/sessions"
    assert recorded[0][2]["sandbox_id"] == "sb-xyz"
    assert recorded[0][2]["name"] == "agent-a"
