"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { LuArrowLeft, LuPlus, LuFile, LuFolder, LuUpload } from "react-icons/lu";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getAgentColor } from "@/lib/agent-colors";
import { WorkspaceEditor, type OpenFile } from "@/components/workspace-editor";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const MAX_TEXTAREA_HEIGHT = 200;

interface TreeNode {
  name: string;
  path: string;
  children: TreeNode[];
  isFile: boolean;
}

type PendingCreate = { parentPath: string; kind: "file" | "folder" };

function FolderAddMenu({ pos, onSelect, onClose }: { pos: { x: number; y: number }; onSelect: (kind: "file" | "folder" | "upload") => void; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  if (typeof window === "undefined") return null;
  return createPortal(
    <div
      ref={ref}
      className="fixed z-[10000] bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-lg py-1.5 min-w-[150px]"
      style={{ left: pos.x, top: pos.y }}
    >
      <button onClick={() => { onSelect("file"); onClose(); }} className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors text-left">
        <LuFile size={12} /> New File
      </button>
      <button onClick={() => { onSelect("folder"); onClose(); }} className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors text-left">
        <LuFolder size={12} /> New Folder
      </button>
      <button onClick={() => { onSelect("upload"); onClose(); }} className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors text-left">
        <LuUpload size={12} /> Upload File
      </button>
    </div>,
    document.body,
  );
}

function InlineNameInput({ kind, depth, onSubmit, onCancel }: { kind: "file" | "folder"; depth: number; onSubmit: (name: string) => void; onCancel: () => void }) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { inputRef.current?.focus(); }, []);

  return (
    <div className="flex items-center gap-1.5 py-0.5" style={{ paddingLeft: `${depth * 14}px` }}>
      {kind === "folder" ? (
        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50 text-[var(--color-text)]">
          <path fillRule="evenodd" d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75z" />
        </svg>
      ) : (
        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50 text-[var(--color-text)]">
          <path fillRule="evenodd" d="M3.75 1.5a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V4.664a.25.25 0 00-.073-.177l-2.914-2.914a.25.25 0 00-.177-.073H3.75zM2 1.75C2 .784 2.784 0 3.75 0h5.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0112.25 16h-8.5A1.75 1.75 0 012 14.25V1.75z" />
        </svg>
      )}
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) onSubmit(value.trim());
          if (e.key === "Escape") onCancel();
        }}
        onBlur={() => { if (value.trim()) onSubmit(value.trim()); else onCancel(); }}
        placeholder={kind === "folder" ? "folder-name" : "filename.ext"}
        className="flex-1 min-w-0 text-xs font-[family-name:var(--font-ibm-plex-mono)] bg-[var(--color-bg)] border border-[var(--color-accent)] px-1.5 py-0.5 text-[var(--color-text)]"
        style={{ outline: "none", boxShadow: "none" }}
      />
    </div>
  );
}

function FileTreeNode({
  node,
  expandedDirs,
  onToggleDir,
  onAddNode,
  onFileClick,
  pendingCreate,
  onPendingCreate,
  onCancelCreate,
  depth = 0,
}: {
  node: TreeNode;
  expandedDirs: Set<string>;
  onToggleDir: (path: string) => void;
  onAddNode: (parentPath: string, name: string, isFile: boolean) => void;
  onFileClick: (node: TreeNode) => void;
  pendingCreate: PendingCreate | null;
  onPendingCreate: (p: PendingCreate) => void;
  onCancelCreate: () => void;
  depth?: number;
}) {
  const isExpanded = expandedDirs.has(node.path);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const hasPending = pendingCreate?.parentPath === node.path;

  if (!node.isFile) {
    return (
      <div>
        <div
          className="group flex items-center py-0.5"
          style={{ paddingLeft: `${depth * 14}px` }}
        >
          <button
            onClick={() => onToggleDir(node.path)}
            className="flex items-center gap-1.5 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] transition-colors text-left min-w-0"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50">
              <path fillRule="evenodd" d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75z" />
            </svg>
            <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate font-medium">{node.name}</span>
          </button>
          <div className="ml-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (menuPos) { setMenuPos(null); return; }
                const rect = e.currentTarget.getBoundingClientRect();
                setMenuPos({ x: rect.right + 4, y: rect.top });
              }}
              className="w-4 h-4 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <LuPlus size={11} />
            </button>
            {menuPos && (
              <FolderAddMenu
                pos={menuPos}
                onSelect={(kind) => {
                  if (kind === "upload") return;
                  if (!isExpanded) onToggleDir(node.path);
                  onPendingCreate({ parentPath: node.path, kind });
                }}
                onClose={() => setMenuPos(null)}
              />
            )}
          </div>
        </div>
        {isExpanded && (
          <div>
            {hasPending && pendingCreate && (
              <InlineNameInput
                kind={pendingCreate.kind}
                depth={depth + 1}
                onSubmit={(name) => { onAddNode(node.path, name, pendingCreate.kind === "file"); onCancelCreate(); }}
                onCancel={onCancelCreate}
              />
            )}
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                expandedDirs={expandedDirs}
                onToggleDir={onToggleDir}
                onAddNode={onAddNode}
                onFileClick={onFileClick}
                pendingCreate={pendingCreate}
                onPendingCreate={onPendingCreate}
                onCancelCreate={onCancelCreate}
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
    </button>
  );
}

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const agentId = params.id as string;
  const workspaceName = searchParams.get("name") ?? agentId;
  const agentName = searchParams.get("agent") ?? agentId;
  const color = getAgentColor(agentName);
  const initials = agentName.split("-").map(w => w[0]?.toUpperCase() ?? "").join("").slice(0, 2) || agentName.slice(0, 2).toUpperCase();

  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(() => new Set([workspaceName]));
  const [leftWidth, setLeftWidth] = useState(20);
  const [chatWidth, setChatWidth] = useState(35);
  const [pendingCreate, setPendingCreate] = useState<PendingCreate | null>(null);
  const [fileTree, setFileTree] = useState<TreeNode[]>([
    { name: workspaceName, path: workspaceName, isFile: false, children: [] },
  ]);
  const [isDragging, setIsDragging] = useState<"left" | "right" | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Editor state
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);

  const handleFileClick = useCallback((node: TreeNode) => {
    setOpenFiles((prev) => {
      if (prev.some((f) => f.path === node.path)) return prev;
      return [...prev, { path: node.path, name: node.name, content: "" }];
    });
    setActivePath(node.path);
  }, []);

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

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
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
    const userMsg: ChatMessage = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    // Simulate assistant response (placeholder until backend is wired)
    setTimeout(() => {
      setMessages((prev) => [...prev, { role: "assistant", content: "This is a placeholder response. The chat backend is not connected yet." }]);
      setIsLoading(false);
    }, 1000);
  }, [input, isLoading]);

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

  const handleAddNode = useCallback((parentPath: string, name: string, isFile: boolean) => {
    setFileTree((prev) => {
      const addToTree = (nodes: TreeNode[]): TreeNode[] =>
        nodes.map((n) => {
          if (n.path === parentPath && !n.isFile) {
            const newPath = `${n.path}/${name}`;
            if (n.children.some((c) => c.path === newPath)) return n;
            const newNode: TreeNode = { name, path: newPath, isFile, children: [] };
            const updated = [...n.children, newNode].sort((a, b) => {
              if (a.isFile !== b.isFile) return a.isFile ? 1 : -1;
              return a.name.localeCompare(b.name);
            });
            return { ...n, children: updated };
          }
          return { ...n, children: addToTree(n.children) };
        });
      return addToTree(prev);
    });
  }, []);

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
        <span className="text-[14px] font-semibold text-[var(--color-text)]">{workspaceName}</span>
      </div>

      {/* Split view */}
      <div ref={containerRef} className="flex-1 flex min-h-0">
        {/* Left: File System */}
        <div className="shrink-0 flex flex-col" style={{ width: `${leftWidth}%` }}>
          {/* File tree */}
          <div className="flex-1 overflow-y-auto min-h-0 px-5 pt-4 pb-5">
            <div className="space-y-0.5">
              {fileTree.map((node) => (
                <FileTreeNode
                  key={node.path}
                  node={node}
                  expandedDirs={expandedDirs}
                  onToggleDir={handleToggleDir}
                  onAddNode={handleAddNode}
                  onFileClick={handleFileClick}
                  pendingCreate={pendingCreate}
                  onPendingCreate={setPendingCreate}
                  onCancelCreate={() => setPendingCreate(null)}
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
          {/* Agent indicator */}
          <div className="shrink-0 px-4 py-3 flex items-center gap-2">
            <div
              className="w-5 h-5 rounded flex items-center justify-center text-white font-bold text-[8px]"
              style={{ backgroundColor: color }}
            >
              {initials}
            </div>
            <span className="text-sm font-medium text-[var(--color-text)]">{agentName}</span>
          </div>

          {/* Messages */}
          <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto min-h-0 p-4 space-y-3">
            {messages.length === 0 && (
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
                ) : (
                  <div className="w-[90%] prose prose-sm max-w-none text-[var(--color-text)]">
                    {msg.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    ) : isLoading && i === messages.length - 1 ? (
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
        </div>
      </div>
    </div>
  );
}
