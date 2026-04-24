"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, apiPostJson } from "@/lib/api";
import { getAuthHeader } from "@/lib/auth";
import {
  classifyMessageContent,
  extractSseTag,
  extractToolCallId,
  extractToolName,
  extractToolResponse,
  iterSseBlocks,
  parseAcpPayload,
  parseSseData,
} from "@/lib/sse";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

export interface ToolCall {
  id: string;
  name: string;
  input: unknown;
  output: unknown | null;
  status: "pending" | "done" | "error";
}

export type TurnRole = "user" | "assistant" | "error";

export interface Turn {
  key: string;                 // client-local react key
  role: TurnRole;
  text: string;
  reasoning: string;
  toolCalls: ToolCall[];
  promptId: string | null;
  stopReason: string | null;
  streaming: boolean;
}

interface AgentSessionMeta {
  id: number;
  sdk_session_id: string;
  sdk_base_url: string;
  status: string;
  upstream_status?: { agent_busy?: boolean; active_rpc_id?: string | null };
}

interface LogEvent {
  event_type: string;
  payload: Record<string, unknown>;
  created_at?: string;
}

let turnSeq = 0;
const newTurnKey = () => `t${++turnSeq}`;

function emptyTurn(role: TurnRole, promptId: string | null, streaming = false): Turn {
  return {
    key: newTurnKey(),
    role,
    text: "",
    reasoning: "",
    toolCalls: [],
    promptId,
    stopReason: null,
    streaming,
  };
}

/** Locate (or create) the current assistant turn for a given promptId. */
function upsertAssistantTurn(turns: Turn[], promptId: string | null): [Turn[], number] {
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    if (t.role === "assistant" && t.promptId === promptId && t.streaming) {
      return [turns, i];
    }
  }
  const next = [...turns, emptyTurn("assistant", promptId, true)];
  return [next, next.length - 1];
}

/** Apply one typed log event (from GET /log) to a running list of turns. */
function applyLogEvent(turns: Turn[], e: LogEvent): Turn[] {
  const p = e.payload || {};
  const pid = (p.prompt_id as string) ?? null;
  switch (e.event_type) {
    case "user_message": {
      const t = emptyTurn("user", pid, false);
      t.text = (p.text as string) ?? "";
      return [...turns, t];
    }
    case "assistant_message": {
      let next = turns;
      let idx: number;
      [next, idx] = upsertAssistantTurn(next, pid);
      const t = { ...next[idx], text: ((p.text as string) ?? "") };
      const out = [...next];
      out[idx] = t;
      return out;
    }
    case "reasoning": {
      let next = turns;
      let idx: number;
      [next, idx] = upsertAssistantTurn(next, pid);
      const t = { ...next[idx], reasoning: ((p.text as string) ?? "") };
      const out = [...next];
      out[idx] = t;
      return out;
    }
    case "tool_call": {
      let next = turns;
      let idx: number;
      [next, idx] = upsertAssistantTurn(next, pid);
      const tc: ToolCall = {
        id: (p.tool_call_id as string) ?? `${pid ?? "p"}-${next[idx].toolCalls.length}`,
        name: (p.tool as string) ?? "tool",
        input: p.args ?? null,
        output: null,
        status: "pending",
      };
      const t = { ...next[idx], toolCalls: [...next[idx].toolCalls, tc] };
      const out = [...next]; out[idx] = t; return out;
    }
    case "tool_result": {
      let next = turns;
      let idx: number;
      [next, idx] = upsertAssistantTurn(next, pid);
      const id = (p.tool_call_id as string) ?? "";
      const turn = next[idx];
      const updated = turn.toolCalls.map((tc) =>
        tc.id === id ? { ...tc, output: p.result ?? null, status: "done" as const } : tc
      );
      const t = { ...turn, toolCalls: updated };
      const out = [...next]; out[idx] = t; return out;
    }
    case "turn_end": {
      let next = turns;
      let idx: number;
      [next, idx] = upsertAssistantTurn(next, pid);
      const t = { ...next[idx], streaming: false, stopReason: (p.stop_reason as string) ?? null };
      const out = [...next]; out[idx] = t; return out;
    }
    case "error": {
      const t = emptyTurn("error", pid, false);
      t.text = (p.message as string) ?? "error";
      return [...turns, t];
    }
    default:
      return turns;
  }
}

/** Apply one live ACP session/update notification to a running list of turns. */
function applyAcpUpdate(turns: Turn[], update: Record<string, unknown>, pid: string | null): Turn[] {
  const su = update.sessionUpdate as string | undefined;
  if (!su) return turns;

  // Text or reasoning deltas / chunks
  if (su === "agent_message_delta" || su === "agent_message_chunk") {
    const cls = classifyMessageContent(update.content);
    if (!cls) return turns;
    let next = turns; let idx: number;
    [next, idx] = upsertAssistantTurn(next, pid);
    const field = cls.kind === "reasoning" ? "reasoning" : "text";
    const t = { ...next[idx], [field]: next[idx][field] + cls.value };
    const out = [...next]; out[idx] = t; return out;
  }
  if (su === "agent_thought_chunk") {
    const cls = classifyMessageContent(update.content);
    if (!cls) return turns;
    let next = turns; let idx: number;
    [next, idx] = upsertAssistantTurn(next, pid);
    const t = { ...next[idx], reasoning: next[idx].reasoning + cls.value };
    const out = [...next]; out[idx] = t; return out;
  }

  // Tool call start
  if (su === "tool_call" || su === "execute_tool_started") {
    const id = extractToolCallId(update) ?? `${pid ?? "p"}-tc-${Date.now()}`;
    const name = extractToolName(update);
    let next = turns; let idx: number;
    [next, idx] = upsertAssistantTurn(next, pid);
    const existing = next[idx].toolCalls.find((c) => c.id === id);
    if (existing) return turns;
    const tc: ToolCall = {
      id, name, input: update.rawInput ?? null, output: null, status: "pending",
    };
    const t = { ...next[idx], toolCalls: [...next[idx].toolCalls, tc] };
    const out = [...next]; out[idx] = t; return out;
  }

  // Tool call update / completion
  if (su === "tool_call_update" || su === "execute_tool_completed") {
    const id = extractToolCallId(update);
    const response = extractToolResponse(update);
    if (!id) return turns;
    let next = turns; let idx: number;
    [next, idx] = upsertAssistantTurn(next, pid);
    const turn = next[idx];
    const updated = turn.toolCalls.map((tc) =>
      tc.id === id ? { ...tc, output: response ?? tc.output, status: "done" as const } : tc
    );
    const t = { ...turn, toolCalls: updated };
    const out = [...next]; out[idx] = t; return out;
  }

  // usage / commands — ignored in v1
  return turns;
}

function endStreamingTurn(turns: Turn[], pid: string | null, stopReason: string | null): Turn[] {
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    if (t.role === "assistant" && t.promptId === pid && t.streaming) {
      const updated = { ...t, streaming: false, stopReason };
      const out = [...turns]; out[i] = updated; return out;
    }
  }
  return turns;
}

export function useAgentSession(sessionId: number | null) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [meta, setMeta] = useState<AgentSessionMeta | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const loadedRef = useRef<number | null>(null);
  const sdkRef = useRef<{ baseUrl: string; sessionId: string } | null>(null);

  useEffect(() => {
    if (sessionId == null) return;
    if (loadedRef.current === sessionId) return;
    loadedRef.current = sessionId;

    let cancelled = false;
    setTurns([]);
    setError(null);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    (async () => {
      try {
        // Fetch session metadata (via Hive proxy — auth-gated)
        const session = await apiFetch<AgentSessionMeta>(`/agent-chat/sessions/${sessionId}`);
        if (cancelled) return;
        setMeta(session);
        setBusy(Boolean(session.upstream_status?.agent_busy));

        const sdkBase = session.sdk_base_url?.replace(/\/+$/, "");
        const sdkSid = session.sdk_session_id;
        if (!sdkBase || !sdkSid) {
          setError("agent-sdk URL not available");
          return;
        }
        sdkRef.current = { baseUrl: sdkBase, sessionId: sdkSid };

        // Cold-load history directly from agent-sdk
        try {
          const logResp = await fetch(`${sdkBase}/sessions/${sdkSid}/log?limit=500`, {
            signal: ctrl.signal,
          });
          if (logResp.ok) {
            const logData = await logResp.json();
            const events: LogEvent[] = logData.events ?? logData ?? [];
            let next: Turn[] = [];
            for (const ev of events) {
              next = applyLogEvent(next, ev);
            }
            if (!cancelled) setTurns(next);
          }
        } catch {
          // Log load failure is non-fatal — SSE will catch up
        }

        // Live SSE — connect directly to agent-sdk (no proxy hop)
        const resp = await fetch(`${sdkBase}/sessions/${sdkSid}/events`, {
          headers: { Accept: "text/event-stream" },
          signal: ctrl.signal,
        });
        if (!resp.ok) throw new Error(`events HTTP ${resp.status}`);

        for await (const block of iterSseBlocks(resp, ctrl.signal)) {
          if (ctrl.signal.aborted) break;
          const payload = parseSseData(block);
          if (!payload) continue;
          const tag = extractSseTag(block);
          const classified = parseAcpPayload(payload, tag);

          if (classified.kind === "update" && classified.data) {
            const params = ((payload.params ?? {}) as Record<string, unknown>);
            const pid = (params.promptId as string | undefined) ?? tag ?? null;
            setTurns((prev) => applyAcpUpdate(prev, classified.data!, pid));
            setBusy(true);
          } else if (classified.kind === "done_result" && classified.data) {
            const pid = (payload.id as string | undefined) ?? tag ?? null;
            const reason = (classified.data.stopReason as string | undefined) ?? null;
            setTurns((prev) => endStreamingTurn(prev, pid, reason));
            setBusy(false);
          } else if (classified.kind === "error" && classified.data) {
            const msg = (classified.data.message as string) ?? "agent error";
            setTurns((prev) => [...prev, { ...emptyTurn("error", null, false), text: msg }]);
            setBusy(false);
          }
        }
      } catch (e) {
        if (!ctrl.signal.aborted) {
          const msg = e instanceof Error ? e.message : String(e);
          if (msg) setError(msg);
        }
      }
    })();

    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [sessionId]);

  const sendPrompt = useCallback(async (text: string, opts?: { interrupt?: boolean }) => {
    if (sessionId == null || !text.trim()) return;
    setTurns((prev) => {
      const t = emptyTurn("user", null, false);
      t.text = text;
      return [...prev, t];
    });
    setBusy(true);
    const sdk = sdkRef.current;
    if (sdk) {
      // Send directly to agent-sdk
      await fetch(`${sdk.baseUrl}/sessions/${sdk.sessionId}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, interrupt: Boolean(opts?.interrupt) }),
      });
    } else {
      // Fallback to Hive proxy
      await apiPostJson(`/agent-chat/sessions/${sessionId}/message`, {
        text,
        interrupt: Boolean(opts?.interrupt),
      });
    }
  }, [sessionId]);

  const cancel = useCallback(async () => {
    if (sessionId == null) return;
    const sdk = sdkRef.current;
    if (sdk) {
      await fetch(`${sdk.baseUrl}/sessions/${sdk.sessionId}/cancel`, { method: "POST" });
    } else {
      await apiPostJson(`/agent-chat/sessions/${sessionId}/cancel`, {});
    }
  }, [sessionId]);

  return { turns, meta, busy, error, sendPrompt, cancel };
}
