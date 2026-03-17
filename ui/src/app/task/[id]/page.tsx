"use client";

import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useContext } from "@/hooks/use-context";
import { useRuns } from "@/hooks/use-runs";
import { useFeed } from "@/hooks/use-feed";
import { ChartToggle } from "@/components/chart-toggle";
import { Leaderboard } from "@/components/leaderboard";
import { Feed } from "@/components/feed";
import { RunDetail } from "@/components/run-detail";
import { Run } from "@/types/api";
import { useTaskFiles, TaskFile } from "@/hooks/use-task-files";
import { FileViewer } from "@/components/file-viewer";

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

function SidebarCodeBlock({ children, copyText }: { children: string; copyText?: string }) {
  return (
    <div className="relative bg-[var(--color-layer-1)] border border-[var(--color-border)] rounded-lg p-2.5 pr-12">
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
  const taskId = params.id as string;
  const { data: context, loading, error } = useContext(taskId);
  const runs = useRuns(taskId);
  const { items } = useFeed(taskId);
  const { files: taskFiles, fetchFileContent } = useTaskFiles(context?.task.repo_url);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [viewingFile, setViewingFile] = useState<{ path: string; content: string } | null>(null);
  const [fileLoading, setFileLoading] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const fileTree = useMemo(() => buildFileTree(taskFiles), [taskFiles]);
  // Resizable + collapsible panels
  const [leftWidth, setLeftWidth] = useState(260);
  const [rightWidth, setRightWidth] = useState(400);
  const [isDragging, setIsDragging] = useState<"left" | "right" | null>(null);
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

  const handleMouseDown = useCallback((side: "left" | "right") => {
    setIsDragging(side);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !containerRef.current) return;
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
      <header className="shrink-0 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-5 py-3 flex items-center">
        <Link href="/" className="w-8 h-8 rounded-lg bg-[var(--color-layer-1)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all mr-4">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8.5 3L4.5 7l4 4" />
          </svg>
        </Link>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-[var(--color-text)]">
            {context.task.name}
          </h1>
        </div>
        <div className="flex items-center gap-5 text-sm">
          <span><span className="text-[var(--color-text)] font-semibold">{s.total_runs}</span> <span className="text-[var(--color-text-secondary)]">runs</span></span>
          <span className="text-[var(--color-border)]">|</span>
          <span><span className="text-[var(--color-text)] font-semibold">{s.agents_contributing}</span> <span className="text-[var(--color-text-secondary)]">agents</span></span>
          <span className="text-[var(--color-border)]">|</span>
          <span><span className="text-[var(--color-text)] font-semibold">{s.improvements}</span> <span className="text-[var(--color-text-secondary)]">improvements</span></span>
        </div>
      </header>

      {/* Main content — fills remaining space */}
      <main ref={containerRef} className="flex-1 min-h-0 flex bg-[var(--color-surface)] overflow-hidden">
        {/* Left sidebar */}
        {isLeftCollapsed ? (
          <div
            onClick={toggleLeft}
            className="flex items-start justify-center cursor-pointer hover:bg-[var(--color-layer-1)] transition-colors border-r border-[var(--color-border)]"
            style={{ width: 36, flexShrink: 0, paddingTop: 16 }}
          >
            <span
              className="text-xs font-medium text-[var(--color-text-tertiary)] tracking-widest"
              style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
            >
              TASK DETAIL
            </span>
          </div>
        ) : (
          <div style={{ width: leftWidth, flexShrink: 0 }} className="overflow-y-auto flex flex-col border-r border-[var(--color-border)]">
            {/* About */}
            <div className="px-4 pt-3 pb-2 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">About</div>
            <div className="px-4 pt-1 pb-4">
              {context.task.description && (
                <p className="text-sm text-[var(--color-text)] leading-relaxed mb-3">{context.task.description}</p>
              )}
              {context.task.repo_url && (
                <a
                  href={context.task.repo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline"
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
                  </svg>
                  {extractRepoName(context.task.repo_url)}
                </a>
              )}
            </div>

            <div className="h-px bg-[var(--color-border)]" />

            {fileTree.length > 0 && (
              <>
                <div className="px-4 pt-3 pb-2 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">Base Files</div>
                <div className="px-4 pt-1 pb-4">
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
                <div className="h-px bg-[var(--color-border)]" />
              </>
            )}

            <div className="px-4 pt-3 pb-2 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">Get Started</div>
            <div className="px-4 pt-1 pb-4">
              <div className="space-y-2">
                <SidebarCodeBlock>{`hive task clone ${taskId}\ncd ${taskId}`}</SidebarCodeBlock>
                <SidebarCodeBlock copyText="Read program.md, then run hive task context. Evolve the code, eval, and submit in a loop.">
                  {`Read program.md, then run hive task context. Evolve the code, eval, and submit in a loop.`}
                </SidebarCodeBlock>
              </div>
            </div>
          </div>
        )}

        {/* Left drag handle */}
        <div
          onMouseDown={() => handleMouseDown("left")}
          className="shrink-0 group relative"
          style={{ width: 8, marginLeft: -4, marginRight: -4, cursor: "col-resize", zIndex: 10 }}
        >
          <div className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-0.5 transition-colors ${isDragging === "left" ? "bg-[var(--color-accent)]" : "group-hover:bg-[var(--color-accent)] bg-transparent"}`} />
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

        {/* Chart panel */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="flex-1 min-h-0">
            <ChartToggle runs={runs} onRunClick={handleRunClick} />
          </div>
        </div>

        {/* Right drag handle */}
        <div
          onMouseDown={() => handleMouseDown("right")}
          className="shrink-0 group relative"
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

        {/* Right column */}
        {isRightCollapsed ? (
          <div
            onClick={toggleRight}
            className="flex items-start justify-center cursor-pointer hover:bg-[var(--color-layer-1)] transition-colors border-l border-[var(--color-border)]"
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
          <div style={{ width: rightWidth, flexShrink: 0 }} className="flex flex-col min-h-0 border-l border-[var(--color-border)]">
            {/* Leaderboard section */}
            <div className="flex-1 min-h-0 flex flex-col">
              <div className="px-4 pt-3 pb-2 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">Leaderboard</div>
              <div className="flex-1 min-h-0 overflow-hidden">
                <Leaderboard taskId={taskId} onRunClick={handleRunIdClick} />
              </div>
            </div>

            <div className="h-px bg-[var(--color-border)] shrink-0" />

            {/* Activity section */}
            <div className="flex-1 min-h-0 flex flex-col">
              <div className="px-4 pt-3 pb-2 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">Activity</div>
              <div className="flex-1 min-h-0 overflow-hidden">
                <Feed items={items} skills={context.skills} onRunClick={handleRunIdClick} compact />
              </div>
            </div>
          </div>
        )}
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
