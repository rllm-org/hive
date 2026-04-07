"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";
import { getAuthHeader } from "./auth";
import { apiFetch, apiPostJson, apiDelete } from "./api";
import type {
  SandboxInfo,
  SandboxSessionCreateResponse,
  SandboxTerminalSessionRow,
} from "@/types/api";
import * as store from "./terminal-store";

type Tab = {
  key: string;
  sessionId: number;
  title: string | null;
  ticket: string;
  storeKey: string;
};

interface TaskTerminalState {
  sandbox: SandboxInfo | null;
  sandboxLoading: boolean;
  sandboxError: string | null;
  creatingSandbox: boolean;
  sessions: SandboxTerminalSessionRow[];
  tabs: Tab[];
  activeKey: string | null;
  initialLoadDone: boolean;
}

function makeInitialState(): TaskTerminalState {
  return {
    sandbox: null,
    sandboxLoading: false,
    sandboxError: null,
    creatingSandbox: false,
    sessions: [],
    tabs: [],
    activeKey: null,
    initialLoadDone: false,
  };
}

interface TerminalContextValue {
  getState: (taskPath: string) => TaskTerminalState;
  initTask: (taskPath: string) => void;
  createSandbox: (taskPath: string) => Promise<void>;
  deleteSandbox: (taskPath: string) => Promise<void>;
  newTerminal: (taskPath: string) => Promise<void>;
  reconnectSession: (taskPath: string, session: SandboxTerminalSessionRow) => Promise<void>;
  closeSession: (taskPath: string, sessionId: number) => Promise<void>;
  setActiveKey: (taskPath: string, key: string | null) => void;
  loadSessions: (taskPath: string) => Promise<void>;
}

const TerminalContext = createContext<TerminalContextValue | null>(null);

export function useTerminal() {
  const ctx = useContext(TerminalContext);
  if (!ctx) throw new Error("useTerminal must be used within TerminalProvider");
  return ctx;
}

export function TerminalProvider({ children }: { children: React.ReactNode }) {
  // Map of taskPath -> state. Using useState with a Map so updates trigger re-renders.
  const [stateMap, setStateMap] = useState<Map<string, TaskTerminalState>>(new Map());
  const stateMapRef = useRef(stateMap);
  stateMapRef.current = stateMap;

  const getOrCreate = useCallback((taskPath: string): TaskTerminalState => {
    return stateMapRef.current.get(taskPath) ?? makeInitialState();
  }, []);

  const update = useCallback((taskPath: string, patch: Partial<TaskTerminalState>) => {
    setStateMap((prev) => {
      const next = new Map(prev);
      const current = next.get(taskPath) ?? makeInitialState();
      next.set(taskPath, { ...current, ...patch });
      return next;
    });
  }, []);

  const updateFn = useCallback((taskPath: string, fn: (s: TaskTerminalState) => Partial<TaskTerminalState>) => {
    setStateMap((prev) => {
      const next = new Map(prev);
      const current = next.get(taskPath) ?? makeInitialState();
      next.set(taskPath, { ...current, ...fn(current) });
      return next;
    });
  }, []);

  const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

  const loadSessionsImpl = useCallback(async (taskPath: string) => {
    try {
      const data = await apiFetch<{ sessions: SandboxTerminalSessionRow[] }>(
        `/tasks/${taskPath}/sandbox/sessions`,
      );
      update(taskPath, { sessions: data.sessions });
    } catch {
      update(taskPath, { sessions: [] });
    }
  }, [update]);

  const initTask = useCallback((taskPath: string) => {
    const s = getOrCreate(taskPath);
    if (s.initialLoadDone) return;
    update(taskPath, { initialLoadDone: true, sandboxLoading: true, sandboxError: null });

    (async () => {
      try {
        const data = await apiFetch<SandboxInfo>(`/tasks/${taskPath}/sandbox`);
        update(taskPath, { sandbox: data, sandboxLoading: false });
      } catch (e) {
        const msg = e instanceof Error ? e.message : "";
        update(taskPath, {
          sandbox: null,
          sandboxLoading: false,
          sandboxError: msg.includes("404") ? null : msg || "Failed to load sandbox",
        });
      }
    })();

    void loadSessionsImpl(taskPath);
  }, [getOrCreate, update, loadSessionsImpl]);

  const createSandbox = useCallback(async (taskPath: string) => {
    update(taskPath, { creatingSandbox: true, sandboxError: null });
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
      update(taskPath, { sandbox: data });
      if (data.status === "creating") {
        const t = setInterval(async () => {
          try {
            const s = await apiFetch<SandboxInfo>(`/tasks/${taskPath}/sandbox`);
            update(taskPath, { sandbox: s });
            if (s.status === "ready" || s.status === "error") {
              clearInterval(t);
              update(taskPath, { creatingSandbox: false });
            }
          } catch {
            clearInterval(t);
            update(taskPath, { creatingSandbox: false });
          }
        }, 2000);
        return;
      }
    } catch (e) {
      update(taskPath, { sandboxError: e instanceof Error ? e.message : "Failed to create sandbox" });
    } finally {
      update(taskPath, { creatingSandbox: false });
    }
  }, [API_BASE, update]);

  const deleteSandbox = useCallback(async (taskPath: string) => {
    if (!confirm("Delete this workspace? All terminal sessions will be lost.")) return;
    // Close all store sessions for this task
    const s = getOrCreate(taskPath);
    for (const tab of s.tabs) {
      store.closeSession(tab.storeKey);
    }
    update(taskPath, {
      sandboxError: null,
      tabs: [],
      activeKey: null,
      sessions: [],
      sandbox: null,
      sandboxLoading: false,
      initialLoadDone: false,
    });
    try {
      await apiDelete(`/tasks/${taskPath}/sandbox`, getAuthHeader());
    } catch (e) {
      update(taskPath, { sandboxError: e instanceof Error ? e.message : "Failed to delete workspace" });
    }
  }, [getOrCreate, update]);

  const newTerminal = useCallback(async (taskPath: string) => {
    update(taskPath, { sandboxError: null });
    try {
      const created = await apiPostJson<SandboxSessionCreateResponse>(
        `/tasks/${taskPath}/sandbox/sessions`,
        {},
        getAuthHeader(),
      );
      const storeKey = store.openSession(taskPath, created.ticket);
      const key = `t-${created.id}-${Date.now()}`;
      updateFn(taskPath, (s) => ({
        tabs: [...s.tabs, { key, sessionId: created.id, title: created.title ?? "zsh", ticket: created.ticket, storeKey }],
        activeKey: key,
      }));
      await loadSessionsImpl(taskPath);
    } catch (e) {
      update(taskPath, { sandboxError: e instanceof Error ? e.message : "Failed to open terminal session" });
    }
  }, [update, updateFn, loadSessionsImpl]);

  const reconnectSession = useCallback(async (taskPath: string, session: SandboxTerminalSessionRow) => {
    const s = getOrCreate(taskPath);
    const existing = s.tabs.find((t) => t.sessionId === session.id);
    if (existing) {
      update(taskPath, { activeKey: existing.key });
      return;
    }
    update(taskPath, { sandboxError: null });
    try {
      const data = await apiPostJson<{ ticket: string }>(
        `/tasks/${taskPath}/sandbox/sessions/${session.id}/ticket`,
        {},
        getAuthHeader(),
      );
      const storeKey = store.openSession(taskPath, data.ticket);
      const key = `t-${session.id}-${Date.now()}`;
      updateFn(taskPath, (s) => ({
        tabs: [...s.tabs, { key, sessionId: session.id, title: session.title ?? "zsh", ticket: data.ticket, storeKey }],
        activeKey: key,
      }));
    } catch (e) {
      update(taskPath, { sandboxError: e instanceof Error ? e.message : "Failed to reconnect" });
    }
  }, [getOrCreate, update, updateFn]);

  const closeSessionImpl = useCallback(async (taskPath: string, sessionId: number) => {
    updateFn(taskPath, (s) => {
      const tab = s.tabs.find((t) => t.sessionId === sessionId);
      if (tab) store.closeSession(tab.storeKey);
      return {
        tabs: s.tabs.filter((t) => t.sessionId !== sessionId),
        activeKey: tab && s.activeKey === tab.key ? null : s.activeKey,
      };
    });
    try {
      await apiDelete(`/tasks/${taskPath}/sandbox/sessions/${sessionId}`, getAuthHeader());
      await loadSessionsImpl(taskPath);
    } catch {
      /* ignore */
    }
  }, [updateFn, loadSessionsImpl]);

  const setActiveKeyImpl = useCallback((taskPath: string, key: string | null) => {
    update(taskPath, { activeKey: key });
  }, [update]);

  const getState = useCallback((taskPath: string): TaskTerminalState => {
    return stateMap.get(taskPath) ?? makeInitialState();
  }, [stateMap]);

  const value: TerminalContextValue = {
    getState,
    initTask,
    createSandbox,
    deleteSandbox,
    newTerminal,
    reconnectSession,
    closeSession: closeSessionImpl,
    setActiveKey: setActiveKeyImpl,
    loadSessions: loadSessionsImpl,
  };

  return (
    <TerminalContext.Provider value={value}>
      {children}
    </TerminalContext.Provider>
  );
}
