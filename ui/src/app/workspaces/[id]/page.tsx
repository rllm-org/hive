"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { LuArrowLeft } from "react-icons/lu";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch, apiPostJson, apiDelete } from "@/lib/api";
import { getAuthHeader, useAuth } from "@/lib/auth";
import { TextShimmer } from "@/components/text-shimmer";
import { AskUserWidget, type AskUserData } from "@/components/chat/ask-user-widget";
import { ThinkingBlock } from "@/components/shared/thinking-block";
import { ToolCallCard } from "@/components/shared/tool-call-card";
import { FileTree, FsPromptModal } from "@/components/shared/file-tree";
import { AgentTabBar } from "@/components/shared/agent-tab-bar";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";
import BoringAvatar from "boring-avatars";

const AVATAR_COLORS = ["#92A1C6", "#146A7C", "#F0AB3D", "#C271B4", "#C20D90"];

function HighlightSlash({ text, validCommands }: { text: string; validCommands: Set<string> }) {
  return (
    <>
      {text.split(/((?:^|(?<=\s))\/[\w:-]+)/).map((part, i) =>
        /^\/[\w:-]+$/.test(part) && validCommands.has(part.slice(1))
          ? <span key={i} className="text-[var(--color-accent)]">{part}</span>
          : <span key={i}>{part}</span>
      )}
    </>
  );
}

import type { MessagePart } from "@/hooks/use-workspace-agent";

interface ModelInfo {
  id: string;
  display_name?: string;
  description?: string;
}

const DEFAULT_MODEL = "claude-sonnet-4-6";

function CreateAgentModal({
  existingNames,
  onClose,
  onCreate,
  submitting,
}: {
  existingNames: string[];
  onClose: () => void;
  onCreate: (name?: string) => Promise<{ id: string } | undefined>;
  submitting: boolean;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const { claudeStatus } = useAuth();
  const [name, setName] = useState(() => {
    const set = new Set(existingNames);
    let x = 1;
    while (set.has(`agent-${x}`)) x++;
    return `agent-${x}`;
  });
  const [error, setError] = useState<string | null>(null);
  const [claudeConnected, setClaudeConnected] = useState<boolean | null>(null);

  useEffect(() => {
    claudeStatus().then((s) => setClaudeConnected(s.connected)).catch(() => {});
  }, [claudeStatus]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const submit = async () => {
    const trimmed = name.trim().toLowerCase();
    if (!trimmed) { setError("Name required"); return; }
    setError(null);
    try {
      await onCreate(trimmed);
      onClose();
    } catch (err) {
      if (err instanceof Error && err.message.includes("402")) {
        window.location.href = "/profile?tab=settings";
        return;
      }
      setError(err instanceof Error ? err.message : "Failed");
    }
  };

  return (
    <>
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[420px] flex flex-col animate-fade-in" style={{ borderRadius: 6 }}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-base font-semibold text-[var(--color-text)]">Add Agent</h2>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>
        <div className="px-6 py-5 space-y-3">
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Agent Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value.toLowerCase())}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
              placeholder="agent-1"
              className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
              style={{ outline: "none", boxShadow: "none" }}
              autoFocus
            />
            <p className="text-xs text-[var(--color-text-tertiary)] mt-1.5">3–40 lowercase letters, digits, or hyphens.</p>
          </div>

          {/* Options */}
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Options</label>
            {claudeConnected === true ? (
              <div className="flex items-center gap-3 p-3 border border-[var(--color-accent)] bg-[var(--color-accent)]/5">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/claude-icon.png" alt="Claude" width={28} height={28} className="rounded-full shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-[var(--color-text)]">Claude Code</div>
                  <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5">Powered by your Claude subscription</div>
                </div>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 text-emerald-500">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>
            ) : (
              <button
                onClick={() => window.location.href = "/profile?tab=settings"}
                className="w-full flex items-center gap-3 p-3 border border-dashed border-[var(--color-border)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent)]/5 transition-colors text-left"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/claude-icon.png" alt="Claude" width={28} height={28} className="rounded-full shrink-0 opacity-60" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-[var(--color-text)]">Connect Claude</div>
                  <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5">Link your Claude account in Settings to create agents</div>
                </div>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="shrink-0 text-[var(--color-text-tertiary)]">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                </svg>
              </button>
            )}
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={submitting || claudeConnected === false}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
            >
              {submitting ? "Creating…" : "Create"}
            </button>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
import { WorkspaceEditor, type OpenFile } from "@/components/workspace-editor";
import { useWorkspaceAgents, type AgentState } from "@/hooks/use-workspace-agent";
import { useWorkspaceFiles, type FsTreeNode } from "@/hooks/use-workspace-files";

interface WorkspaceAgent {
  id: string;
  type: "local" | "cloud" | "persistent";
  harness: string;
  model: string;
  avatar_seed: string | null;
  session_id: string | null;
  role: string | null;
  description: string | null;
  last_seen_at: string | null;
}

interface Workspace {
  id: number;
  name: string;
  type: "local" | "cloud" | "persistent";
  agents: WorkspaceAgent[];
  created_at: string;
}

import type { ChatMessage } from "@/hooks/use-workspace-agent";

const MAX_TEXTAREA_HEIGHT = 200;



function DeleteWorkspaceModal({ workspace, onClose, onDeleted }: { workspace: Workspace; onClose: () => void; onDeleted: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const matches = confirm === workspace.name;
  const agentCount = workspace.agents?.length ?? 0;

  const submit = async () => {
    if (!matches) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/workspaces/${workspace.id}`, {
        method: "DELETE",
        headers: getAuthHeader(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? "Delete failed");
      }
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      setSubmitting(false);
    }
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[440px] flex flex-col animate-fade-in" style={{ borderRadius: 6 }}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-base font-semibold text-[var(--color-text)]">Delete Workspace</h2>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div className="px-3 py-2.5 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900" style={{ borderRadius: 4 }}>
            <p className="text-xs text-red-700 dark:text-red-300">
              This action cannot be undone.
              {agentCount > 0 && (
                <> {agentCount} {agentCount === 1 ? "agent" : "agents"} and {agentCount === 1 ? "its sandbox" : "their sandboxes"} will be torn down. Agents with public runs will be preserved but unlinked.</>
              )}
            </p>
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-secondary)] mb-1.5">
              Type <span className="font-semibold text-[var(--color-text)]">{workspace.name}</span> to confirm.
            </label>
            <input
              type="text"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && matches) { e.preventDefault(); submit(); } }}
              className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] font-[family-name:var(--font-ibm-plex-mono)]"
              style={{ outline: "none", boxShadow: "none" }}
              autoFocus
            />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={submitting || !matches}
              className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Deleting…" : "I understand, delete this workspace"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function WorkspacePage({ embeddedWorkspaceId }: { embeddedWorkspaceId?: string } = {}) {
  const params = useParams();
  const router = useRouter();
  const workspaceId = embeddedWorkspaceId ?? (params?.id as string);

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);
  const [wsLoading, setWsLoading] = useState(true);
  const [addingAgent, setAddingAgent] = useState(false);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);
  const [currentModel, setCurrentModel] = useState<string>(DEFAULT_MODEL);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelError, setModelError] = useState<string | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [modelChanging, setModelChanging] = useState(false);
  const [modelHover, setModelHover] = useState(0);
  const modelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_BASE}/models`, { headers: getAuthHeader() })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d?.models) setModels(d.models); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!modelOpen) return;
    const handler = (e: MouseEvent) => {
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) setModelOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelOpen]);
  const [wsMenuOpen, setWsMenuOpen] = useState(false);
  const [showDeleteWs, setShowDeleteWs] = useState(false);
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const wsMenuRef = useRef<HTMLDivElement>(null);

  const refetchWorkspace = useCallback(async () => {
    try {
      const data = await apiFetch<Workspace>(`/workspaces/${workspaceId}`);
      setWorkspace(data);
    } catch { /* ignore */ }
  }, [workspaceId]);

  useEffect(() => {
    let cancelled = false;
    apiFetch<Workspace>(`/workspaces/${workspaceId}`)
      .then((data) => { if (!cancelled) setWorkspace(data); })
      .catch(() => { if (!cancelled) setWsError("Workspace not found"); })
      .finally(() => { if (!cancelled) setWsLoading(false); });
    return () => { cancelled = true; };
  }, [workspaceId]);

  const isProvisioning = false; // sandbox provisioning is now lazy via /connect

  useEffect(() => {
    if (!isProvisioning) return;
    const timer = setInterval(() => { refetchWorkspace(); }, 2000);
    return () => clearInterval(timer);
  }, [isProvisioning, refetchWorkspace]);

  const handleAddAgent = useCallback(async (name?: string) => {
    setAddingAgent(true);
    try {
      const agent = await apiPostJson<{ id: string }>(`/workspaces/${workspaceId}/agents`, {
        name: name ?? "",
        harness: "claude-code",
        model: "claude-sonnet-4-6",
      });
      await refetchWorkspace();
      setActiveAgentId(agent.id);
      return agent;
    } finally {
      setAddingAgent(false);
    }
  }, [workspaceId, refetchWorkspace]);

  const handleDeleteAgent = useCallback(async (agentId: string) => {
    await apiDelete(`/workspaces/${workspaceId}/agents/${agentId}`);
    // If the deleted agent was active, pick another or clear
    if (activeAgentId === agentId) {
      setActiveAgentId(null);
    }
    await refetchWorkspace();
  }, [workspaceId, activeAgentId, refetchWorkspace]);

  const workspaceName = workspace?.name ?? "";
  const agents = workspace?.agents ?? [];
  const activeAgent = activeAgentId ? agents.find((a) => a.id === activeAgentId) ?? null : (agents[0] ?? null);
  const agentName = activeAgent?.id ?? "";

  // Auto-select first agent when workspace loads or agents change and no selection
  useEffect(() => {
    if (!activeAgentId && agents.length > 0) {
      setActiveAgentId(agents[0].id);
    }
  }, [activeAgentId, agents]);

  useEffect(() => {
    setCurrentModel(activeAgent?.model ?? DEFAULT_MODEL);
    setModelError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeAgent?.id]);

  // Close workspace menu on outside click
  useEffect(() => {
    if (!wsMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (wsMenuRef.current && !wsMenuRef.current.contains(e.target as Node)) setWsMenuOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [wsMenuOpen]);

  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [leftWidth, setLeftWidth] = useState(20);
  const [chatWidth, setChatWidth] = useState(35);
  const [isDragging, setIsDragging] = useState<"left" | "right" | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Editor state
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);


  const handleCloseTab = useCallback((path: string) => {
    setOpenFiles((prev) => {
      const next = prev.filter((f) => f.path !== path);
      if (activePath === path) {
        setActivePath(next.length > 0 ? next[next.length - 1].path : null);
      }
      return next;
    });
  }, [activePath]);

  const handleChangeContent = useCallback((path: string, content: string) => {
    setOpenFiles((prev) => prev.map((f) => f.path === path ? { ...f, content } : f));
  }, []);

  // Chat state — all agents connected simultaneously
  const agentIdList = useMemo(() => agents.map((a) => a.id), [agents]);
  const { states: agentStates, sendMessage: sendAgentMessage, cancel: cancelAgent, setModel: setAgentModel } = useWorkspaceAgents(
    workspace ? workspaceId : null,
    agentIdList,
  );
  const emptyState: AgentState = { messages: [], commands: [], isLoading: false, cancelling: false, connecting: false, error: null, sdkBaseUrl: null, sessionId: null };
  const activeState: AgentState = activeAgent ? agentStates[activeAgent.id] ?? emptyState : emptyState;
  const { messages, commands: rawCommands, isLoading, cancelling, connecting, error: agentError } = activeState;
  const sendMessage = useCallback((text: string) => { if (activeAgent) sendAgentMessage(activeAgent.id, text); }, [activeAgent, sendAgentMessage]);
  const cancel = useCallback(() => { if (activeAgent) cancelAgent(activeAgent.id); }, [activeAgent, cancelAgent]);

  const handleModelChange = useCallback(async (model: string) => {
    if (!activeAgent?.id) return;
    const targetId = activeAgent.id;
    setModelError(null);
    try {
      await setAgentModel(targetId, model);
      setCurrentModel((prev) => (activeAgent?.id === targetId ? model : prev));
    } catch (err) {
      setModelError(err instanceof Error ? err.message : "Failed to switch model");
    }
  }, [activeAgent?.id, setAgentModel]);

  const commands = rawCommands;
  const validCommandNames = useMemo(() => new Set(commands.map((c) => c.name)), [commands]);

  // Live sandbox filesystem — uses the active agent's sandbox for file browsing
  const activeAgentState = activeAgent ? agentStates[activeAgent.id] : null;
  const { tree: fsTree, loading: fsLoading, error: fsError, readFile, editFile, uploadFiles, deleteFile, renameFile, downloadFile, refresh: fsRefresh } = useWorkspaceFiles(
    activeAgentState?.sdkBaseUrl ?? null,
    null, // sandbox_id fetched by useWorkspaceFiles when needed
  );
  const [draggingOver, setDraggingOver] = useState(false);
  const [bgMenuPos, setBgMenuPos] = useState<{ x: number; y: number } | null>(null);
  const bgMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!bgMenuPos) return;
    const handler = (e: MouseEvent) => {
      if (bgMenuRef.current && !bgMenuRef.current.contains(e.target as Node)) setBgMenuPos(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [bgMenuPos]);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    setDraggingOver(false);
    const items = e.dataTransfer.items;
    const allFiles: File[] = [];

    // Recursively read directory entries
    async function readEntry(entry: FileSystemEntry, basePath: string): Promise<void> {
      if (entry.isFile) {
        const file = await new Promise<File>((resolve) => (entry as FileSystemFileEntry).file(resolve));
        const path = basePath ? `${basePath}/${file.name}` : file.name;
        allFiles.push(new File([file], path, { type: file.type }));
      } else if (entry.isDirectory) {
        const reader = (entry as FileSystemDirectoryEntry).createReader();
        const entries = await new Promise<FileSystemEntry[]>((resolve) => reader.readEntries(resolve));
        const dirPath = basePath ? `${basePath}/${entry.name}` : entry.name;
        for (const child of entries) await readEntry(child, dirPath);
      }
    }

    if (items) {
      for (let i = 0; i < items.length; i++) {
        const entry = items[i].webkitGetAsEntry?.();
        if (entry) {
          await readEntry(entry, "");
        } else if (items[i].kind === "file") {
          const file = items[i].getAsFile();
          if (file) allFiles.push(file);
        }
      }
    }

    if (allFiles.length > 0) {
      const result = await uploadFiles(allFiles);
      if (!result.ok) alert("Upload failed: " + (result.error ?? "unknown"));
      await fsRefresh();
    }
  }, [uploadFiles, fsRefresh]);

  const handleDeleteFile = useCallback(async (filePath: string) => {
    if (!confirm(`Delete "${filePath}"?`)) return;
    const result = await deleteFile(filePath);
    if (!result.ok) alert("Delete failed: " + (result.error ?? "unknown"));
    await fsRefresh();
  }, [deleteFile, fsRefresh]);

  const [fsPrompt, setFsPrompt] = useState<{ title: string; label: string; value: string; onSubmit: (v: string) => Promise<void> } | null>(null);

  const handleRenameFile = useCallback((filePath: string) => {
    const fileName = filePath.includes("/") ? filePath.slice(filePath.lastIndexOf("/") + 1) : filePath;
    const dir = filePath.includes("/") ? filePath.slice(0, filePath.lastIndexOf("/")) : "";
    setFsPrompt({
      title: "Rename",
      label: "New name",
      value: fileName,
      onSubmit: async (name) => {
        const newPath = dir ? `${dir}/${name}` : name;
        if (newPath === filePath) return;
        const result = await renameFile(filePath, newPath);
        if (!result.ok) alert("Rename failed: " + (result.error ?? "unknown"));
        await fsRefresh();
      },
    });
  }, [renameFile, fsRefresh]);

  const handleNewFile = useCallback((directory: string) => {
    setFsPrompt({
      title: "New File",
      label: "File name",
      value: "",
      onSubmit: async (name) => {
        const filePath = directory ? `${directory}/${name}` : name;
        const result = await editFile(filePath, "", "");
        if (!result.ok) alert("Create failed: " + (result.error ?? "unknown"));
        await fsRefresh();
      },
    });
  }, [editFile, fsRefresh]);

  const handleNewFolder = useCallback((directory: string) => {
    setFsPrompt({
      title: "New Folder",
      label: "Folder name",
      value: "",
      onSubmit: async (name) => {
        const folderPath = directory ? `${directory}/${name}` : name;
        const placeholderPath = `${folderPath}/.keep`;
        const result = await editFile(placeholderPath, "", "");
        if (!result.ok) alert("Create failed: " + (result.error ?? "unknown"));
        await fsRefresh();
      },
    });
  }, [editFile, fsRefresh]);

  const handleSaveFile = useCallback(async (path: string, content: string) => {
    const result = await editFile(path, "", content);
    if (!result.ok) {
      alert("Save failed: " + (result.error ?? "unknown error"));
    }
  }, [editFile]);

  // Auto-expand root directories on first tree load
  const fsInitRef = useRef(false);
  useEffect(() => {
    if (fsTree.length > 0 && !fsInitRef.current) {
      fsInitRef.current = true;
      setExpandedDirs(new Set(fsTree.filter(n => n.type === "directory").map(n => n.path)));
    }
  }, [fsTree]);

  const handleFileClick = useCallback(async (node: FsTreeNode) => {
    if (node.type === "directory") return;
    // Activate tab immediately with loading placeholder
    setOpenFiles((prev) => {
      if (prev.some((f) => f.path === node.path)) return prev;
      return [...prev, { path: node.path, name: node.name, content: "Loading…" }];
    });
    setActivePath(node.path);
    // Fetch real content
    try {
      const data = await readFile(node.path);
      if (data && !data.binary) {
        setOpenFiles((prev) => prev.map((f) => f.path === node.path ? { ...f, content: data.content } : f));
      } else if (data?.binary) {
        setOpenFiles((prev) => prev.map((f) => f.path === node.path ? { ...f, content: `[binary file — ${data.size} bytes]` } : f));
      }
    } catch {
      setOpenFiles((prev) => prev.map((f) => f.path === node.path ? { ...f, content: "Error loading file" } : f));
    }
  }, [readFile]);
  const [input, setInput] = useState("");
  const [answeredToolIds, setAnsweredToolIds] = useState<Set<string>>(new Set());
  // Clear input and scroll to bottom of content when switching agents
  useEffect(() => {
    setInput("");
    requestAnimationFrame(() => {
      // Collapse the spacer so we scroll to actual content, not empty space
      if (spacerRef.current) spacerRef.current.style.height = "0px";
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, [activeAgentId]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const latestUserRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, MAX_TEXTAREA_HEIGHT) + "px";
    ta.style.overflowY = ta.scrollHeight > MAX_TEXTAREA_HEIGHT ? "auto" : "hidden";
  }, []);

  useEffect(() => { resizeTextarea(); }, [input, resizeTextarea]);

  // Slash command autocomplete — detect /word at cursor position
  const [cmdIndex, setCmdIndex] = useState(0);
  const [cmdDismissed, setCmdDismissed] = useState(false);
  const getSlashWord = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return "";
    const pos = ta.selectionStart ?? input.length;
    const before = input.slice(0, pos);
    const match = before.match(/\/([^\s]*)$/);
    return match ? match[0] : "";
  }, [input]);
  const slashWord = getSlashWord();
  const showCommands = slashWord.length > 0 && commands.length > 0 && !cmdDismissed;
  const filteredCommands = showCommands
    ? commands.filter((c) => `/${c.name}`.startsWith(slashWord.toLowerCase()))
    : [];
  useEffect(() => {
    setCmdIndex(0);
    // Re-enable dropdown when user types a new slash
    if (slashWord) setCmdDismissed(false);
  }, [input, slashWord]);

  const lastUserIdx = messages.reduce((acc, msg, i) => msg.role === "user" ? i : acc, -1);

  const updateSpacer = useCallback(() => {
    const container = scrollRef.current;
    const userEl = latestUserRef.current;
    const spacer = spacerRef.current;
    const contentEl = contentRef.current;
    if (!container || !userEl || !spacer || !contentEl) return;
    spacer.style.height = "0px";
    const contentHeight = contentEl.scrollHeight;
    const userOffset = userEl.offsetTop - contentEl.offsetTop;
    const contentFromUser = contentHeight - userOffset;
    const containerPadding = parseFloat(getComputedStyle(container).paddingTop) + parseFloat(getComputedStyle(container).paddingBottom);
    const needed = Math.max(0, container.clientHeight - contentFromUser - containerPadding);
    spacer.style.height = needed + "px";
  }, []);

  const prevLastUserIdxRef = useRef(lastUserIdx);
  useEffect(() => {
    updateSpacer();
    const isNewUserMsg = lastUserIdx !== prevLastUserIdxRef.current;
    prevLastUserIdxRef.current = lastUserIdx;
    if (isNewUserMsg) {
      requestAnimationFrame(() => {
        updateSpacer();
        if (latestUserRef.current) {
          latestUserRef.current.scrollIntoView({ block: "start" });
        }
      });
    }
  }, [messages, lastUserIdx, updateSpacer]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    const observer = new ResizeObserver(() => updateSpacer());
    observer.observe(content);
    return () => observer.disconnect();
  }, [updateSpacer]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    sendMessage(input.trim());
    setInput("");
    setTimeout(() => {
      updateSpacer();
      if (latestUserRef.current) {
        latestUserRef.current.scrollIntoView({ block: "start" });
      }
    }, 0);
  }, [input, sendMessage, updateSpacer]);

  const selectCommand = useCallback((cmd: string) => {
    setCmdDismissed(true);
    const ta = textareaRef.current;
    if (!ta) { setInput(`/${cmd} `); return; }
    const pos = ta.selectionStart ?? input.length;
    const before = input.slice(0, pos);
    const after = input.slice(pos);
    const match = before.match(/\/([^\s]*)$/);
    if (match) {
      const start = before.length - match[0].length;
      setInput(before.slice(0, start) + `/${cmd} ` + after);
    } else {
      setInput(`/${cmd} `);
    }
    ta.focus();
  }, [input]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (filteredCommands.length > 0 && showCommands) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCmdIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setCmdIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        selectCommand(filteredCommands[cmdIndex].name);
        return;
      }
      if (e.key === "Escape") {
        setInput("");
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }, [handleSubmit, filteredCommands, showCommands, cmdIndex, selectCommand]);

  const handleToggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleMouseDown = useCallback((side: "left" | "right") => {
    setIsDragging(side);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    if (isDragging === "left") {
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftWidth(Math.max(12, Math.min(40, pct)));
    } else {
      const pct = ((rect.right - e.clientX) / rect.width) * 100;
      setChatWidth(Math.max(20, Math.min(50, pct)));
    }
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(null);
  }, []);

  useEffect(() => {
    if (isDragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    }
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  if (wsLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
      </div>
    );
  }

  if (wsError || !workspace) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3">
        <p className="text-sm text-[var(--color-text-tertiary)]">{wsError ?? "Workspace not found"}</p>
        <button
          onClick={() => router.push("/profile?tab=workspaces")}
          className="text-sm text-[var(--color-accent)] hover:underline"
        >
          Back to Workspaces
        </button>
      </div>
    );
  }

  const isEmbedded = !!embeddedWorkspaceId;

  return (
    <div className="h-full flex flex-col relative">
      {/* Header — hidden when embedded */}
      {!isEmbedded && (
      <div className="shrink-0 h-[52px] px-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center gap-3">
        <button
          onClick={() => router.push("/profile?tab=workspaces")}
          className="flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
        >
          <LuArrowLeft size={14} />
        </button>
        <div className="flex flex-col leading-tight">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-semibold">
            {workspace?.type === "cloud" ? "Cloud" : workspace?.type === "persistent" ? "Persistent" : "Local"}
          </span>
          <span className="text-[14px] font-semibold text-[var(--color-text)]">{workspaceName}</span>
        </div>

        {/* Workspace menu (right side) */}
        <div ref={wsMenuRef} className="ml-auto relative">
          <button
            onClick={() => setWsMenuOpen((o) => !o)}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
            style={{ borderRadius: 4 }}
            aria-label="Workspace menu"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
              <circle cx="7" cy="3" r="1.3" />
              <circle cx="7" cy="7" r="1.3" />
              <circle cx="7" cy="11" r="1.3" />
            </svg>
          </button>
          {wsMenuOpen && (
            <div
              className="absolute right-0 mt-1 bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 min-w-[160px] z-50"
              style={{ borderRadius: 6 }}
            >
              <button
                onClick={() => { setWsMenuOpen(false); setShowCreateAgent(true); }}
                className="w-full text-left px-3 py-2 text-sm font-medium text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
              >
                Add agent
              </button>
              <button
                onClick={() => { setWsMenuOpen(false); setShowDeleteWs(true); }}
                className="w-full text-left px-3 py-2 text-sm font-medium text-red-500 hover:bg-red-500/10 transition-colors"
              >
                Delete workspace
              </button>
            </div>
          )}
        </div>
      </div>
      )}

      {showCreateAgent && (
        <CreateAgentModal
          existingNames={agents.map((a) => a.id)}
          onClose={() => setShowCreateAgent(false)}
          onCreate={handleAddAgent}
          submitting={addingAgent}
        />
      )}
      {showDeleteWs && workspace && (
        <DeleteWorkspaceModal
          workspace={workspace}
          onClose={() => setShowDeleteWs(false)}
          onDeleted={() => {
            setShowDeleteWs(false);
            router.push("/profile?tab=workspaces");
          }}
        />
      )}

      {fsPrompt && (
        <FsPromptModal
          title={fsPrompt.title}
          label={fsPrompt.label}
          defaultValue={fsPrompt.value}
          onClose={() => setFsPrompt(null)}
          onSubmit={async (v) => { setFsPrompt(null); await fsPrompt.onSubmit(v); }}
        />
      )}

      {isProvisioning && (
        <div className="absolute inset-x-0 top-[52px] bottom-0 z-20 flex flex-col items-center justify-center gap-3 bg-[var(--color-bg)]">
          <div className="w-8 h-8 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
          <div className="text-sm text-[var(--color-text-secondary)]">Preparing your workspace sandbox…</div>
          <div className="text-xs text-[var(--color-text-tertiary)] max-w-xs text-center px-4">
            Installing dependencies on a fresh cloud sandbox. This usually takes 1–5 minutes.
          </div>
        </div>
      )}

      {/* Split view */}
      <div ref={containerRef} className="flex-1 flex min-h-0">
        {/* Left: File System */}
        <div
          className={`shrink-0 flex flex-col bg-[var(--color-layer-2)] ${draggingOver ? "ring-2 ring-inset ring-[var(--color-accent)]" : ""}`}
          style={{ width: `${leftWidth}%` }}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setDraggingOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setDraggingOver(false); }}
          onDrop={handleDrop}
        >
          {/* File tree */}
          <div
            className="flex-1 overflow-y-auto min-h-0 px-5 pt-4 pb-5"
            onContextMenu={(e) => {
              // Only trigger on the background itself, not on tree nodes
              if (e.target === e.currentTarget || (e.target as HTMLElement).closest("[data-fs-bg]")) {
                e.preventDefault();
                setBgMenuPos({ x: e.clientX, y: e.clientY });
              }
            }}
          >
            {fsLoading && (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
              </div>
            )}
            {fsError && (
              <p className="text-xs text-[var(--color-text-tertiary)] px-1 py-4">{fsError}</p>
            )}
            {!fsLoading && !fsError && fsTree.length === 0 && (
              <p className="text-xs text-[var(--color-text-tertiary)] px-1 py-4" data-fs-bg>No files yet</p>
            )}
            {bgMenuPos && (
              <div
                ref={bgMenuRef}
                className="fixed bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 min-w-[140px] z-[9999]"
                style={{ borderRadius: 6, left: bgMenuPos.x, top: bgMenuPos.y }}
              >
                <button onClick={() => { setBgMenuPos(null); handleNewFile(""); }} className="w-full text-left px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-layer-1)]">
                  New File
                </button>
                <button onClick={() => { setBgMenuPos(null); handleNewFolder(""); }} className="w-full text-left px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-layer-1)]">
                  New Folder
                </button>
              </div>
            )}
            <div className="space-y-0.5">
              <FileTree
                nodes={fsTree}
                expandedDirs={expandedDirs}
                onToggleDir={handleToggleDir}
                onFileClick={handleFileClick}
                onDelete={handleDeleteFile}
                onRename={handleRenameFile}
                onDownload={downloadFile}
                onNewFile={handleNewFile}
                onNewFolder={handleNewFolder}
              />
            </div>
          </div>
        </div>

        {openFiles.length > 0 && (
          <>
            {/* Drag handle 1 (tree | editor) */}
            <div
              onMouseDown={() => handleMouseDown("left")}
              className="shrink-0 group relative"
              style={{ width: 8, marginLeft: -4, marginRight: -4, cursor: "col-resize", zIndex: 10 }}
            >
              <div className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-px transition-colors ${isDragging === "left" ? "bg-[var(--color-accent)]" : "bg-[var(--color-border)] group-hover:bg-[var(--color-accent)]"}`} />
            </div>

            {/* Middle: Editor */}
            <div className="flex-1 min-w-0 flex flex-col">
              <WorkspaceEditor
                openFiles={openFiles}
                activePath={activePath}
                onSelectTab={setActivePath}
                onCloseTab={handleCloseTab}
                onChangeContent={handleChangeContent}
                onSave={handleSaveFile}
              />
            </div>
          </>
        )}

        {/* Drag handle 2 (editor | chat) */}
        <div
          onMouseDown={() => handleMouseDown("right")}
          className="shrink-0 group relative"
          style={{ width: 8, marginLeft: -4, marginRight: -4, cursor: "col-resize", zIndex: 10 }}
        >
          <div className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-px transition-colors ${isDragging === "right" ? "bg-[var(--color-accent)]" : "bg-[var(--color-border)] group-hover:bg-[var(--color-accent)]"}`} />
        </div>

        {/* Right: Chat */}
        <div
          className={`min-w-0 flex flex-col bg-[var(--color-layer-2)] ${openFiles.length === 0 ? "flex-1" : "shrink-0"}`}
          style={{ ...(openFiles.length === 0 ? { height: "100%" } : { width: `${chatWidth}%`, height: "100%" }), fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}
        >
          {/* Agent tabs */}
          <AgentTabBar
            agents={agents.map(a => ({ id: a.id, avatar_seed: a.avatar_seed }))}
            activeId={activeAgent?.id ?? null}
            onSelect={setActiveAgentId}
            onClose={handleDeleteAgent}
          />
          {modelError && (
            <div className="shrink-0 px-3 py-1 text-[11px] text-red-400 bg-red-500/5 border-b border-[var(--color-border)]">
              {modelError}
            </div>
          )}

          {!activeAgent ? (
            <div className="flex-1 border-t border-[var(--color-border)] bg-[var(--color-layer-1)] flex flex-col items-center justify-center gap-3 px-6">
              <svg className="w-10 h-10 text-[var(--color-text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="text-sm text-[var(--color-text-tertiary)] text-center">No agents in this workspace yet</p>
              <button
                onClick={() => setShowCreateAgent(true)}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Add your first agent
              </button>
            </div>
          ) : (
            <>
          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0 py-4 space-y-3 border-t border-[var(--color-border)] bg-[var(--color-layer-1)]">
            {connecting && (
              <div className="flex flex-col items-center justify-center h-full">
                <div className="w-6 h-6 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin mb-3" />
                <p className="text-sm text-[var(--color-text-tertiary)]">Connecting to agent…</p>
              </div>
            )}
            {agentError && (
              <div className="px-3 py-2 text-sm text-red-500 border border-red-500/30 bg-red-500/5 rounded">
                {agentError}
              </div>
            )}
            {!connecting && messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full">
                <svg className="w-8 h-8 text-[var(--color-text-tertiary)] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <p className="text-sm text-[var(--color-text-tertiary)]">No messages yet</p>
              </div>
            )}

            <div ref={contentRef} className="max-w-4xl mx-auto px-6 space-y-3">
            {messages.map((msg, i) => (
              <div key={i} className={`flex justify-start ${i === lastUserIdx ? "pt-4" : ""}`} ref={i === lastUserIdx ? latestUserRef : undefined}>
                {msg.role === "user" ? (
                  <div className="w-full px-3 py-2 bg-white dark:bg-[var(--color-layer-2)] shadow-sm text-[var(--color-text)]" style={{ borderRadius: 10 }}>
                    <p className="text-sm whitespace-pre-wrap"><HighlightSlash text={msg.content} validCommands={validCommandNames} /></p>
                  </div>
                ) : msg.role === "error" ? (
                  <div className="w-full pl-4 px-3 py-2 text-sm text-red-500 border border-red-500/30 bg-red-500/5 rounded whitespace-pre-wrap">
                    {msg.content}
                  </div>
                ) : (
                  <div className="w-full pl-4 space-y-1.5">
                    {msg.parts && msg.parts.length > 0 ? (
                      <>
                        {msg.parts.map((part, pi) => {
                          const isLastPart = pi === (msg.parts?.length ?? 0) - 1;
                          if (part.type === "text") {
                            return (
                              <div key={pi} className="prose prose-sm max-w-none text-[var(--color-text)]">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.content}</ReactMarkdown>
                              </div>
                            );
                          }
                          if (part.type === "thinking") {
                            return <ThinkingBlock key={pi} content={part.content} active={!!msg.streaming && isLastPart} />;
                          }
                          return <ToolCallCard key={pi} part={part} active={!!msg.streaming && isLastPart} />;
                        })}
                        {msg.streaming && msg.parts[msg.parts.length - 1]?.type === "text" && (
                          <span className="inline-block w-2 h-4 ml-0.5 bg-[var(--color-text)] animate-pulse" />
                        )}
                      </>
                    ) : msg.content ? (
                      <div className="prose prose-sm max-w-none text-[var(--color-text)]">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                        {msg.streaming && <span className="inline-block w-2 h-4 ml-0.5 bg-[var(--color-text)] animate-pulse" />}
                      </div>
                    ) : msg.streaming ? (
                      <div>
                        <TextShimmer className="text-sm [--base-color:var(--color-text-tertiary)] [--base-gradient-color:var(--color-text)]" duration={2}>Working on it</TextShimmer>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            ))}

            {isLoading && messages.length > 0 && messages[messages.length - 1].role === "user" && (
              <div className="flex justify-start">
                <div className="pl-4">
                  <TextShimmer className="text-sm [--base-color:var(--color-text-tertiary)] [--base-gradient-color:var(--color-text)]" duration={2}>Working on it</TextShimmer>
                </div>
              </div>
            )}
            <div ref={spacerRef} />
            </div>
          </div>

          {/* ask_user widget — above the input */}
          {(() => {
            const pendingQuestions: { data: AskUserData; id: string }[] = [];
            for (const msg of messages) {
              if (msg.parts) {
                for (const part of msg.parts) {
                  if (part.type === "tool" && part.name.endsWith("ask_user") && part.input && !answeredToolIds.has(part.id)) {
                    let inp: Record<string, unknown>;
                    if (typeof part.input === "string") {
                      try { inp = JSON.parse(part.input); } catch { inp = {}; }
                    } else {
                      inp = part.input as Record<string, unknown>;
                    }
                    const args = (inp.arguments ?? inp.input ?? inp) as Record<string, unknown>;
                    // Support both single question and questions array format
                    const questionsArr = args.questions as Array<Record<string, unknown>> | undefined;
                    if (questionsArr && Array.isArray(questionsArr)) {
                      for (const q of questionsArr) {
                        const question = (q.question as string) ?? "";
                        if (!question) continue;
                        pendingQuestions.push({
                          id: part.id,
                          data: {
                            question,
                            options: q.options as string[] | undefined,
                            mode: (q.mode as AskUserData["mode"]) ?? "select",
                          },
                        });
                      }
                    } else {
                      // Fallback: single question format
                      const question = (args.question as string) ?? "";
                      if (!question) continue;
                      pendingQuestions.push({
                        id: part.id,
                        data: {
                          question,
                          options: args.options as string[] | undefined,
                          mode: (args.mode as AskUserData["mode"]) ?? "select",
                        },
                      });
                    }
                  }
                }
              }
            }
            if (pendingQuestions.length === 0) return null;
            return (
              <div className="shrink-0 px-3 pb-2 bg-[var(--color-layer-1)]">
                <div className="max-w-4xl mx-auto">
                  <AskUserWidget
                    questions={pendingQuestions.map((q) => q.data)}
                    onSubmitAll={(answers) => {
                      // Mark all questions as answered
                      setAnsweredToolIds((prev) => {
                        const next = new Set(prev);
                        for (const q of pendingQuestions) next.add(q.id);
                        return next;
                      });
                      // Build answer text
                      const text = answers.map((a, i) => {
                        const q = pendingQuestions[i]?.data.question ?? "";
                        const ans = Array.isArray(a) ? a.join(", ") : a;
                        return pendingQuestions.length === 1 ? ans : `${q}: ${ans}`;
                      }).join("\n");
                      sendMessage(text);
                    }}
                  />
                </div>
              </div>
            );
          })()}

          {/* Input */}
          <div className="shrink-0 px-3 pb-5 pt-2 bg-[var(--color-layer-1)]">
            <div className="max-w-4xl mx-auto relative">
              {/* Slash command dropdown */}
              {showCommands && filteredCommands.length > 0 && (
                <div className="absolute bottom-full left-0 mb-1 flex items-end gap-1 z-50">
                  <div className="bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 overflow-y-auto max-h-52 w-[300px]" style={{ borderRadius: 6 }}>
                    <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-medium">Skills</div>
                    {filteredCommands.map((cmd, i) => (
                      <button
                        key={cmd.name}
                        onMouseDown={(e) => { e.preventDefault(); selectCommand(cmd.name); }}
                        onMouseEnter={() => setCmdIndex(i)}
                        className={`w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 transition-colors ${
                          i === cmdIndex
                            ? "bg-[var(--color-layer-2)]"
                            : "hover:bg-[var(--color-layer-2)]"
                        }`}
                      >
                        <span className="font-medium text-[var(--color-text)] font-[family-name:var(--font-ibm-plex-mono)]">{cmd.name}</span>
                        <span className="text-[var(--color-text-tertiary)] truncate flex-1">{cmd.description}</span>
                      </button>
                    ))}
                  </div>
                  {filteredCommands[cmdIndex]?.description.length > 40 && (
                    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg px-3 py-2.5 w-[220px] max-h-52 overflow-y-auto text-xs text-[var(--color-text-secondary)] leading-relaxed" style={{ borderRadius: 6 }}>
                      {filteredCommands[cmdIndex].description}
                    </div>
                  )}
                </div>
              )}
              {/* Model selector dropdown */}
              {modelOpen && models.length > 0 && (
                <div className="absolute bottom-full left-0 mb-1 flex items-end gap-1 z-50">
                  <div className="bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 w-[200px]" style={{ borderRadius: 6 }}>
                    <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-medium">Model</div>
                    {models.map((m, i) => {
                      const isCurrent = m.id === currentModel;
                      return (
                        <button
                          type="button"
                          key={m.id}
                          onMouseEnter={() => setModelHover(i)}
                          onMouseDown={async (e) => {
                            e.preventDefault();
                            if (isCurrent) { setModelOpen(false); return; }
                            setModelOpen(false);
                            setModelChanging(true);
                            try { await handleModelChange(m.id); } finally { setModelChanging(false); }
                          }}
                          className={`w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 transition-colors ${
                            i === modelHover ? "bg-[var(--color-layer-2)]" : "hover:bg-[var(--color-layer-2)]"
                          }`}
                        >
                          <span className="font-medium text-[var(--color-text)]">{m.display_name ?? m.id}</span>
                          {isCurrent && (
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="ml-auto text-[var(--color-text)]">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                            </svg>
                          )}
                        </button>
                      );
                    })}
                  </div>
                  {models[modelHover]?.description && (
                    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg px-3 py-2.5 w-[220px] max-h-52 overflow-y-auto text-xs text-[var(--color-text-secondary)] leading-relaxed" style={{ borderRadius: 6 }}>
                      {models[modelHover].description.replace(/\bOur\b/g, "Anthropic's")}
                    </div>
                  )}
                </div>
              )}
              <div className="relative bg-white dark:bg-[var(--color-surface)] shadow-sm flex flex-col" style={{ borderRadius: 16, minHeight: 40 }}>
                {/* Text input row */}
                <div className="flex items-end gap-2 px-4 py-2.5">
                  {/* Highlight overlay */}
                  <div
                    aria-hidden
                    className="absolute inset-x-4 top-2.5 right-12 text-sm whitespace-pre-wrap break-words pointer-events-none"
                    style={{ lineHeight: "20px" }}
                  >
                    <span className="text-[var(--color-text)]"><HighlightSlash text={input} validCommands={validCommandNames} /></span>
                  </div>
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={`Ask ${agentName} something...`}
                    rows={1}
                    className="flex-1 resize-none text-sm bg-transparent placeholder:text-[var(--color-text-tertiary)]"
                    style={{
                      outline: "none", boxShadow: "none",
                      color: "transparent",
                      caretColor: "var(--color-text)",
                      padding: 0, margin: 0, border: "none",
                      lineHeight: "20px",
                    }}
                  />
                </div>
                {/* Bottom row: model selector (left) + send button (right) */}
                <div className="flex items-center justify-between px-4 pb-2">
                  {activeAgent ? (
                    <div ref={modelRef}>
                      <button
                        type="button"
                        onClick={() => { setModelOpen((v) => !v); setModelHover(0); }}
                        disabled={modelChanging}
                        className="flex items-center gap-1 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors disabled:opacity-50"
                      >
                        {modelChanging && <span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />}
                        {models.find((m) => m.id === currentModel)?.display_name ?? currentModel}
                        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="opacity-40">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </div>
                  ) : <div />}
                  {cancelling ? (
                    <div className="shrink-0 w-7 h-7 flex items-center justify-center" title="Stopping…">
                      <div className="w-5 h-5 border-2 border-[var(--color-border)] border-t-[var(--color-text-tertiary)] rounded-full animate-spin" />
                    </div>
                  ) : isLoading ? (
                    <button
                      type="button"
                      onClick={cancel}
                      className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full bg-[var(--color-text)] text-white hover:opacity-80 transition-colors"
                      title="Stop generating"
                    >
                      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                        <rect x="6" y="6" width="12" height="12" rx="1" />
                      </svg>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => handleSubmit(e as unknown as React.FormEvent)}
                      disabled={!input.trim()}
                      className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full bg-[var(--color-text)] text-white disabled:bg-[var(--color-layer-2)] disabled:text-[var(--color-text-tertiary)] disabled:cursor-not-allowed transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
