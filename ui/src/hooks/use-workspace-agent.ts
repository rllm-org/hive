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

export interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
  toolName?: string;
  reasoning?: string;
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
            for (const ev of events) {
              if (ev.event_type === "user_message") {
                msgs.push({ role: "user", content: (ev.payload.text as string) ?? "" });
              } else if (ev.event_type === "assistant_message") {
                msgs.push({ role: "assistant", content: (ev.payload.text as string) ?? "" });
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
              if (cls && cls.kind === "text") {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.role === "assistant" && last.streaming && !last.toolName) {
                    return [...prev.slice(0, -1), { ...last, content: last.content + cls.value }];
                  }
                  // After a tool call, start a new assistant message
                  return [...prev, { role: "assistant", content: cls.value, streaming: true }];
                });
              }
            } else if (su === "available_commands_update") {
              const cmds = classified.data.availableCommands as SlashCommand[] | undefined;
              if (Array.isArray(cmds)) setCommands(cmds);
            } else if (su === "tool_call" || su === "execute_tool_started") {
              const name = extractToolName(classified.data);
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last?.role === "assistant" && last.streaming) {
                  return [...prev.slice(0, -1), { ...last, toolName: name }];
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
