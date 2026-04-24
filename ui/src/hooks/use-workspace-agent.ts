"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api";
import { SDK_BASE } from "@/lib/sdk";
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

export interface SlashCommand {
  name: string;
  description: string;
  input?: { hint: string } | null;
}

export type MessagePart =
  | { type: "text"; content: string }
  | { type: "thinking"; content: string }
  | { type: "tool"; id: string; name: string; status: "pending" | "done" | "error"; title?: string; input?: unknown; output?: unknown };

export interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
  parts?: MessagePart[];
  streaming?: boolean;
}

export interface AgentState {
  messages: ChatMessage[];
  commands: SlashCommand[];
  isLoading: boolean;
  cancelling: boolean;
  connecting: boolean;
  error: string | null;
  sessionId: string | null;
}

const EMPTY_STATE: AgentState = {
  messages: [],
  commands: [],
  isLoading: false,
  cancelling: false,
  connecting: false,
  error: null,
  sessionId: null,
};

// ---------------------------------------------------------------------------
// Cold-load history from session log
// ---------------------------------------------------------------------------

function buildMessagesFromLog(events: Array<{ event_type: string; payload: Record<string, unknown> }>): ChatMessage[] {
  const msgs: ChatMessage[] = [];
  const getOrCreateAssistant = (): ChatMessage => {
    const last = msgs[msgs.length - 1];
    if (last?.role === "assistant") return last;
    const m: ChatMessage = { role: "assistant", content: "", parts: [] };
    msgs.push(m);
    return m;
  };
  for (const ev of events) {
    if (ev.event_type === "user_message") {
      msgs.push({ role: "user", content: (ev.payload.text as string) ?? "" });
    } else if (ev.event_type === "assistant_message") {
      const text = (ev.payload.text as string) ?? "";
      const m = getOrCreateAssistant();
      m.content += text;
      (m.parts ??= []).push({ type: "text", content: text });
    } else if (ev.event_type === "reasoning") {
      const text = (ev.payload.text as string) ?? "";
      if (text) {
        const m = getOrCreateAssistant();
        const parts = (m.parts ??= []);
        const last = parts[parts.length - 1];
        if (last?.type === "thinking") {
          last.content += text;
        } else {
          parts.push({ type: "thinking", content: text });
        }
      }
    } else if (ev.event_type === "tool_call") {
      const m = getOrCreateAssistant();
      (m.parts ??= []).push({
        type: "tool",
        id: (ev.payload.tool_call_id as string) ?? `tc-${msgs.length}`,
        name: (ev.payload.tool as string) ?? "tool",
        status: "pending",
        title: (ev.payload.title as string) ?? undefined,
        input: ev.payload.args ?? undefined,
      });
    } else if (ev.event_type === "tool_result") {
      const m = getOrCreateAssistant();
      const parts = (m.parts ??= []);
      const tcId = (ev.payload.tool_call_id as string) ?? "";
      const title = (ev.payload.title as string) ?? undefined;
      const idx = parts.findLastIndex((p) => p.type === "tool" && (p.id === tcId || p.status === "pending"));
      if (idx >= 0 && parts[idx].type === "tool") {
        parts[idx] = { ...parts[idx], status: "done", output: ev.payload.result ?? undefined, ...(title ? { title } : {}) } as MessagePart;
      }
    } else if (ev.event_type === "error") {
      msgs.push({ role: "error", content: (ev.payload.message as string) ?? "error" });
    }
  }
  // Fix ordering: log may store reasoning after text, but at runtime
  // thinking appears before text. Swap adjacent (text, thinking) pairs.
  for (const m of msgs) {
    if (m.role === "assistant" && m.parts && m.parts.length > 1) {
      for (let i = 0; i < m.parts.length - 1; i++) {
        if (m.parts[i].type === "text" && m.parts[i + 1].type === "thinking") {
          [m.parts[i], m.parts[i + 1]] = [m.parts[i + 1], m.parts[i]];
        }
      }
    }
  }
  return msgs;
}

// ---------------------------------------------------------------------------
// SSE event processor — applies one SSE block to the current messages
// ---------------------------------------------------------------------------

type MsgUpdater = (fn: (prev: ChatMessage[]) => ChatMessage[]) => void;
type CmdUpdater = (cmds: SlashCommand[]) => void;
type LoadUpdater = (loading: boolean) => void;

function processSseBlock(
  block: string,
  setMessages: MsgUpdater,
  setCommands: CmdUpdater,
  setIsLoading: LoadUpdater,
) {
  const payload = parseSseData(block);
  if (!payload) return;

  // No client-side session filtering needed: agent-sdk's /events stream is
  // already scoped per-session via the per-SessionState upstream URL
  // (/v1/acp/{acp_session_id}) — each subscriber only sees its own events.

  const tag = extractSseTag(block);
  const classified = parseAcpPayload(payload, tag);

  if (classified.kind === "update" && classified.data) {
    const su = classified.data.sessionUpdate as string | undefined;

    if (su === "agent_message_delta" || su === "agent_message_chunk") {
      const cls = classifyMessageContent(classified.data.content);
      if (!cls) { /* skip */ }
      else if (cls.kind === "text") {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming) {
            const parts = [...(last.parts ?? [])];
            const lastPart = parts[parts.length - 1];
            if (lastPart?.type === "text") {
              parts[parts.length - 1] = { ...lastPart, content: lastPart.content + cls.value };
            } else {
              parts.push({ type: "text", content: cls.value });
            }
            return [...prev.slice(0, -1), { ...last, content: last.content + cls.value, parts }];
          }
          return [...prev, {
            role: "assistant" as const, content: cls.value, streaming: true,
            parts: [{ type: "text" as const, content: cls.value }],
          }];
        });
      } else if (cls.kind === "reasoning") {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming) {
            const parts = [...(last.parts ?? [])];
            const lastPart = parts[parts.length - 1];
            if (lastPart?.type === "thinking") {
              parts[parts.length - 1] = { ...lastPart, content: lastPart.content + cls.value };
            } else {
              parts.push({ type: "thinking", content: cls.value });
            }
            return [...prev.slice(0, -1), { ...last, parts }];
          }
          return [...prev, {
            role: "assistant" as const, content: "", streaming: true,
            parts: [{ type: "thinking" as const, content: cls.value }],
          }];
        });
      }
    } else if (su === "agent_thought_chunk") {
      const content = classified.data.content as Record<string, unknown> | undefined;
      const text = (content?.text as string) ?? (content?.thinking as string) ?? "";
      if (text) {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming) {
            const parts = [...(last.parts ?? [])];
            const lastPart = parts[parts.length - 1];
            if (lastPart?.type === "thinking") {
              parts[parts.length - 1] = { ...lastPart, content: lastPart.content + text };
            } else {
              parts.push({ type: "thinking", content: text });
            }
            return [...prev.slice(0, -1), { ...last, parts }];
          }
          return [...prev, {
            role: "assistant" as const, content: "", streaming: true,
            parts: [{ type: "thinking" as const, content: text }],
          }];
        });
      }
    } else if (su === "available_commands_update") {
      const cmds = classified.data.availableCommands as SlashCommand[] | undefined;
      if (Array.isArray(cmds)) setCommands(cmds);
    } else if (su === "tool_call" || su === "execute_tool_started") {
      const name = extractToolName(classified.data);
      const title = (classified.data.title as string) ?? "";
      const input = classified.data.rawInput ?? classified.data.input ?? classified.data.arguments ?? undefined;
      const tcId = extractToolCallId(classified.data) ?? `tc-${Date.now()}`;
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant" && last.streaming) {
          const parts = [...(last.parts ?? [])];
          if (parts.some((p) => p.type === "tool" && p.id === tcId)) return prev;
          parts.push({ type: "tool", id: tcId, name, status: "pending", title, input });
          return [...prev.slice(0, -1), { ...last, parts }];
        }
        return [...prev, {
          role: "assistant" as const, content: "", streaming: true,
          parts: [{ type: "tool" as const, id: tcId, name, status: "pending" as const, title, input }],
        }];
      });
    } else if (su === "tool_call_update" || su === "execute_tool_completed") {
      const tcId = extractToolCallId(classified.data) ?? "";
      const title = (classified.data.title as string) ?? "";
      const output = classified.data.rawOutput ?? extractToolResponse(classified.data) ?? undefined;
      const rawInput = classified.data.rawInput ?? undefined;
      const status = (classified.data.status as string) === "failed" ? "error" as const : "done" as const;
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant" && last.streaming && last.parts) {
          const parts = last.parts.map((p) =>
            p.type === "tool" && (p.id === tcId || (tcId === "" && p.status === "pending"))
              ? { ...p, status, ...(title ? { title } : {}), ...(output !== undefined ? { output } : {}), ...(rawInput !== undefined ? { input: rawInput } : {}) }
              : p
          );
          return [...prev.slice(0, -1), { ...last, parts }];
        }
        return prev;
      });
    }
    setIsLoading(true);
  } else if (classified.kind === "done_result") {
    // ACP sends intermediate done_result events between tool calls within
    // the same turn. Only mark as done if no tools are still pending.
    let turnDone = true;
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last?.role === "assistant" && last.streaming) {
        const hasPending = last.parts?.some((p) => p.type === "tool" && p.status === "pending");
        if (hasPending) {
          turnDone = false;
          return prev;
        }
        return [...prev.slice(0, -1), { ...last, streaming: false }];
      }
      return prev;
    });
    if (turnDone) setIsLoading(false);
  } else if (classified.kind === "error" && classified.data) {
    const msg = (classified.data.message as string) ?? "agent error";
    setMessages((prev) => [...prev, { role: "error", content: msg }]);
    setIsLoading(false);
  }
}

// ---------------------------------------------------------------------------
// Multi-agent hook — each agent has its own SSE connection and state
// ---------------------------------------------------------------------------

interface AgentConnection {
  abort: AbortController;
  sdkSid: string;
}

export function useWorkspaceAgents(
  workspaceId: string | number | null,
  agentIds: string[],
) {
  const [states, setStates] = useState<Record<string, AgentState>>({});
  const connectionsRef = useRef<Record<string, AgentConnection>>({});
  const activeIdsRef = useRef<Set<string>>(new Set());

  // Per-agent state updaters
  const updateAgent = useCallback((agentId: string, patch: Partial<AgentState>) => {
    setStates((prev) => ({
      ...prev,
      [agentId]: { ...(prev[agentId] ?? EMPTY_STATE), ...patch },
    }));
  }, []);

  const updateMessages = useCallback((agentId: string, fn: (prev: ChatMessage[]) => ChatMessage[]) => {
    setStates((prev) => {
      const s = prev[agentId] ?? EMPTY_STATE;
      return { ...prev, [agentId]: { ...s, messages: fn(s.messages) } };
    });
  }, []);

  // Start SSE stream for an agent (reusable by both initial connect and reconnect after cancel)
  const startSseStream = useCallback((agentId: string, sdkSid: string, ctrl: AbortController) => {
    (async () => {
      try {
        const sseResp = await fetch(`${SDK_BASE}/sessions/${sdkSid}/events`, {
          headers: { Accept: "text/event-stream" },
          signal: ctrl.signal,
        });
        if (!sseResp.ok || ctrl.signal.aborted) return;

        for await (const block of iterSseBlocks(sseResp, ctrl.signal)) {
          if (ctrl.signal.aborted) break;
          processSseBlock(
            block,
            (fn) => updateMessages(agentId, fn),
            (cmds) => updateAgent(agentId, { commands: cmds }),
            (loading) => updateAgent(agentId, { isLoading: loading }),
          );
        }
      } catch (e) {
        if (!ctrl.signal.aborted) {
          console.warn("[sse] stream dropped for", agentId, "— reconnecting in 2s");
        }
      }
      // Auto-reconnect if not intentionally aborted
      if (!ctrl.signal.aborted) {
        const conn = connectionsRef.current[agentId];
        if (conn) {
          await new Promise((r) => setTimeout(r, 2000));
          if (!ctrl.signal.aborted) {
            const newCtrl = new AbortController();
            connectionsRef.current[agentId] = { ...conn, abort: newCtrl };
            startSseStream(agentId, sdkSid, newCtrl);
          }
        }
      }
    })();
  }, [updateAgent, updateMessages]);

  // Start/stop connections based on agentIds
  useEffect(() => {
    if (workspaceId == null) return;

    const currentIds = new Set(agentIds);
    const prevIds = activeIdsRef.current;

    // Stop connections for removed agents
    for (const id of prevIds) {
      if (!currentIds.has(id)) {
        connectionsRef.current[id]?.abort.abort();
        delete connectionsRef.current[id];
        prevIds.delete(id);
      }
    }

    // Start connections for new agents
    for (const agentId of agentIds) {
      if (prevIds.has(agentId)) continue;
      prevIds.add(agentId);

      // Initialize state
      updateAgent(agentId, { ...EMPTY_STATE, connecting: true });

      const ctrl = new AbortController();

      (async () => {
        try {
          if (!SDK_BASE) {
            updateAgent(agentId, { connecting: false, error: "NEXT_PUBLIC_AGENT_SDK_BASE_URL not set" });
            return;
          }

          const row = await apiFetch<{ session_id: string | null }>(
            `/workspaces/${workspaceId}/agents/${agentId}`,
          );
          if (ctrl.signal.aborted) return;
          const sdkSid = row.session_id;
          if (!sdkSid) throw new Error("agent has no session");

          connectionsRef.current[agentId] = { abort: ctrl, sdkSid };
          updateAgent(agentId, { sessionId: sdkSid });

          // Cold-load history
          try {
            const logResp = await fetch(`${SDK_BASE}/sessions/${sdkSid}/log?limit=500`, { signal: ctrl.signal });
            if (logResp.ok) {
              const logData = await logResp.json();
              const events = logData.events ?? logData ?? [];
              const msgs = buildMessagesFromLog(events);
              if (!ctrl.signal.aborted) updateAgent(agentId, { messages: msgs });
            }
          } catch { /* non-fatal */ }

          updateAgent(agentId, { connecting: false });

          // Live SSE
          startSseStream(agentId, sdkSid, ctrl);
        } catch (e) {
          if (!ctrl.signal.aborted) {
            updateAgent(agentId, { error: e instanceof Error ? e.message : String(e), connecting: false });
          }
        }
      })();
    }

    // Cleanup all on unmount
    return () => {
      for (const id of Object.keys(connectionsRef.current)) {
        connectionsRef.current[id]?.abort.abort();
      }
      connectionsRef.current = {};
      activeIdsRef.current = new Set();
    };
  }, [workspaceId, agentIds.join(","), updateAgent, updateMessages, startSseStream]);

  const sendMessage = useCallback(async (agentId: string, text: string) => {
    if (!text.trim()) return;
    updateMessages(agentId, (prev) => [...prev, { role: "user", content: text }]);
    updateAgent(agentId, { isLoading: true });
    let sdkSid: string | undefined = connectionsRef.current[agentId]?.sdkSid;
    if (!sdkSid && workspaceId != null) {
      try {
        const row = await apiFetch<{ session_id: string | null }>(
          `/workspaces/${workspaceId}/agents/${agentId}`,
        );
        sdkSid = row.session_id ?? undefined;
      } catch { /* fall through */ }
    }
    if (!sdkSid) {
      updateAgent(agentId, { isLoading: false, error: "agent has no session" });
      return;
    }
    try {
      const res = await fetch(`${SDK_BASE}/sessions/${sdkSid}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) {
        updateAgent(agentId, { isLoading: false, error: `send failed: ${res.status}` });
      }
    } catch (e) {
      updateAgent(agentId, { isLoading: false, error: `send failed: ${String(e)}` });
    }
  }, [updateMessages, updateAgent, workspaceId]);

  const cancel = useCallback(async (agentId: string) => {
    const conn = connectionsRef.current[agentId];
    if (!conn) return;

    updateAgent(agentId, { cancelling: true });

    try {
      const res = await fetch(`${SDK_BASE}/sessions/${conn.sdkSid}/cancel`, { method: "POST" });
      if (res.ok) {
        updateAgent(agentId, { cancelling: false });
        return;
      }
    } catch {
      // Network error
    }

    // Failed — reshow the stop button so user can try again
    updateAgent(agentId, { cancelling: false });
  }, [updateAgent]);

  const setModel = useCallback(async (agentId: string, model: string) => {
    const conn = connectionsRef.current[agentId];
    if (!conn) throw new Error("set_model: agent not connected");
    const res = await fetch(`${SDK_BASE}/sessions/${conn.sdkSid}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    });
    if (!res.ok) {
      let detail = "";
      try { const body = await res.json(); if (body.error) detail = `: ${body.error}`; } catch {}
      throw new Error(`set_model failed (${res.status})${detail}`);
    }
  }, []);

  return { states, sendMessage, cancel, setModel };
}

// ---------------------------------------------------------------------------
// Backward-compat wrapper — single agent (used by workspace page for now)
// ---------------------------------------------------------------------------

export function useWorkspaceAgent(workspaceId: string | number | null, agentId: string | null) {
  const agentIds = agentId ? [agentId] : [];
  const { states, sendMessage: _sendMessage, cancel: _cancel } = useWorkspaceAgents(workspaceId, agentIds);
  const state = agentId ? states[agentId] ?? EMPTY_STATE : EMPTY_STATE;

  const sendMessage = useCallback(async (text: string) => {
    if (agentId) await _sendMessage(agentId, text);
  }, [agentId, _sendMessage]);

  const cancel = useCallback(async () => {
    if (agentId) await _cancel(agentId);
  }, [agentId, _cancel]);

  return {
    messages: state.messages,
    commands: state.commands,
    isLoading: state.isLoading,
    connecting: state.connecting,
    error: state.error,
    sendMessage,
    cancel,
    sessionId: state.sessionId,
  };
}
