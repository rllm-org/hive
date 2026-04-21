"""Lightweight MCP server for registering hive tools with agents.

Handles tool registration (initialize + tools/list) and blocking ask_user
tool calls — the HTTP response is held open until the user responds via
the chat UI.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/api/mcp")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "ask_user",
        "description": (
            "Ask the user one or more questions. Each question has options for the user to choose from. "
            "You can ask multiple questions at once — they will be shown as a paginated form. "
            "Include 'Other...' as the last option to allow free-text input."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "List of questions to ask. Each question is shown one at a time in a paginated widget.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question text",
                            },
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of options. Add 'Other...' as last option for custom input.",
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["select", "confirm", "multi_select", "text"],
                                "default": "select",
                                "description": "select: pick one, confirm: yes/no, multi_select: pick many, text: free input",
                            },
                        },
                        "required": ["question", "options"],
                    },
                },
            },
            "required": ["questions"],
        },
    },
]

# ---------------------------------------------------------------------------
# Pending ask_user responses
# ---------------------------------------------------------------------------

ASK_USER_TIMEOUT = 600  # 10 minutes

# ask_id -> asyncio.Future[str]
_pending_asks: dict[str, asyncio.Future] = {}


def submit_ask_response(ask_id: str, answer: str) -> bool:
    """Resolve a pending ask_user call. Returns True if found."""
    fut = _pending_asks.get(ask_id)
    if fut and not fut.done():
        fut.set_result(answer)
        return True
    return False


def get_pending_ask_ids() -> list[str]:
    """Return all pending (unresolved) ask IDs."""
    return [k for k, f in _pending_asks.items() if not f.done()]


# ---------------------------------------------------------------------------
# SSE endpoint (for MCP SSE transport)
# ---------------------------------------------------------------------------

@router.get("")
async def mcp_sse_endpoint(request: Request):
    """SSE stream with endpoint event for MCP SSE transport."""
    log.info("[mcp] GET SSE connect")
    async def sse_stream():
        yield "event: endpoint\ndata: /api/mcp\n\n"
        while True:
            yield ": heartbeat\n\n"
            await asyncio.sleep(15)
    return StreamingResponse(sse_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# JSON-RPC endpoint
# ---------------------------------------------------------------------------

@router.post("")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC — handles initialize, tools/list, and tools/call."""
    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error")

    rpc_id = body.get("id")
    method = body.get("method", "")
    print(f"[mcp] {method} (id={rpc_id})", flush=True)

    if method == "initialize":
        return _jsonrpc_ok(rpc_id, {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "hive", "version": "0.1.0"},
        })

    if method == "notifications/initialized":
        return JSONResponse(status_code=202, content={}, headers=_MCP_HEADERS)

    if method == "tools/list":
        return _jsonrpc_ok(rpc_id, {"tools": TOOLS})

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name", "")

        if tool_name == "ask_user":
            return await _handle_ask_user(rpc_id, params)

        return _jsonrpc_ok(rpc_id, {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
        })

    return _jsonrpc_error(rpc_id, -32601, f"Method not found: {method}")


async def _handle_ask_user(rpc_id, params):
    """Block until the user responds or timeout."""
    ask_id = uuid.uuid4().hex[:12]
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[str] = loop.create_future()
    _pending_asks[ask_id] = fut

    print(f"[mcp] ask_user blocking (ask_id={ask_id})", flush=True)

    try:
        answer = await asyncio.wait_for(fut, timeout=ASK_USER_TIMEOUT)
        print(f"[mcp] ask_user resolved (ask_id={ask_id})", flush=True)
        return _jsonrpc_ok(rpc_id, {
            "content": [{"type": "text", "text": answer}],
        })
    except asyncio.TimeoutError:
        print(f"[mcp] ask_user timed out (ask_id={ask_id})", flush=True)
        return _jsonrpc_ok(rpc_id, {
            "content": [{"type": "text", "text": "User did not respond in time."}],
        })
    finally:
        _pending_asks.pop(ask_id, None)


# ---------------------------------------------------------------------------
# Response endpoint — called by the frontend when the user answers
# ---------------------------------------------------------------------------

@router.post("/ask/respond")
async def ask_respond(request: Request):
    """Submit an answer to a pending ask_user call.

    Body: { "ask_id": "...", "answer": "..." }
    If ask_id is omitted, resolves the most recent pending ask.
    """
    body = await request.json()
    ask_id = body.get("ask_id")
    answer = body.get("answer", "")

    if not ask_id:
        # Resolve the most recent pending ask
        pending = get_pending_ask_ids()
        if not pending:
            return JSONResponse({"ok": False, "reason": "no pending ask"}, status_code=404)
        ask_id = pending[-1]

    if submit_ask_response(ask_id, answer):
        return JSONResponse({"ok": True, "ask_id": ask_id})
    return JSONResponse({"ok": False, "reason": "ask not found or already resolved"}, status_code=404)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MCP_SESSION_ID = "hive-mcp-" + uuid.uuid4().hex[:12]
_MCP_HEADERS = {"mcp-session-id": _MCP_SESSION_ID}


def _jsonrpc_ok(rpc_id, result):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result}, headers=_MCP_HEADERS)


def _jsonrpc_error(rpc_id, code, message):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}, headers=_MCP_HEADERS)
