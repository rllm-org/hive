"use client";

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { LuArrowLeft, LuPlus } from "react-icons/lu";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch, apiPostJson } from "@/lib/api";
import BoringAvatar from "boring-avatars";

const AVATAR_COLORS = ["#92A1C6", "#146A7C", "#F0AB3D", "#C271B4", "#C20D90"];

function AgentAvatar({ seed, id, size = 20 }: { seed: string | null; id: string; size?: number }) {
  return (
    <div className="overflow-hidden shrink-0" style={{ width: size, height: size, borderRadius: 4 }}>
      <BoringAvatar name={seed || id} variant="beam" size={size} square colors={AVATAR_COLORS} />
    </div>
  );
}

function AgentTabs({
  agents,
  activeAgentId,
  onSelect,
  onCreate,
  adding,
}: {
  agents: WorkspaceAgent[];
  activeAgentId: string | null;
  onSelect: (id: string) => void;
  onCreate: (name?: string) => Promise<{ id: string } | undefined>;
  adding: boolean;
}) {
  const [showModal, setShowModal] = useState(false);

  return (
    <>
      <div className="shrink-0 flex items-center gap-1 px-3 pt-3 border-b border-[var(--color-border)]">
        {agents.map((a) => {
          const active = a.id === activeAgentId;
          return (
            <button
              key={a.id}
              onClick={() => onSelect(a.id)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
                active
                  ? "bg-[var(--color-surface)] text-[var(--color-text)] border border-[var(--color-border)] border-b-[var(--color-surface)] -mb-px"
                  : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] border border-transparent"
              }`}
              style={{ borderRadius: "6px 6px 0 0" }}
            >
              <AgentAvatar seed={a.avatar_seed} id={a.id} size={16} />
              <span className="truncate max-w-[120px]">{a.id}</span>
            </button>
          );
        })}
        <button
          onClick={() => setShowModal(true)}
          className="ml-1 flex items-center gap-1 px-2 py-1.5 text-[12px] font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
          style={{ borderRadius: 4 }}
        >
          <LuPlus size={12} />
          Agent
        </button>
      </div>
      {showModal && (
        <CreateAgentModal
          existingNames={agents.map((a) => a.id)}
          onClose={() => setShowModal(false)}
          onCreate={onCreate}
          submitting={adding}
        />
      )}
    </>
  );
}

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
  const [name, setName] = useState(() => {
    const set = new Set(existingNames);
    let x = 1;
    while (set.has(`agent-${x}`)) x++;
    return `agent-${x}`;
  });
  const [error, setError] = useState<string | null>(null);

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
      setError(err instanceof Error ? err.message : "Failed");
    }
  };

  return (
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
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
            >
              {submitting ? "Creating…" : "Create"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
import { WorkspaceEditor, type OpenFile } from "@/components/workspace-editor";
import { useWorkspaceAgent } from "@/hooks/use-workspace-agent";
import { useWorkspaceFiles, type FsTreeNode } from "@/hooks/use-workspace-files";

interface WorkspaceAgent {
  id: string;
  type: "local" | "cloud";
  harness: string;
  model: string;
  avatar_seed: string | null;
  sdk_session_id: string | null;
  sdk_base_url: string | null;
  last_seen_at: string | null;
}

interface Workspace {
  id: number;
  name: string;
  type: "local" | "cloud";
  agents: WorkspaceAgent[];
  created_at: string;
}

import type { ChatMessage } from "@/hooks/use-workspace-agent";

const MAX_TEXTAREA_HEIGHT = 200;

function SandboxTreeNode({
  node,
  expandedDirs,
  onToggleDir,
  onFileClick,
  depth = 0,
}: {
  node: FsTreeNode;
  expandedDirs: Set<string>;
  onToggleDir: (path: string) => void;
  onFileClick: (node: FsTreeNode) => void;
  depth?: number;
}) {
  const isDir = node.type === "directory";
  const isExpanded = expandedDirs.has(node.path);

  if (isDir) {
    return (
      <div>
        <button
          onClick={() => onToggleDir(node.path)}
          className="group flex items-center gap-1.5 py-0.5 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] transition-colors text-left w-full min-w-0"
          style={{ paddingLeft: `${depth * 14}px` }}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50">
            <path fillRule="evenodd" d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75z" />
          </svg>
          <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate font-medium">{node.name}</span>
        </button>
        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <SandboxTreeNode
                key={child.path}
                node={child}
                expandedDirs={expandedDirs}
                onToggleDir={onToggleDir}
                onFileClick={onFileClick}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={() => onFileClick(node)}
      className="flex items-center gap-1.5 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] py-0.5 transition-colors w-full text-left"
      style={{ paddingLeft: `${depth * 14}px` }}
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50">
        <path fillRule="evenodd" d="M3.75 1.5a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V4.664a.25.25 0 00-.073-.177l-2.914-2.914a.25.25 0 00-.177-.073H3.75zM2 1.75C2 .784 2.784 0 3.75 0h5.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0112.25 16h-8.5A1.75 1.75 0 012 14.25V1.75z" />
      </svg>
      <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate">{node.name}</span>
      {node.size != null && node.size > 0 && (
        <span className="ml-auto text-[10px] text-[var(--color-text-tertiary)] shrink-0">
          {node.size < 1024 ? `${node.size} B` : node.size < 1024 * 1024 ? `${(node.size / 1024).toFixed(1)} KB` : `${(node.size / (1024 * 1024)).toFixed(1)} MB`}
        </span>
      )}
    </button>
  );
}

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);
  const [wsLoading, setWsLoading] = useState(true);
  const [addingAgent, setAddingAgent] = useState(false);
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);

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

  // Chat state — wired to agent-sdk via workspace connect
  const { messages, isLoading, connecting, error: agentError, sendMessage, cancel, sdkBaseUrl, sdkSessionId } = useWorkspaceAgent(workspace ? workspaceId : null);

  // Live sandbox filesystem
  const { tree: fsTree, loading: fsLoading, error: fsError, readFile } = useWorkspaceFiles(sdkBaseUrl, sdkSessionId);

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const lastScrollTopRef = useRef(0);
  const programmaticScrollRef = useRef(false);

  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, MAX_TEXTAREA_HEIGHT) + "px";
    ta.style.overflowY = ta.scrollHeight > MAX_TEXTAREA_HEIGHT ? "auto" : "hidden";
  }, []);

  useEffect(() => { resizeTextarea(); }, [input, resizeTextarea]);

  // Auto-scroll to bottom
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || programmaticScrollRef.current) return;
    const scrollTop = el.scrollTop;
    if (scrollTop < lastScrollTopRef.current) userScrolledUpRef.current = true;
    lastScrollTopRef.current = scrollTop;
    if (el.scrollHeight - scrollTop - el.clientHeight < 40) userScrolledUpRef.current = false;
  }, []);

  useEffect(() => {
    if (!userScrolledUpRef.current && scrollRef.current) {
      programmaticScrollRef.current = true;
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      requestAnimationFrame(() => {
        programmaticScrollRef.current = false;
        if (scrollRef.current) lastScrollTopRef.current = scrollRef.current.scrollTop;
      });
    }
  }, [messages]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    userScrolledUpRef.current = false;
    sendMessage(input.trim());
    setInput("");
  }, [input, isLoading, sendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }, [handleSubmit]);

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
          onClick={() => router.push("/me?tab=workspaces")}
          className="text-sm text-[var(--color-accent)] hover:underline"
        >
          Back to Workspaces
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="shrink-0 h-[52px] px-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center gap-3">
        <button
          onClick={() => router.push("/me?tab=workspaces")}
          className="flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
        >
          <LuArrowLeft size={14} />
        </button>
        <div className="flex flex-col leading-tight">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-semibold">
            {workspace?.type === "cloud" ? "Cloud" : "Local"}
          </span>
          <span className="text-[14px] font-semibold text-[var(--color-text)]">{workspaceName}</span>
        </div>
      </div>

      {/* Split view */}
      <div ref={containerRef} className="flex-1 flex min-h-0">
        {/* Left: File System */}
        <div className="shrink-0 flex flex-col" style={{ width: `${leftWidth}%` }}>
          {/* File tree */}
          <div className="flex-1 overflow-y-auto min-h-0 px-5 pt-4 pb-5">
            {fsLoading && (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
              </div>
            )}
            {fsError && (
              <p className="text-xs text-[var(--color-text-tertiary)] px-1 py-4">{fsError}</p>
            )}
            {!fsLoading && !fsError && fsTree.length === 0 && (
              <p className="text-xs text-[var(--color-text-tertiary)] px-1 py-4">No files yet</p>
            )}
            <div className="space-y-0.5">
              {fsTree.map((node) => (
                <SandboxTreeNode
                  key={node.path}
                  node={node}
                  expandedDirs={expandedDirs}
                  onToggleDir={handleToggleDir}
                  onFileClick={handleFileClick}
                />
              ))}
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
          className={`min-w-0 flex flex-col ${openFiles.length === 0 ? "flex-1" : "shrink-0"}`}
          style={openFiles.length === 0 ? { height: "100%" } : { width: `${chatWidth}%`, height: "100%" }}
        >
          {/* Agent tabs */}
          <AgentTabs
            agents={agents}
            activeAgentId={activeAgent?.id ?? null}
            onSelect={setActiveAgentId}
            onCreate={handleAddAgent}
            adding={addingAgent}
          />

          {!activeAgent ? (
            <div className="flex-1" />
          ) : (
            <>
          {/* Messages */}
          <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto min-h-0 p-4 space-y-3">
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

            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "user" ? (
                  <div className="max-w-[85%] px-3 py-2 rounded-lg bg-[var(--color-accent)] text-white">
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  </div>
                ) : msg.role === "error" ? (
                  <div className="w-[90%] px-3 py-2 text-sm text-red-500 border border-red-500/30 bg-red-500/5 rounded whitespace-pre-wrap">
                    {msg.content}
                  </div>
                ) : (
                  <div className="w-[90%] prose prose-sm max-w-none text-[var(--color-text)]">
                    {msg.toolName && (
                      <div className="text-xs text-[var(--color-text-tertiary)] mb-1">
                        ● {msg.toolName}
                      </div>
                    )}
                    {msg.content ? (
                      <>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                        {msg.streaming && <span className="inline-block w-2 h-4 ml-0.5 bg-[var(--color-text)] animate-pulse" />}
                      </>
                    ) : msg.streaming ? (
                      <div className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
                        <div className="w-1.5 h-1.5 bg-[var(--color-text-tertiary)] rounded-full animate-pulse" />
                        <span>Thinking...</span>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            ))}

            {isLoading && messages.length > 0 && messages[messages.length - 1].role === "user" && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 text-[var(--color-text-tertiary)]">
                  <div className="w-1.5 h-1.5 bg-[var(--color-text-tertiary)] rounded-full animate-pulse" />
                  <span className="text-sm">Thinking...</span>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <form onSubmit={handleSubmit} className="shrink-0 px-3 pb-3 pt-2">
            <div className="border border-[var(--color-border)] rounded-xl bg-[var(--color-surface)]">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask ${agentName} something...`}
                rows={1}
                disabled={isLoading}
                className="w-full resize-none px-3 pt-2.5 pb-1 text-sm bg-transparent text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
                style={{ overflowY: "hidden", outline: "none", boxShadow: "none" }}
              />
              <div className="flex items-center justify-end px-2 pb-2">
                <button
                  type="submit"
                  disabled={isLoading || !input.trim()}
                  className="p-1.5 rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:bg-[var(--color-layer-2)] disabled:text-[var(--color-text-tertiary)] disabled:cursor-not-allowed transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
            </div>
          </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
