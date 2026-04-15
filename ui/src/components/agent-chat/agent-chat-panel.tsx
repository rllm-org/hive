"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, apiPostJson } from "@/lib/api";
import { useAgentSession } from "@/hooks/use-agent-session";
import { SessionBootstrap } from "./session-bootstrap";
import { TurnStream } from "./turn-stream";
import { Composer } from "./composer";

interface AgentChatPanelProps {
  owner: string;
  slug: string;
  /** When false, the panel is hidden (but the SSE stream is not torn down). */
  active?: boolean;
}

interface SessionSummary {
  id: number;
  sdk_session_id: string;
  agent_kind: string;
  title: string | null;
  status: string;
  last_activity: string | null;
  created_at: string;
}

export function AgentChatPanel({ owner, slug, active = true }: AgentChatPanelProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await apiFetch<{ sessions: SessionSummary[] }>(
        `/tasks/${owner}/${slug}/agent-chat/sessions`
      );
      const live = (r.sessions ?? []).filter((s) => s.status !== "closed");
      setSessions(live);
      setSelectedId((cur) => (cur != null && live.some((s) => s.id === cur) ? cur : live[0]?.id ?? null));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [owner, slug]);

  useEffect(() => { refresh(); }, [refresh]);

  const createSession = useCallback(async (agentKind: string) => {
    setCreating(true); setErr(null);
    try {
      const s = await apiPostJson<SessionSummary>(
        `/tasks/${owner}/${slug}/agent-chat/sessions`,
        { agent_kind: agentKind }
      );
      setSessions((prev) => [s, ...prev]);
      setSelectedId(s.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }, [owner, slug]);

  const { turns, busy, sendPrompt, cancel, error: streamError } = useAgentSession(selectedId);

  if (!active) return null;

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--color-surface)] border border-[var(--color-border)]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--color-border)] text-xs">
        <div className="flex items-center gap-2">
          <span className="font-medium">Agent chat</span>
          {selectedId != null && (
            <span className="text-[var(--color-text-secondary)]">#{selectedId}</span>
          )}
          {busy && <span className="text-amber-500">• thinking…</span>}
        </div>
        <div className="flex items-center gap-2">
          {busy && (
            <button
              className="px-2 py-0.5 border border-[var(--color-border)] hover:bg-[var(--color-layer-2)]"
              onClick={cancel}
            >Stop</button>
          )}
          <button
            className="px-2 py-0.5 border border-[var(--color-border)] hover:bg-[var(--color-layer-2)]"
            onClick={refresh}
          >Refresh</button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-sm text-[var(--color-text-secondary)]">Loading…</div>
        ) : selectedId == null ? (
          <SessionBootstrap onStart={createSession} starting={creating} error={err} />
        ) : (
          <TurnStream turns={turns} />
        )}
      </div>

      {/* Composer */}
      {selectedId != null && (
        <Composer
          disabled={creating}
          busy={busy}
          onSend={(text, interrupt) => sendPrompt(text, { interrupt })}
        />
      )}

      {(err || streamError) && (
        <div className="px-3 py-1 text-xs text-red-500 border-t border-[var(--color-border)]">
          {err ?? streamError}
        </div>
      )}
    </div>
  );
}
