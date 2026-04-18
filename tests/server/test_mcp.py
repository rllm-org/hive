"""Tests for the MCP server endpoints."""

import threading

def _jsonrpc(method, params=None, rpc_id=1):
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params:
        body["params"] = params
    return body


class TestMcpProtocol:
    def test_initialize(self, client):
        resp = client.post("/api/mcp", json=_jsonrpc("initialize"))
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["serverInfo"]["name"] == "hive"
        assert "tools" in result["capabilities"]

    def test_tools_list(self, client):
        resp = client.post("/api/mcp", json=_jsonrpc("tools/list"))
        assert resp.status_code == 200
        tools = resp.json()["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "ask_user" in names
        assert len(names) == 1

    def test_unknown_method(self, client):
        resp = client.post("/api/mcp", json=_jsonrpc("bogus/method"))
        assert resp.status_code == 200
        assert "error" in resp.json()
        assert resp.json()["error"]["code"] == -32601

    def test_notifications_initialized(self, client):
        body = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = client.post("/api/mcp", json=body)
        assert resp.status_code == 202

    def test_unknown_tool(self, client):
        resp = client.post("/api/mcp", json=_jsonrpc("tools/call", {
            "name": "bogus", "arguments": {},
        }))
        assert resp.status_code == 200
        assert resp.json()["result"]["isError"] is True


class TestAskUser:
    def test_answer_flow(self, client):
        """ask_user blocks until answer is posted, then returns it."""
        import json
        from hive.server.mcp import _pending

        result_holder = {}

        def _call_ask():
            resp = client.post("/api/mcp", json=_jsonrpc("tools/call", {
                "name": "ask_user",
                "arguments": {
                    "question": "Pick a color",
                    "options": ["red", "blue", "green"],
                    "mode": "select",
                },
            }))
            result_holder["resp"] = resp

        t = threading.Thread(target=_call_ask)
        t.start()

        import time
        for _ in range(50):
            if _pending:
                break
            time.sleep(0.1)
        assert _pending, "question never appeared in pending"

        qid = list(_pending.keys())[0]
        entry = _pending[qid]
        assert entry["question"] == "Pick a color"
        assert entry["options"] == ["red", "blue", "green"]

        # List pending questions
        resp = client.get("/api/mcp/questions")
        assert resp.status_code == 200
        questions = resp.json()["questions"]
        assert len(questions) == 1
        assert questions[0]["id"] == qid

        # Answer the question
        resp = client.post(f"/api/mcp/questions/{qid}/answer", json={"answer": "blue"})
        assert resp.status_code == 200

        t.join(timeout=5)
        assert "resp" in result_holder

        data = json.loads(result_holder["resp"].json()["result"]["content"][0]["text"])
        assert data["status"] == "answered"
        assert data["answer"] == "blue"

    def test_answer_not_found(self, client):
        resp = client.post("/api/mcp/questions/nonexistent/answer", json={"answer": "x"})
        assert resp.status_code == 404

    def test_confirm_mode(self, client):
        import json
        from hive.server.mcp import _pending
        _pending.clear()

        result_holder = {}

        def _call():
            resp = client.post("/api/mcp", json=_jsonrpc("tools/call", {
                "name": "ask_user",
                "arguments": {"question": "Delete this?", "mode": "confirm"},
            }))
            result_holder["resp"] = resp

        t = threading.Thread(target=_call)
        t.start()

        import time
        for _ in range(50):
            if _pending:
                break
            time.sleep(0.1)

        qid = list(_pending.keys())[0]
        client.post(f"/api/mcp/questions/{qid}/answer", json={"answer": "yes"})
        t.join(timeout=5)

        data = json.loads(result_holder["resp"].json()["result"]["content"][0]["text"])
        assert data["answer"] == "yes"
