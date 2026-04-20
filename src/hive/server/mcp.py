"""MCP (Model Context Protocol) HTTP server for hive tools.

Exposes hive-specific tools to agents via the MCP protocol. Attached
automatically when workspace agent sessions are created.

For ask_user, the handler blocks via asyncio.Event until the browser
user responds through the REST answer endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("hive.mcp")

router = APIRouter(prefix="/api/mcp")

QUESTION_TIMEOUT_S = float(os.environ.get("MCP_QUESTION_TIMEOUT", "300"))  # 5 min

# ---------------------------------------------------------------------------
# In-memory pending questions store
# ---------------------------------------------------------------------------

_pending: dict[str, dict[str, Any]] = {}
# key: question_id
# value: {"question": {...}, "answer": None, "event": asyncio.Event,
#          "session_id": str, "created_at": str}


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "ask_user",
        "description": (
            "Ask the user a question with multiple choice options. "
            "Always provide options for the user to choose from. Include 'Other...' as the last option to allow free-text input."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of options. Always include at least 2. Add 'Other...' as last option for custom input.",
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
]


# ---------------------------------------------------------------------------
# MCP protocol handler
# ---------------------------------------------------------------------------

@router.get("")
async def mcp_sse_endpoint(request: Request):
    """Handle GET requests — SSE transport needs an 'endpoint' event to know where to POST."""
    log.info("[mcp] GET SSE connect from %s", request.client)
    from fastapi.responses import StreamingResponse
    async def sse_stream():
        # Send endpoint as relative path — SSE transport resolves against connection URL
        yield "event: endpoint\ndata: /api/mcp\n\n"
        # Keep alive with heartbeats
        while True:
            yield ": heartbeat\n\n"
            await asyncio.sleep(15)
    return StreamingResponse(sse_stream(), media_type="text/event-stream")


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def mcp_catch_all(path: str, request: Request):
    """Catch-all for debugging — log any unexpected sub-path requests."""
    body = await request.body()
    log.warning("[mcp] unexpected %s /api/mcp/%s body=%s headers=%s", request.method, path, body[:500], dict(request.headers))
    return JSONResponse({"error": f"unknown path: /api/mcp/{path}"}, status_code=404)


@router.post("")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC endpoint. Handles initialize, tools/list, tools/call."""
    try:
        body = await request.json()
    except Exception:
        log.warning("[mcp] parse error from %s", request.client)
        return _jsonrpc_error(None, -32700, "Parse error")

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})
    log.info("[mcp] %s (id=%s)", method, rpc_id)

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
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            result = await _dispatch_tool(tool_name, args)
            return _jsonrpc_ok(rpc_id, {
                "content": [{"type": "text", "text": json.dumps(result) if isinstance(result, (dict, list)) else str(result)}],
            })
        except HTTPException as e:
            return _jsonrpc_ok(rpc_id, {
                "content": [{"type": "text", "text": f"Error: {e.detail}"}],
                "isError": True,
            })
        except Exception as e:
            log.exception("tool %s failed", tool_name)
            return _jsonrpc_ok(rpc_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })

    return _jsonrpc_error(rpc_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

async def _dispatch_tool(name: str, args: dict) -> Any:
    if name == "ask_user":
        return await _tool_ask_user(args)
    raise HTTPException(400, f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# ask_user — blocks until UI responds
# ---------------------------------------------------------------------------

async def _tool_ask_user(args: dict) -> Any:
    question = args.get("question", "")
    if not question:
        raise HTTPException(400, "question is required")

    qid = str(uuid.uuid4())
    event = asyncio.Event()
    _pending[qid] = {
        "id": qid,
        "question": question,
        "options": args.get("options"),
        "mode": args.get("mode", "select"),
        "answer": None,
        "event": event,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await asyncio.wait_for(event.wait(), timeout=QUESTION_TIMEOUT_S)
    except asyncio.TimeoutError:
        _pending.pop(qid, None)
        return {"status": "timeout", "message": "User did not respond in time"}

    entry = _pending.pop(qid, {})
    return {"status": "answered", "answer": entry.get("answer")}


# ---------------------------------------------------------------------------
# Question REST endpoints (for the UI)
# ---------------------------------------------------------------------------

@router.get("/questions")
async def list_pending_questions():
    """List all pending questions (for the UI to render)."""
    return {
        "questions": [
            {k: v for k, v in entry.items() if k != "event"}
            for entry in _pending.values()
            if entry.get("answer") is None
        ]
    }


@router.post("/questions/{question_id}/answer")
async def answer_question(
    question_id: str,
    request: Request,
):
    """Submit an answer to a pending question. Wakes up the blocked tool call."""
    entry = _pending.get(question_id)
    if not entry:
        raise HTTPException(404, "question not found or already answered")

    body = await request.json()
    answer = body.get("answer")
    if answer is None:
        raise HTTPException(400, "answer is required")

    entry["answer"] = answer
    entry["event"].set()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MCP_SESSION_ID = "hive-mcp-" + uuid.uuid4().hex[:12]
_MCP_HEADERS = {"mcp-session-id": _MCP_SESSION_ID}


def _jsonrpc_ok(rpc_id, result):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result}, headers=_MCP_HEADERS)


def _jsonrpc_error(rpc_id, code, message):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}, headers=_MCP_HEADERS)
