"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@/lib/auth";
import { useTerminal } from "@/lib/terminal-context";
import { XtermPane } from "./xterm-pane";

interface TaskTerminalPanelProps {
  taskPath: string;
  active: boolean;
}

export function TaskTerminalPanel({ taskPath, active }: TaskTerminalPanelProps) {
  const { user } = useAuth();
  const ctx = useTerminal();
  const state = ctx.getState(taskPath);

  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (!active || !user) return;
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;
    ctx.initTask(taskPath);
  }, [active, user, taskPath, ctx]);

  // Auto-open a default terminal when sandbox becomes ready and there are no sessions
  const autoOpenedRef = useRef(false);
  useEffect(() => {
    if (autoOpenedRef.current) return;
    if (state.sandbox?.status !== "ready") return;
    if (state.tabs.length > 0 || state.sessions.length > 0) return;
    autoOpenedRef.current = true;
    void ctx.newTerminal(taskPath);
  }, [state.sandbox?.status, state.tabs.length, state.sessions.length, taskPath, ctx]);

  if (!user) {
    return (
      <div className="flex items-center justify-center h-full p-6 text-sm text-[var(--color-text-secondary)]">
        Sign in to use the task sandbox terminal.
      </div>
    );
  }

  const { sandbox, sandboxLoading, sandboxError, creatingSandbox, sessions, tabs, activeKey } = state;
  const ready = sandbox?.status === "ready";
  const creating = sandbox?.status === "creating" || creatingSandbox;
  const detachedSessions = sessions.filter((s) => !tabs.some((t) => t.sessionId === s.id));

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      <div className="flex flex-col min-h-0 flex-1 overflow-hidden">
        {sandboxLoading && (
          <p className="p-4 text-sm text-[var(--color-text-secondary)]">Loading workspace…</p>
        )}

        {!sandboxLoading && (!sandbox || sandbox.status === "creating") && !sandboxError && (
          <div className="p-6 space-y-4">
            <div className="flex items-start gap-2 px-3 py-2 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 text-xs text-amber-800 dark:text-amber-300">
              <span className="font-semibold">Beta:</span>
              <span>Opencode and Claude Code installed in the sandbox.</span>
            </div>
            <p className="text-sm text-[var(--color-text-secondary)]">
              Create a cloud workspace for this task to open an interactive terminal (Daytona).
            </p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => void ctx.createSandbox(taskPath)}
                disabled={creating}
                className="px-6 py-3 text-sm font-medium bg-[var(--color-accent)] text-white rounded-md disabled:opacity-60 hover:bg-[var(--color-accent-hover)] transition-colors"
              >
                Create workspace
              </button>
              {creating && (
                <span className="inline-block w-4 h-4 border-2 border-[var(--color-text-tertiary)] border-t-transparent rounded-full animate-spin" aria-label="Creating" />
              )}
            </div>
          </div>
        )}

        {sandbox?.status === "error" && (
          <p className="p-4 text-sm text-red-500">{sandbox.error_message ?? "Workspace error"}</p>
        )}

        {sandboxError && <p className="p-4 text-sm text-red-500">{sandboxError}</p>}

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
                      onClick={() => ctx.setActiveKey(taskPath, tab.key)}
                      className={`group flex items-center gap-2 pl-3 pr-2 cursor-pointer transition-colors ${
                        isActive
                          ? "bg-[#1a1b26] text-[#c0caf5]"
                          : "bg-transparent text-[#9aa5ce] hover:text-[#c0caf5] hover:bg-[#1a1b26]/50"
                      }`}
                      style={{ minWidth: 120 }}
                    >
                      <span className="truncate flex-1">{tab.title ?? "zsh"}</span>
                      <button
                        type="button"
                        aria-label="Close tab"
                        onClick={(e) => { e.stopPropagation(); void ctx.closeSession(taskPath, tab.sessionId); }}
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
                  onClick={() => void ctx.newTerminal(taskPath)}
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
                  onClick={() => void ctx.deleteSandbox(taskPath)}
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

            <div className="flex-1 min-h-0 bg-[#1a1b26] overflow-hidden relative">
              {tabs.length === 0 && detachedSessions.length > 0 && (
                <div className="px-4 py-4 space-y-2 font-[family-name:var(--font-ibm-plex-mono)]">
                  <p className="text-[11px] uppercase tracking-wider text-[#7a82a8]">
                    Active sessions ({detachedSessions.length})
                  </p>
                  {detachedSessions.map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center justify-between px-3 py-2 border border-[#414868] rounded bg-[#24283b]"
                    >
                      <span className="text-[13px] text-[#c0caf5]">
                        {s.title ?? "zsh"}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void ctx.reconnectSession(taskPath, s)}
                          className="px-2.5 py-1 text-[11px] font-medium rounded bg-[#7aa2f7] text-[#1a1b26] hover:bg-[#9ab8f9] transition-colors"
                        >
                          Reconnect
                        </button>
                        <button
                          type="button"
                          onClick={() => void ctx.closeSession(taskPath, s.id)}
                          className="px-2.5 py-1 text-[11px] font-medium rounded border border-[#414868] text-[#9aa5ce] hover:text-[#f7768e] hover:border-[#f7768e] transition-colors"
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
                  className="absolute inset-0"
                  style={{ visibility: activeKey === tab.key ? "visible" : "hidden" }}
                >
                  <XtermPane
                    storeKey={tab.storeKey}
                    active={activeKey === tab.key}
                    onDisconnected={() => void ctx.loadSessions(taskPath)}
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
