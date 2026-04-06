"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, apiPostJson, apiDelete } from "@/lib/api";

type SandboxInfo = {
  id: string;
  status: string;
  provider: string;
  daytona_sandbox_id?: string | null;
  error_message?: string | null;
  created_at?: string;
};

export function SandboxPanel({ taskId, enabled }: { taskId: string; enabled: boolean }) {
  const [sandbox, setSandbox] = useState<SandboxInfo | null | undefined>(undefined);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [provider, setProvider] = useState("claude_code");
  const [autoAccept, setAutoAccept] = useState(false);
  const [message, setMessage] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const data = await apiFetch<{ sandbox: SandboxInfo | null }>(`/tasks/${taskId}/sandbox`);
      setSandbox(data.sandbox ?? null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sandbox");
      setSandbox(null);
    }
  }, [taskId, enabled]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const ensureSandbox = async () => {
    setLoading(true);
    setError(null);
    try {
      await apiPostJson(`/tasks/${taskId}/sandbox`, { provider });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const startSession = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiPostJson<{ session_id: string }>(`/tasks/${taskId}/sandbox/sessions`, {
        provider,
        approval_mode: autoAccept ? "auto_accept" : "guarded",
      });
      setSessionId(data.session_id);
      setEvents((prev) => [...prev, `session ${data.session_id} started`]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!sessionId || !message.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await apiPostJson(`/tasks/${taskId}/sandbox/sessions/${sessionId}/messages`, { message });
      setEvents((prev) => [...prev, `> ${message}`]);
      setMessage("");
      const ev = await apiFetch<{ events: { type: string; data: Record<string, unknown> }[] }>(
        `/tasks/${taskId}/sandbox/sessions/${sessionId}/events?offset=0&limit=50`
      );
      for (const x of ev.events) {
        setEvents((p) => [...p, `${x.type}: ${JSON.stringify(x.data)}`]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const stopSandbox = async () => {
    setLoading(true);
    try {
      await apiPostJson(`/tasks/${taskId}/sandbox/stop`, {});
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const removeSandbox = async () => {
    setLoading(true);
    try {
      await apiDelete(`/tasks/${taskId}/sandbox`);
      setSandbox(null);
      setSessionId(null);
      setEvents([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  if (!enabled) return null;

  return (
    <div className="border border-[var(--color-border)] rounded-lg p-4 space-y-3 bg-[var(--color-layer-1)]">
      <div className="text-xs font-bold uppercase tracking-wide text-[var(--color-text-secondary)]">
        Sandbox (Daytona)
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
      <div className="flex flex-wrap gap-2 items-center text-xs">
        <label className="text-[var(--color-text-secondary)]">Provider</label>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-[var(--color-text)]"
        >
          <option value="claude_code">Claude Code</option>
          <option value="codex">Codex</option>
          <option value="opencode">OpenCode</option>
        </select>
        <label className="flex items-center gap-1 cursor-pointer">
          <input type="checkbox" checked={autoAccept} onChange={(e) => setAutoAccept(e.target.checked)} />
          Auto-accept (dangerous)
        </label>
      </div>
      <div className="text-xs text-[var(--color-text-secondary)]">
        {sandbox === undefined && "Loading…"}
        {sandbox === null && "No sandbox yet."}
        {sandbox && (
          <>
            Status: <span className="text-[var(--color-accent)] font-mono">{sandbox.status}</span>
            {sandbox.error_message && <span className="text-red-500 ml-2">{sandbox.error_message}</span>}
          </>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={ensureSandbox}
          className="px-3 py-1.5 text-xs font-medium bg-[var(--color-accent)] text-white disabled:opacity-50"
        >
          {loading ? "…" : "Start / resume sandbox"}
        </button>
        <button
          type="button"
          disabled={loading || !sandbox}
          onClick={startSession}
          className="px-3 py-1.5 text-xs border border-[var(--color-border)] disabled:opacity-50"
        >
          New session
        </button>
        <button type="button" disabled={loading || !sandbox} onClick={stopSandbox} className="px-3 py-1.5 text-xs border border-[var(--color-border)] disabled:opacity-50">
          Stop
        </button>
        <button type="button" disabled={loading || !sandbox} onClick={removeSandbox} className="px-3 py-1.5 text-xs text-red-500 border border-red-500/40 disabled:opacity-50">
          Delete sandbox
        </button>
      </div>
      {sessionId && (
        <div className="space-y-2">
          <div className="text-[10px] font-mono text-[var(--color-text-tertiary)]">session {sessionId}</div>
          <div className="flex gap-2">
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Message to agent…"
              className="flex-1 px-2 py-1.5 text-xs border border-[var(--color-border)] bg-[var(--color-bg)]"
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            />
            <button type="button" disabled={loading} onClick={sendMessage} className="px-3 py-1.5 text-xs bg-[var(--color-text)] text-[var(--color-bg)] disabled:opacity-50">
              Send
            </button>
          </div>
        </div>
      )}
      {events.length > 0 && (
        <pre className="text-[10px] font-mono max-h-40 overflow-y-auto whitespace-pre-wrap text-[var(--color-text-secondary)] border border-[var(--color-border)] p-2">
          {events.join("\n")}
        </pre>
      )}
    </div>
  );
}
