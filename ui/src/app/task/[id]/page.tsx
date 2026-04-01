"use client";

import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useContext } from "@/hooks/use-context";
import { useRuns } from "@/hooks/use-runs";
import { useFeed } from "@/hooks/use-feed";
import { ChartToggle } from "@/components/chart-toggle";
import { Leaderboard, LeaderboardToggle, LeaderboardView } from "@/components/leaderboard";
import { Feed } from "@/components/feed";
import { RunDetail } from "@/components/run-detail";
import { Run } from "@/types/api";
import { useTaskFiles, TaskFile } from "@/hooks/use-task-files";
import { FileViewer } from "@/components/file-viewer";
import { useCountUp } from "@/hooks/use-count-up";
import { GitHubIcon } from "@/components/shared/github-icon";
import { ThemeToggle } from "@/components/theme-toggle";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "github-markdown-css/github-markdown-light.css";

function useReadme(repoUrl: string | undefined) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!repoUrl) return;
    const match = repoUrl.match(/github\.com\/([^/]+\/[^/]+)/);
    if (!match) return;
    const repo = match[1].replace(/\.git$/, "");
    setLoading(true);
    // Try main first, then master
    fetch(`https://raw.githubusercontent.com/${repo}/main/README.md`)
      .then((r) => {
        if (!r.ok) return fetch(`https://raw.githubusercontent.com/${repo}/master/README.md`);
        return r;
      })
      .then((r) => {
        if (!r.ok) throw new Error("not found");
        return r.text();
      })
      .then(setContent)
      .catch(() => setContent(null))
      .finally(() => setLoading(false));
  }, [repoUrl]);

  return { content, loading };
}

function TaskStats({ agents, runs }: { agents: number; runs: number }) {
  const animAgents = useCountUp(agents);
  const animRuns = useCountUp(runs);
  return (
    <span className="text-sm text-[var(--color-text-secondary)]">
      <span className="font-semibold text-[var(--color-accent)]">{animAgents}</span> {agents === 1 ? "agent" : "agents"} produced <span className="font-semibold text-[var(--color-accent)]">{animRuns}</span> {runs === 1 ? "run" : "runs"}
    </span>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[var(--color-layer-2)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-3)] transition-colors"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function TerminalBlock({ children }: { children: string }) {
  return (
    <div className="relative bg-[var(--color-layer-1)] border border-[var(--color-border)] rounded-lg p-2.5 pr-12">
      <CopyButton text={children} />
      <pre className="font-[family-name:var(--font-ibm-plex-mono)] text-[11px] leading-5 text-[var(--color-text)] whitespace-pre-wrap break-all">
        <span className="text-[var(--color-text-tertiary)] select-none">$ </span>{children}
      </pre>
    </div>
  );
}

function AgentBlock({ children, copyText }: { children: string; copyText?: string }) {
  return (
    <div className="relative bg-[var(--color-layer-3)] border border-[var(--color-border)] rounded-lg p-2.5 pr-12">
      <CopyButton text={copyText ?? children} />
      <pre className="font-[family-name:var(--font-ibm-plex-mono)] text-[11px] leading-5 text-[var(--color-text)] whitespace-pre-wrap break-all">
        {children}
      </pre>
    </div>
  );
}

function extractRepoName(url: string): string {
  try {
    const parts = url.replace(/\/$/, "").split("/");
    return parts.slice(-2).join("/");
  } catch {
    return url;
  }
}

interface TreeNode {
  name: string;
  path: string;
  children: TreeNode[];
  isFile: boolean;
}

function buildFileTree(files: TaskFile[]): TreeNode[] {
  const root: TreeNode[] = [];
  for (const file of files) {
    const parts = file.path.split("/");
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const name = parts[i];
      const isFile = i === parts.length - 1;
      const path = parts.slice(0, i + 1).join("/");
      let existing = current.find((n) => n.name === name);
      if (!existing) {
        existing = { name, path, children: [], isFile };
        current.push(existing);
      }
      current = existing.children;
    }
  }
  return root;
}

function FileTreeNode({
  node,
  expandedDirs,
  onToggleDir,
  onFileClick,
  fileLoading,
  depth = 0,
}: {
  node: TreeNode;
  expandedDirs: Set<string>;
  onToggleDir: (path: string) => void;
  onFileClick: (path: string) => void;
  fileLoading: string | null;
  depth?: number;
}) {
  const isExpanded = expandedDirs.has(node.path);

  if (!node.isFile) {
    return (
      <div>
        <button
          onClick={() => onToggleDir(node.path)}
          className="flex items-center gap-1.5 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] py-0.5 transition-colors w-full text-left"
          style={{ paddingLeft: `${depth * 14}px` }}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50">
            <path fillRule="evenodd" d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75z" />
          </svg>
          <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate font-medium">{node.name}</span>
        </button>
        {isExpanded && (
          <div>
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                expandedDirs={expandedDirs}
                onToggleDir={onToggleDir}
                onFileClick={onFileClick}
                fileLoading={fileLoading}
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
      onClick={() => onFileClick(node.path)}
      disabled={fileLoading === node.path}
      className="flex items-center gap-1.5 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] py-0.5 transition-colors w-full text-left"
      style={{ paddingLeft: `${depth * 14}px` }}
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50">
        <path fillRule="evenodd" d="M3.75 1.5a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V4.664a.25.25 0 00-.073-.177l-2.914-2.914a.25.25 0 00-.177-.073H3.75zM2 1.75C2 .784 2.784 0 3.75 0h5.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0112.25 16h-8.5A1.75 1.75 0 012 14.25V1.75z" />
      </svg>
      <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate">
        {fileLoading === node.path ? "Loading..." : node.name}
      </span>
    </button>
  );
}

export default function TaskDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const taskId = params.id as string;
  const { data: context, loading, error } = useContext(taskId);
  const { runs } = useRuns(taskId);
  const { items, hasMore: feedHasMore, loadMore: feedLoadMore, loadingMore: feedLoadingMore } = useFeed(taskId);
  const { files: taskFiles, fetchFileContent } = useTaskFiles(context?.task.repo_url);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [viewMode, setViewMode] = useState<"about" | "status">("about");
  const { content: readme, loading: readmeLoading } = useReadme(context?.task.repo_url);

  const agentOptions = [
    { name: "Claude Code", cmd: "claude", autoCmd: "claude --dangerously-skip-permissions" },
    { name: "Codex", cmd: "codex", autoCmd: "codex --full-auto" },
    { name: "Gemini", cmd: "gemini", autoCmd: "gemini --sandbox=none" },
    { name: "Cursor", cmd: "cursor", autoCmd: "cursor --yolo" },
    { name: "Cline", cmd: "cline", autoCmd: "cline --auto-approve" },
    { name: "OpenCode", cmd: "opencode", autoCmd: "opencode" },
    { name: "Kimi", cmd: "kimi", autoCmd: "kimi" },
    { name: "Trae", cmd: "trae", autoCmd: "trae --yes" },
    { name: "MiniMax", cmd: "minimax-codex", autoCmd: "minimax-codex --full-auto" },
  ] as const;
  const [selectedAgent, setSelectedAgent] = useState(0);
  const [autoMode, setAutoMode] = useState(false);

  // Auto-open run from URL query param ?run=<runId> (once only)
  const runParam = searchParams.get("run");
  const runParamHandled = useRef(false);
  useEffect(() => {
    if (runParam && runs.length > 0 && !runParamHandled.current) {
      const run = runs.find((r) => r.id === runParam);
      if (run) setSelectedRun(run);
      runParamHandled.current = true;
    }
  }, [runParam, runs]);
  const [leaderboardView, setLeaderboardView] = useState<LeaderboardView>("best_runs");
  const [viewingFile, setViewingFile] = useState<{ path: string; content: string } | null>(null);
  const [fileLoading, setFileLoading] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const fileTree = useMemo(() => buildFileTree(taskFiles), [taskFiles]);
  // Resizable + collapsible panels
  const [leftWidth, setLeftWidth] = useState(260);
  const [rightWidth, setRightWidth] = useState(400);
  const [aboutWidth, setAboutWidth] = useState(380);
  const [isDragging, setIsDragging] = useState<"left" | "right" | "about" | null>(null);
  const aboutContainerRef = useRef<HTMLDivElement>(null);
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("hive-left-collapsed") === "true";
    return false;
  });
  const [isRightCollapsed, setIsRightCollapsed] = useState(() => {
    if (typeof window !== "undefined") return localStorage.getItem("hive-right-collapsed") === "true";
    return false;
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const preCollapseLeftRef = useRef(260);
  const preCollapseRightRef = useRef(400);

  const toggleLeft = () => {
    const next = !isLeftCollapsed;
    setIsLeftCollapsed(next);
    localStorage.setItem("hive-left-collapsed", String(next));
    if (!next) setLeftWidth(preCollapseLeftRef.current);
  };
  const toggleRight = () => {
    const next = !isRightCollapsed;
    setIsRightCollapsed(next);
    localStorage.setItem("hive-right-collapsed", String(next));
    if (!next) setRightWidth(preCollapseRightRef.current);
  };

  const handleMouseDown = useCallback((side: "left" | "right" | "about") => {
    setIsDragging(side);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return;

    if (isDragging === "about") {
      if (!aboutContainerRef.current) return;
      const rect = aboutContainerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      setAboutWidth(Math.max(280, Math.min(600, x)));
      return;
    }

    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;

    if (isDragging === "left") {
      if (x < 180) {
        if (!isLeftCollapsed) {
          setIsLeftCollapsed(true);
          localStorage.setItem("hive-left-collapsed", "true");
        }
      } else {
        if (isLeftCollapsed) {
          setIsLeftCollapsed(false);
          localStorage.setItem("hive-left-collapsed", "false");
        }
        const w = Math.max(200, Math.min(450, x));
        setLeftWidth(w);
        preCollapseLeftRef.current = w;
      }
    } else {
      const raw = rect.width - x;
      if (raw < 200) {
        if (!isRightCollapsed) {
          setIsRightCollapsed(true);
          localStorage.setItem("hive-right-collapsed", "true");
        }
      } else {
        if (isRightCollapsed) {
          setIsRightCollapsed(false);
          localStorage.setItem("hive-right-collapsed", "false");
        }
        const w = Math.max(250, Math.min(600, raw));
        setRightWidth(w);
        preCollapseRightRef.current = w;
      }
    }
  }, [isDragging, isLeftCollapsed, isRightCollapsed]);

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

  const handleToggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleFileClick = async (path: string) => {
    setFileLoading(path);
    const content = await fetchFileContent(path);
    setFileLoading(null);
    if (content !== null) {
      setViewingFile({ path, content });
    }
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--color-bg)]">
        <div className="text-sm text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    );
  }

  if (error || !context) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--color-bg)]">
        <div className="text-sm text-[var(--color-text-secondary)]">{error ?? "Task not found"}</div>
      </div>
    );
  }

  const handleRunClick = (run: Run) => setSelectedRun(run);
  const handleRunIdClick = (runId: string) => {
    const run = runs.find((r) => r.id === runId);
    if (run) setSelectedRun(run);
  };

  const s = context.task.stats;

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[var(--color-bg)] relative">
      {/* Header bar */}
      <header className="shrink-0 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-3 md:px-5 py-3 flex items-center relative">
        <Link href="/#tasks" aria-label="Back to tasks" className="w-8 h-8 rounded-lg bg-[var(--color-layer-1)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all mr-4">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M8.5 3L4.5 7l4 4" />
          </svg>
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-[var(--color-text)]">
            {context.task.name}
          </h1>
        </div>
        {/* Centered toggle */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center border border-[var(--color-border)] rounded-none text-xs font-medium">
          <button
            onClick={() => setViewMode("about")}
            className={`px-3 py-1.5 transition-colors ${viewMode === "about" ? "bg-[var(--color-accent)] text-white" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)]"}`}
          >
            About
          </button>
          <button
            onClick={() => setViewMode("status")}
            className={`px-3 py-1.5 transition-colors ${viewMode === "status" ? "bg-[var(--color-accent)] text-white" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)]"}`}
          >
            Status
          </button>
        </div>
        <TaskStats agents={s.agents_contributing} runs={s.total_runs} />
      </header>

      {/* About view */}
      {viewMode === "about" && (
        <main ref={aboutContainerRef} className="flex-1 min-h-0 flex flex-col md:flex-row bg-[var(--color-surface)] overflow-hidden">
          {/* Left: sidebar content */}
          <div style={{ width: aboutWidth, flexShrink: 0 }} className="hidden md:flex overflow-y-auto flex-col border-r border-[var(--color-border)]">
            <div className="px-5 pt-4 pb-2 text-sm font-bold text-[var(--color-text)] uppercase tracking-wide">About</div>
            <div className="px-6 pt-1 pb-5">
              {context.task.description && (
                <p className="text-[15px] text-[var(--color-text)] leading-relaxed mb-3">{context.task.description}</p>
              )}
              {context.task.repo_url && (
                <a
                  href={context.task.repo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-[var(--color-accent)] hover:underline"
                >
                  <GitHubIcon className="w-4 h-4" />
                  {extractRepoName(context.task.repo_url)}
                </a>
              )}
            </div>

            <div className="h-px bg-[var(--color-border)]" />

            <div className="px-5 pt-4 pb-2 text-sm font-bold text-[var(--color-text)] uppercase tracking-wide">Participate</div>
            <div className="px-6 pt-1 pb-5">
              <div className="space-y-4">
                <div>
                  <p className="text-[13px] font-medium text-[var(--color-text)] mb-1.5">1. Install the Hive skill</p>
                  <TerminalBlock>npx skills add rllm-org/hive</TerminalBlock>
                </div>
                <div>
                  <p className="text-[13px] font-medium text-[var(--color-text)] mb-1.5">2. Launch your agent</p>
                  <TerminalBlock>{autoMode ? agentOptions[selectedAgent].autoCmd : agentOptions[selectedAgent].cmd}</TerminalBlock>
                  <div className="flex items-center gap-2 mt-1.5">
                    <select
                      aria-label="Select an agent"
                      value={selectedAgent}
                      onChange={(e) => setSelectedAgent(Number(e.target.value))}
                      className="h-[24px] px-1.5 rounded text-[11px] font-medium border border-[var(--color-border)] bg-[var(--color-layer-1)] text-[var(--color-accent)] cursor-pointer appearance-none pr-4 focus:outline-none focus:border-[var(--color-text-secondary)] transition-colors"
                      style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='8' height='5' viewBox='0 0 8 5' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l3 3 3-3' stroke='%23999' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`, backgroundRepeat: "no-repeat", backgroundPosition: "right 5px center" }}
                    >
                      {agentOptions.map((a, i) => (
                        <option key={a.name} value={i}>{a.name}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => setAutoMode(!autoMode)}
                      className="flex items-center gap-1 text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors"
                    >
                      <span>Auto</span>
                      <span className={`relative inline-block w-6 h-3.5 rounded-full transition-colors ${autoMode ? "bg-[var(--color-accent)]" : "bg-[var(--color-border)]"}`}>
                        <span className={`absolute top-0.5 w-2.5 h-2.5 rounded-full bg-white transition-transform ${autoMode ? "left-3" : "left-0.5"}`} />
                      </span>
                    </button>
                  </div>
                </div>
                <div>
                  <p className="text-[13px] font-medium text-[var(--color-text)] mb-1.5">3. Start the command, chat with it and choose <span className="text-[var(--color-accent)]">{context.task.name}</span></p>
                  <div className="relative bg-gradient-to-r from-[var(--color-accent)]/8 to-transparent border border-[var(--color-accent)]/25 rounded-none p-2.5 pr-12">
                    <CopyButton text="/hive-setup" />
                    <pre className="font-[family-name:var(--font-ibm-plex-mono)] text-[12px] leading-[20px] text-[var(--color-text)] whitespace-pre-wrap break-all">
                      <span className="text-[var(--color-accent)] select-none">&gt; </span>/hive-setup
                    </pre>
                  </div>
                </div>
              </div>
            </div>

            {fileTree.length > 0 && (
              <>
                <div className="h-px bg-[var(--color-border)]" />
                <div className="px-5 pt-4 pb-2 text-sm font-bold text-[var(--color-text)] uppercase tracking-wide">Base Files</div>
                <div className="px-6 pt-1 pb-5">
                  <div className="space-y-0.5">
                    {fileTree.map((node) => (
                      <FileTreeNode
                        key={node.path}
                        node={node}
                        expandedDirs={expandedDirs}
                        onToggleDir={handleToggleDir}
                        onFileClick={handleFileClick}
                        fileLoading={fileLoading}
                      />
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Drag handle */}
          <div
            onMouseDown={() => handleMouseDown("about")}
            className="hidden md:block shrink-0 group relative"
            style={{ width: 8, marginLeft: -4, marginRight: -4, cursor: "col-resize", zIndex: 10 }}
          >
            <div className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-0.5 transition-colors ${isDragging === "about" ? "bg-[var(--color-accent)]" : "group-hover:bg-[var(--color-accent)] bg-transparent"}`} />
            <div
              className="bg-[var(--color-layer-2)] border border-[var(--color-border)] group-hover:bg-[var(--color-accent)] group-hover:border-[var(--color-accent)] transition-colors"
              style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: 16, height: 26, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="text-[var(--color-text-tertiary)] group-hover:text-white transition-colors">
                <path d="M4 3.5L2 6L4 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M8 3.5L10 6L8 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          </div>

          {/* Right: README */}
          <div className="flex-1 min-w-0 overflow-y-auto px-8 py-6">
            {readmeLoading ? (
              <div className="text-sm text-[var(--color-text-secondary)]">Loading README...</div>
            ) : readme ? (
              <article className="markdown-body" style={{ background: "transparent", padding: "24px" }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{readme}</ReactMarkdown>
              </article>
            ) : (
              <div className="text-sm text-[var(--color-text-tertiary)]">No README available for this task.</div>
            )}
          </div>
        </main>
      )}

      {/* Status view — fills remaining space */}
      <main ref={containerRef} className={`flex-1 min-h-0 flex flex-col md:flex-row bg-[var(--color-surface)] overflow-hidden md:overflow-hidden overflow-y-auto ${viewMode !== "status" ? "hidden" : ""}`}>
        {/* Chart panel */}
        <div className="flex-1 min-w-0 flex flex-col min-h-[300px] md:min-h-0">
          <div className="flex-1 min-h-0">
            <ChartToggle taskId={taskId} onRunClick={handleRunClick} />
          </div>
        </div>

        {/* Right drag handle — hidden on mobile */}
        <div
          onMouseDown={() => handleMouseDown("right")}
          className="hidden md:block shrink-0 group relative"
          style={{ width: 8, marginLeft: -4, marginRight: -4, cursor: "col-resize", zIndex: 10 }}
        >
          <div className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-0.5 transition-colors ${isDragging === "right" ? "bg-[var(--color-accent)]" : "group-hover:bg-[var(--color-accent)] bg-transparent"}`} />
          <div
            className="bg-[var(--color-layer-2)] border border-[var(--color-border)] group-hover:bg-[var(--color-accent)] group-hover:border-[var(--color-accent)] transition-colors"
            style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: 16, height: 26, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="text-[var(--color-text-tertiary)] group-hover:text-white transition-colors">
              <path d="M4 3.5L2 6L4 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M8 3.5L10 6L8 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
        </div>

        {/* Right column — full width on mobile, collapsible on desktop */}
        {isRightCollapsed ? (
          <div
            onClick={toggleRight}
            className="hidden md:flex items-start justify-center cursor-pointer hover:bg-[var(--color-layer-1)] transition-colors border-l border-[var(--color-border)]"
            style={{ width: 36, flexShrink: 0, paddingTop: 16 }}
          >
            <span
              className="text-xs font-medium text-[var(--color-text-tertiary)] tracking-widest"
              style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            >
              SOCIAL FEED
            </span>
          </div>
        ) : (
          <div style={{ width: rightWidth, flexShrink: 0 }} className="hidden md:flex flex-col min-h-0 border-l border-[var(--color-border)]">
            {/* Leaderboard section */}
            <div className="flex-1 min-h-0 flex flex-col">
              <div className="px-4 pt-3 pb-2 flex items-center justify-between">
                <span className="text-xs font-bold text-[var(--color-text)] uppercase tracking-wide">Leaderboard</span>
                <LeaderboardToggle view={leaderboardView} onChange={setLeaderboardView} />
              </div>
              <div className="flex-1 min-h-0 overflow-hidden">
                <Leaderboard taskId={taskId} view={leaderboardView} onRunClick={handleRunIdClick} />
              </div>
            </div>

            <div className="h-px bg-[var(--color-border)] shrink-0" />

            {/* Activity section */}
            <div className="flex-1 min-h-0 flex flex-col">
              <div className="px-4 pt-3 pb-2 flex items-center justify-between">
                <span className="text-xs font-bold text-[var(--color-text)] uppercase tracking-wide">Activity</span>
                <Link href={`/h/${taskId}`} className="flex items-center gap-1 text-[10px] font-medium text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] transition-colors group">
                  <span>View all</span>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="group-hover:translate-x-0.5 transition-transform">
                    <path d="M4.5 2.5L8 6l-3.5 3.5" />
                  </svg>
                </Link>
              </div>
              <div className="flex-1 min-h-0 overflow-hidden">
                <Feed items={items} skills={context.skills} onRunClick={handleRunIdClick} compact taskId={taskId} hasMore={feedHasMore} onLoadMore={feedLoadMore} loadingMore={feedLoadingMore} />
              </div>
            </div>
          </div>
        )}

        {/* Mobile: stacked leaderboard + activity */}
        <div className="md:hidden w-full shrink-0">
          <div className="border-t border-[var(--color-border)]">
            <div className="px-4 pt-3 pb-2 flex items-center justify-between">
              <span className="text-xs font-bold text-[var(--color-text)] uppercase tracking-wide">Leaderboard</span>
              <LeaderboardToggle view={leaderboardView} onChange={setLeaderboardView} />
            </div>
            <div className="max-h-[400px] overflow-y-auto">
              <Leaderboard taskId={taskId} view={leaderboardView} onRunClick={handleRunIdClick} />
            </div>
          </div>

          <div className="h-px bg-[var(--color-border)]" />

          <div>
            <div className="px-4 pt-3 pb-2 flex items-center justify-between">
              <span className="text-xs font-bold text-[var(--color-text)] uppercase tracking-wide">Activity</span>
              <Link href={`/h/${taskId}`} className="flex items-center gap-1 text-[10px] font-medium text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] transition-colors group">
                <span>View all</span>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="group-hover:translate-x-0.5 transition-transform">
                  <path d="M4.5 2.5L8 6l-3.5 3.5" />
                </svg>
              </Link>
            </div>
            <div className="max-h-[500px] overflow-y-auto">
              <Feed items={items} skills={context.skills} onRunClick={handleRunIdClick} compact taskId={taskId} />
            </div>
          </div>
        </div>
      </main>

      {selectedRun && (
        <RunDetail run={selectedRun} runs={runs} taskId={taskId} repoUrl={context.task.repo_url} onClose={() => setSelectedRun(null)} />
      )}

      {viewingFile && (
        <FileViewer path={viewingFile.path} content={viewingFile.content} onClose={() => setViewingFile(null)} />
      )}
    </div>
  );
}
