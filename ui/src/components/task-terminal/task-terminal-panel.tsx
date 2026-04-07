"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthHeader, useAuth } from "@/lib/auth";
import { apiDelete, apiFetch, apiPostJson } from "@/lib/api";
import type {
  SandboxInfo,
  SandboxSessionCreateResponse,
  SandboxTerminalSessionRow,
} from "@/types/api";
import { XtermPane } from "./xterm-pane";

type Tab = {
  key: string;
  sessionId: number;
  title: string | null;
  ticket: string;
};

interface TaskTerminalPanelProps {
  taskPath: string;
  active: boolean;
}

export function TaskTerminalPanel({ taskPath, active }: TaskTerminalPanelProps) {
  const { user } = useAuth();
  const [sandbox, setSandbox] = useState<SandboxInfo | null>(null);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);
  const [creatingSandbox, setCreatingSandbox] = useState(false);
  const [sessions, setSessions] = useState<SandboxTerminalSessionRow[]>([]);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const loadSandbox = useCallback(async () => {
    setSandboxError(null);
    setSandboxLoading(true);
    try {
      const data = await apiFetch<SandboxInfo>(`/tasks/${taskPath}/sandbox`);
      setSandbox(data);
    } catch (e) {
      setSandbox(null);
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("404")) {
        setSandboxError(null);
      } else {
        setSandboxError(msg || "Failed to load sandbox");
      }
    } finally {
      setSandboxLoading(false);
    }
  }, [taskPath]);

  const loadSessions = useCallback(async () => {
    try {
      const data = await apiFetch<{ sessions: SandboxTerminalSessionRow[] }>(
        `/tasks/${taskPath}/sandbox/sessions`,
      );
      setSessions(data.sessions);
    } catch {
      setSessions([]);
    }
  }, [taskPath]);

  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (!active || !user) return;
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;
    void loadSandbox();
    void loadSessions();
  }, [active, user, loadSandbox, loadSessions]);

  const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

  const createSandbox = async () => {
    setCreatingSandbox(true);
    setSandboxError(null);
    try {
      const res = await fetch(`${API_BASE}/tasks/${taskPath}/sandbox`, {
        method: "POST",
        headers: { ...getAuthHeader() },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => null);
        throw new Error(typeof d?.detail === "string" ? d.detail : `HTTP ${res.status}`);
      }
      const data = (await res.json()) as SandboxInfo;
      setSandbox(data);
      if (data.status === "creating") {
        const t = setInterval(async () => {
          try {
            const s = await apiFetch<SandboxInfo>(`/tasks/${taskPath}/sandbox`);
            setSandbox(s);
            if (s.status === "ready" || s.status === "error") {
              clearInterval(t);
              setCreatingSandbox(false);
            }
          } catch {
            clearInterval(t);
            setCreatingSandbox(false);
          }
        }, 2000);
        return;
      }
    } catch (e) {
      setSandboxError(e instanceof Error ? e.message : "Failed to create sandbox");
    } finally {
      setCreatingSandbox(false);
    }
  };

  const deleteSandbox = async () => {
    if (!confirm("Delete this workspace? All terminal sessions will be lost.")) return;
    setSandboxError(null);
    setTabs([]);
    setActiveKey(null);
    setSessions([]);
    setSandbox(null);
    setSandboxLoading(false);
    initialLoadDone.current = false;
    try {
      await apiDelete(`/tasks/${taskPath}/sandbox`, getAuthHeader());
    } catch (e) {
      setSandboxError(e instanceof Error ? e.message : "Failed to delete workspace");
    }
  };

  const newTerminal = async () => {
    setSandboxError(null);
    try {
      const created = await apiPostJson<SandboxSessionCreateResponse>(
        `/tasks/${taskPath}/sandbox/sessions`,
        {},
        getAuthHeader(),
      );
      const key = `t-${created.id}-${Date.now()}`;
      setTabs((prev) => [
        ...prev,
        { key, sessionId: created.id, title: created.title ?? `Terminal ${created.id}`, ticket: created.ticket },
      ]);
      setActiveKey(key);
      await loadSessions();
    } catch (e) {
      setSandboxError(e instanceof Error ? e.message : "Failed to open terminal session");
    }
  };

  const reconnectSession = async (session: SandboxTerminalSessionRow) => {
    const existing = tabs.find((t) => t.sessionId === session.id);
    if (existing) {
      setActiveKey(existing.key);
      return;
    }
    setSandboxError(null);
    try {
      const data = await apiPostJson<{ ticket: string }>(
        `/tasks/${taskPath}/sandbox/sessions/${session.id}/ticket`,
        {},
        getAuthHeader(),
      );
      const key = `t-${session.id}-${Date.now()}`;
      setTabs((prev) => [
        ...prev,
        { key, sessionId: session.id, title: session.title ?? `Terminal ${session.id}`, ticket: data.ticket },
      ]);
      setActiveKey(key);
    } catch (e) {
      setSandboxError(e instanceof Error ? e.message : "Failed to reconnect");
    }
  };

  const closeSession = async (sessionId: number) => {
    setTabs((prev) => {
      const tab = prev.find((t) => t.sessionId === sessionId);
      if (tab && activeKey === tab.key) {
        setActiveKey(null);
      }
      return prev.filter((t) => t.sessionId !== sessionId);
    });
    try {
      await apiDelete(`/tasks/${taskPath}/sandbox/sessions/${sessionId}`, getAuthHeader());
      await loadSessions();
    } catch {
      /* ignore */
    }
  };

  const onPaneDisconnected = useCallback(
    (_key: string, _sessionId: number) => {
      void loadSessions();
    },
    [loadSessions],
  );

  if (!user) {
    return (
      <div className="flex items-center justify-center h-full p-6 text-sm text-[var(--color-text-secondary)]">
        Sign in to use the task sandbox terminal.
      </div>
    );
  }

  const ready = sandbox?.status === "ready";
  const creating = sandbox?.status === "creating" || creatingSandbox;
  const detachedSessions = sessions.filter((s) => !tabs.some((t) => t.sessionId === s.id));

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      <div className="flex flex-col min-h-0 flex-1 overflow-hidden">
        {sandboxLoading && (
          <p className="p-4 text-sm text-[var(--color-text-secondary)]">Loading workspace…</p>
        )}

        {!sandboxLoading && !sandbox && !sandboxError && (
          <div className="p-6 space-y-4">
            <p className="text-sm text-[var(--color-text-secondary)]">
              Create a cloud workspace for this task to open an interactive terminal (Daytona).
            </p>
            <button
              type="button"
              onClick={() => void createSandbox()}
              disabled={creatingSandbox}
              className="px-6 py-3 text-sm font-medium bg-[var(--color-accent)] text-white rounded-md disabled:opacity-50 hover:bg-[var(--color-accent-hover)] transition-colors"
            >
              {creatingSandbox ? "Creating…" : "Create workspace"}
            </button>
          </div>
        )}

        {sandbox?.status === "error" && (
          <p className="p-4 text-sm text-red-500">{sandbox.error_message ?? "Workspace error"}</p>
        )}

        {sandboxError && <p className="p-4 text-sm text-red-500">{sandboxError}</p>}

        {creating && (
          <p className="p-4 text-sm text-[var(--color-text-secondary)]">Provisioning workspace…</p>
        )}

        {ready && (
          <div className="flex-1 min-h-0 flex flex-col p-2 overflow-hidden">
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden border border-[var(--color-border)] rounded">
            {/* Zed-inspired terminal tab bar */}
            <div className="flex items-stretch h-9 bg-[#2f3349] font-[family-name:var(--font-ibm-plex-mono)] text-[12px] select-none">
              <div className="flex items-stretch min-w-0 overflow-x-auto">
                {tabs.map((tab) => {
                  const isActive = activeKey === tab.key;
                  return (
                    <div
                      key={tab.key}
                      onClick={() => setActiveKey(tab.key)}
                      className={`group flex items-center gap-2 pl-3 pr-2 cursor-pointer transition-colors ${
                        isActive
                          ? "bg-[#1a1b26] text-[#c0caf5]"
                          : "bg-transparent text-[#9aa5ce] hover:text-[#c0caf5] hover:bg-[#1a1b26]/50"
                      }`}
                      style={{ minWidth: 120 }}
                    >
                      <span className="truncate flex-1">{tab.title ?? `session ${tab.sessionId}`}</span>
                      <button
                        type="button"
                        aria-label="Close tab"
                        onClick={(e) => { e.stopPropagation(); void closeSession(tab.sessionId); }}
                        className={`shrink-0 w-4 h-4 flex items-center justify-center rounded-sm transition-opacity ${
                          isActive ? "opacity-60 hover:opacity-100 hover:bg-[#414868]" : "opacity-0 group-hover:opacity-60 hover:opacity-100 hover:bg-[#414868]"
                        }`}
                      >
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                          <path d="M1 1l6 6M7 1L1 7" />
                        </svg>
                      </button>
                    </div>
                  );
                })}
                <button
                  type="button"
                  onClick={() => void newTerminal()}
                  aria-label="New terminal"
                  title="New terminal"
                  className="shrink-0 px-3 text-[#9aa5ce] hover:text-[#c0caf5] hover:bg-[#1a1b26]/50 transition-colors flex items-center"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <path d="M6 2v8M2 6h8" />
                  </svg>
                </button>
              </div>
              <div className="ml-auto flex items-center pr-2">
                <button
                  type="button"
                  onClick={() => void deleteSandbox()}
                  aria-label="Destroy workspace"
                  title="Destroy workspace"
                  className="w-7 h-7 text-[#9aa5ce] hover:text-[#f7768e] hover:bg-[#1a1b26]/50 rounded-sm transition-colors flex items-center justify-center"
                >
                  <svg width="13" height="13" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M2 3h8M4.5 3V2a1 1 0 011-1h1a1 1 0 011 1v1M3 3l.5 7a1 1 0 001 1h3a1 1 0 001-1L9 3" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="flex-1 min-h-0 bg-[#1a1b26] overflow-hidden">
              {tabs.length === 0 && detachedSessions.length === 0 && (
                <p className="text-sm text-[var(--color-text-tertiary)]">
                  Click &quot;New terminal&quot; to start a shell.
                </p>
              )}

              {tabs.length === 0 && detachedSessions.length > 0 && (
                <div className="space-y-2 mb-4">
                  <p className="text-xs font-medium text-[var(--color-text-secondary)]">
                    Active sessions ({detachedSessions.length})
                  </p>
                  {detachedSessions.map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center justify-between px-3 py-2 border border-[var(--color-border)] rounded bg-[var(--color-layer-1)]"
                    >
                      <span className="text-sm text-[var(--color-text)]">
                        {s.title ?? `Terminal ${s.id}`}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void reconnectSession(s)}
                          className="px-2 py-1 text-xs font-medium rounded bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)]"
                        >
                          Reconnect
                        </button>
                        <button
                          type="button"
                          onClick={() => void closeSession(s.id)}
                          className="px-2 py-1 text-xs font-medium rounded border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-red-500 hover:border-red-300"
                        >
                          Close
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {tabs.map((tab) => (
                <div
                  key={tab.key}
                  className="h-full min-h-0"
                  style={{ display: activeKey === tab.key ? "block" : "none" }}
                >
                  <XtermPane
                    taskPath={taskPath}
                    ticket={tab.ticket}
                    active={activeKey === tab.key}
                    onDisconnected={() => onPaneDisconnected(tab.key, tab.sessionId)}
                  />
                </div>
              ))}
            </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
