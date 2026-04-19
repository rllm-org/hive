"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiPostJson } from "@/lib/api";
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
  content: string;       // plain text for user/error, or full text for backward compat
  parts?: MessagePart[]; // assistant turn: interleaved text + tool parts
  streaming?: boolean;
}

export function useWorkspaceAgent(workspaceId: string | number | null, agentId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [commands, setCommands] = useState<SlashCommand[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sdkRef = useRef<{ baseUrl: string; sessionId: string } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const connectedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    // Require both workspace and an active agent to connect
    if (workspaceId == null || !agentId) {
      connectedKeyRef.current = null;
      setMessages([]);
      sdkRef.current = null;
      return;
    }
    const key = `${workspaceId}:${agentId}`;
    if (connectedKeyRef.current === key) return;
    connectedKeyRef.current = key;
    setMessages([]);
    sdkRef.current = null;

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    (async () => {
      setConnecting(true);
      setError(null);
      try {
        const resp = await apiPostJson<{ sdk_session_id: string; sdk_base_url: string }>(
          `/workspaces/${workspaceId}/agents/${agentId}/connect`,
          {}
        );
        if (ctrl.signal.aborted) return;
        const sdkBase = resp.sdk_base_url?.replace(/\/+$/, "");
        const sdkSid = resp.sdk_session_id;
        if (!sdkBase || !sdkSid) {
          setError("Agent SDK not configured");
          setConnecting(false);
          return;
        }
        sdkRef.current = { baseUrl: sdkBase, sessionId: sdkSid };

        // Cold-load history
        try {
          const logResp = await fetch(`${sdkBase}/sessions/${sdkSid}/log?limit=500`, {
            signal: ctrl.signal,
          });
          if (logResp.ok) {
            const logData = await logResp.json();
            const events: Array<{ event_type: string; payload: Record<string, unknown> }> =
              logData.events ?? logData ?? [];
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
                  input: ev.payload.args ?? undefined,
                });
              } else if (ev.event_type === "tool_result") {
                const m = getOrCreateAssistant();
                const parts = (m.parts ??= []);
                const tcId = (ev.payload.tool_call_id as string) ?? "";
                const idx = parts.findLastIndex((p) => p.type === "tool" && (p.id === tcId || p.status === "pending"));
                if (idx >= 0 && parts[idx].type === "tool") {
                  parts[idx] = { ...parts[idx], status: "done", output: ev.payload.result ?? undefined } as MessagePart;
                }
              } else if (ev.event_type === "error") {
                msgs.push({ role: "error", content: (ev.payload.message as string) ?? "error" });
              }
            }
            if (!ctrl.signal.aborted) setMessages(msgs);
          }
        } catch { /* non-fatal */ }

        setConnecting(false);

        // Live SSE — connect directly to agent-sdk
        const sseResp = await fetch(`${sdkBase}/sessions/${sdkSid}/events`, {
          headers: { Accept: "text/event-stream" },
          signal: ctrl.signal,
        });
        if (!sseResp.ok) throw new Error(`events HTTP ${sseResp.status}`);

        // Fetch available commands from session status (cached by agent-sdk)
        fetch(`${sdkBase}/sessions/${sdkSid}/status`, { signal: ctrl.signal })
          .then((r) => r.ok ? r.json() : null)
          .then((data) => {
            if (data?.available_commands && !ctrl.signal.aborted) {
              setCommands(data.available_commands);
            }
          })
          .catch(() => {});

        for await (const block of iterSseBlocks(sseResp, ctrl.signal)) {
          if (ctrl.signal.aborted) break;
          const payload = parseSseData(block);
          if (!payload) continue;
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
              const input = classified.data.rawInput ?? undefined;
              const tcId = extractToolCallId(classified.data) ?? `tc-${Date.now()}`;
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === "assistant" && last.streaming) {
                  const parts = [...(last.parts ?? [])];
                  // Skip if we already have this tool call ID
                  if (parts.some((p) => p.type === "tool" && p.id === tcId)) {
                    return prev;
                  }
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
              const status = (classified.data.status as string) === "failed" ? "error" as const : "done" as const;
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === "assistant" && last.streaming && last.parts) {
                  const parts = last.parts.map((p) =>
                    p.type === "tool" && (p.id === tcId || (tcId === "" && p.status === "pending"))
                      ? { ...p, status, ...(title ? { title } : {}), ...(output !== undefined ? { output } : {}) }
                      : p
                  );
                  return [...prev.slice(0, -1), { ...last, parts }];
                }
                return prev;
              });
            }
            setIsLoading(true);
          } else if (classified.kind === "done_result") {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === "assistant" && last.streaming) {
                return [...prev.slice(0, -1), { ...last, streaming: false }];
              }
              return prev;
            });
            setIsLoading(false);
          } else if (classified.kind === "error" && classified.data) {
            const msg = (classified.data.message as string) ?? "agent error";
            setMessages((prev) => [...prev, { role: "error", content: msg }]);
            setIsLoading(false);
          }
        }
      } catch (e) {
        if (!ctrl.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e));
          setConnecting(false);
        }
      }
    })();

    return () => { ctrl.abort(); };
  }, [workspaceId, agentId]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim()) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsLoading(true);
    const sdk = sdkRef.current;
    if (sdk) {
      await fetch(`${sdk.baseUrl}/sessions/${sdk.sessionId}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
    }
  }, []);

  const cancel = useCallback(async () => {
    const sdk = sdkRef.current;
    if (sdk) {
      await fetch(`${sdk.baseUrl}/sessions/${sdk.sessionId}/cancel`, { method: "POST" });
    }
  }, []);

  return { messages, commands, isLoading, connecting, error, sendMessage, cancel, sdkBaseUrl: sdkRef.current?.baseUrl ?? null, sdkSessionId: sdkRef.current?.sessionId ?? null };
}
