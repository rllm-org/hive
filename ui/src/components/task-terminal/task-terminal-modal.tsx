"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Modal, ModalCloseButton } from "@/components/shared/modal";
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

interface TaskTerminalModalProps {
  taskPath: string;
  open: boolean;
  onClose: () => void;
}

export function TaskTerminalModal({ taskPath, open, onClose }: TaskTerminalModalProps) {
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
    if (!open || !user) return;
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;
    void loadSandbox();
    void loadSessions();
  }, [open, user, loadSandbox, loadSessions]);

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
    // Clear UI immediately so old terminals unmount
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
    // Check if we already have a tab for this session
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
    // Remove tab if open
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
      // Don't remove the tab — session stays alive server-side
      void loadSessions();
    },
    [loadSessions],
  );

  if (!open) return null;

  if (!user) {
    return (
      <Modal onClose={onClose} maxWidth="max-w-md" className="overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
          <h2 className="text-sm font-semibold text-[var(--color-text)]">Terminal</h2>
          <ModalCloseButton onClick={onClose} />
        </div>
        <p className="p-6 text-sm text-[var(--color-text-secondary)]">Sign in to use the task sandbox terminal.</p>
      </Modal>
    );
  }

  const ready = sandbox?.status === "ready";
  const creating = sandbox?.status === "creating" || creatingSandbox;
  // Sessions not attached to a tab (available for reconnect)
  const detachedSessions = sessions.filter((s) => !tabs.some((t) => t.sessionId === s.id));

  return (
    <Modal onClose={onClose} maxWidth="max-w-[95vw]" className="overflow-hidden h-[90vh]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] shrink-0">
        <h2 className="text-sm font-semibold text-[var(--color-text)]">Sandbox terminal</h2>
        <div className="flex items-center gap-2">
          {ready && (
            <button
              type="button"
              onClick={() => void deleteSandbox()}
              className="px-2 py-1 text-xs text-[var(--color-text-tertiary)] hover:text-red-500 border border-[var(--color-border)] rounded hover:border-red-300 transition-colors"
            >
              Delete workspace
            </button>
          )}
          <ModalCloseButton onClick={onClose} />
        </div>
      </div>

      <div className="flex flex-col min-h-0 flex-1 overflow-hidden">
        {sandboxLoading && (
          <p className="p-4 text-sm text-[var(--color-text-secondary)]">Loading workspace…</p>
        )}

        {!sandboxLoading && !sandbox && !sandboxError && (
          <div className="p-4 space-y-3">
            <p className="text-sm text-[var(--color-text-secondary)]">
              Create a cloud workspace for this task to open an interactive terminal (Daytona).
            </p>
            <button
              type="button"
              onClick={() => void createSandbox()}
              disabled={creatingSandbox}
              className="px-3 py-1.5 text-sm font-medium bg-[var(--color-accent)] text-white rounded-md disabled:opacity-50"
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
          <>
            {/* Tab bar */}
            <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-[var(--color-border)] bg-[var(--color-layer-1)]">
              <button
                type="button"
                onClick={() => void newTerminal()}
                className="px-2 py-1 text-xs font-medium rounded border border-[var(--color-border)] hover:bg-[var(--color-layer-2)]"
              >
                + New terminal
              </button>
              {tabs.map((tab) => (
                <div key={tab.key} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setActiveKey(tab.key)}
                    className={`px-2 py-1 text-xs rounded ${
                      activeKey === tab.key
                        ? "bg-[var(--color-accent)] text-white"
                        : "bg-[var(--color-layer-2)] text-[var(--color-text)]"
                    }`}
                  >
                    {tab.title ?? `Session ${tab.sessionId}`}
                  </button>
                  <button
                    type="button"
                    aria-label="Close tab"
                    onClick={() => void closeSession(tab.sessionId)}
                    className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] text-xs px-1"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>

            {/* Terminal panes + detached session list */}
            <div className="flex-1 min-h-[360px] p-3 overflow-hidden">
              {tabs.length === 0 && detachedSessions.length === 0 && (
                <p className="text-sm text-[var(--color-text-tertiary)]">
                  Click &quot;New terminal&quot; to start a shell.
                </p>
              )}

              {/* Show detached sessions available for reconnect */}
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
                  className="h-full min-h-[320px]"
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
          </>
        )}
      </div>
    </Modal>
  );
}
