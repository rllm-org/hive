"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";
import { DiffViewer } from "@/components/diff-viewer";
import { fetchGitHubDiff } from "@/lib/github-diff";
import { apiFetch } from "@/lib/api";
import { resolveRun, resolveId, buildRunMap } from "@/lib/run-utils";

interface FullRun extends Run {
  post_id?: number;
  repo_url?: string;
  fork_url?: string;
  base_sha?: string;
}

interface RunDetailProps {
  run: Run;
  runs: Run[];
  taskId: string;
  repoUrl?: string;
  onClose: () => void;
}

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function buildAncestorChain(run: Run, allRuns: Run[]): Run[] {
  const runMap = buildRunMap(allRuns);
  const chain: Run[] = [];
  let current: Run | undefined = run;
  while (current) {
    chain.unshift(current);
    current = current.parent_id ? resolveRun(current.parent_id, runMap) : undefined;
  }
  return chain;
}

export function RunDetail({ run, runs, taskId, repoUrl, onClose }: RunDetailProps) {
  const [fullRun, setFullRun] = useState<FullRun | null>(null);
  const [compareBaseId, setCompareBaseId] = useState<string>(
    () => {
      if (!run.parent_id) return run.id;
      return resolveId(run.parent_id, runs.map((r) => r.id)) ?? run.id;
    }
  );
  const [diff, setDiff] = useState<string | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const chain = useMemo(() => buildAncestorChain(run, runs), [run, runs]);

  useEffect(() => {
    apiFetch<FullRun>(`/tasks/${taskId}/runs/${run.id}`)
      .then(setFullRun)
      .catch(() => setFullRun(null));
  }, [run.id, taskId]);

  const effectiveRepoUrl = fullRun?.fork_url ?? fullRun?.repo_url ?? repoUrl;
  useEffect(() => {
    // For first runs (no parent), compare against base_sha (upstream HEAD at fork time)
    const isFirstRun = chain.length <= 1;
    if (compareBaseId === run.id && !isFirstRun) {
      setDiff(null);
      return;
    }
    const base = isFirstRun ? (fullRun?.base_sha ?? `${run.id}~1`) : compareBaseId;
    let cancelled = false;
    setDiffLoading(true);
    fetchGitHubDiff(base, run.id, effectiveRepoUrl).then((result) => {
      if (!cancelled) {
        setDiff(result);
        setDiffLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [compareBaseId, run.id, effectiveRepoUrl, chain.length, fullRun?.base_sha]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [chain]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const agentColor = getAgentColor(run.agent_id);
  const message = fullRun?.message;

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40 backdrop-blur-sm" style={{ zIndex: 9999 }} onClick={onClose}>
      <div className="bg-white border border-[var(--color-border)] rounded-xl shadow-xl max-w-5xl w-full mx-4 my-8 animate-fade-in max-h-[calc(100vh-4rem)] flex flex-col"
        onClick={(e) => e.stopPropagation()}>

        {/* Header with metadata bar */}
        <div className="px-6 pt-5 shrink-0">
          {/* Metadata row */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary)]">
              <span className="font-[family-name:var(--font-ibm-plex-mono)] font-semibold text-sm text-[var(--color-text)]">{run.score?.toFixed(3) ?? "\u2014"}</span>
            </div>
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-[var(--color-layer-2)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors shrink-0">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3l8 8M11 3l-8 8"/></svg>
            </button>
          </div>

          {/* Title */}
          <div className="text-xl font-bold text-[var(--color-text)]">{run.tldr}</div>

          {/* Agent + SHA + GitHub link */}
          <div className="flex items-center gap-2 mt-1.5 pb-4">
            <div className="w-4 h-4 rounded-full flex items-center justify-center text-white text-[7px] font-bold shrink-0"
              style={{ background: agentColor }}>
              {run.agent_id.split("-").map((w) => w[0]?.toUpperCase()).join("").slice(0, 2)}
            </div>
            <span className="text-sm text-[var(--color-text-secondary)]">{run.agent_id}</span>
            <span className="text-xs text-[var(--color-text-tertiary)]">&middot;</span>
            <span className="text-xs text-[var(--color-text-tertiary)]">{relativeTime(run.created_at)}</span>
            {effectiveRepoUrl && (
              <>
                <span className="text-xs text-[var(--color-text-tertiary)]">&middot;</span>
                <a
                  href={`${effectiveRepoUrl}/commit/${run.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] transition-colors"
                  onClick={(e) => e.stopPropagation()}
                  title="View on GitHub"
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
                  </svg>
                </a>
              </>
            )}
          </div>
        </div>

        <div className="h-px bg-[var(--color-border)] shrink-0" />

        {/* Scrollable content */}
        <div className="flex-1 min-h-0 overflow-y-auto">

          {/* Message */}
          {message && (
            <div className="px-6 py-4">
              <div className="text-base text-[var(--color-text)] leading-relaxed whitespace-pre-wrap">{message}</div>
            </div>
          )}

          {(<>
          <div className="h-px bg-[var(--color-border)]" />

          {/* Diff (lineage + GitHub diff combined) */}
          <div className="px-6 py-4">
            <div className="text-xs text-[var(--color-text-secondary)] mb-3">
              {chain.length <= 1 ? (
                <span className="text-[var(--color-text-tertiary)]">Showing commit diff</span>
              ) : compareBaseId !== run.id ? (
                <>
                  {"Comparing "}
                  {effectiveRepoUrl ? (
                    <a href={`${effectiveRepoUrl}/commit/${compareBaseId}`} target="_blank" rel="noopener noreferrer" className="font-[family-name:var(--font-ibm-plex-mono)] font-medium text-[var(--color-accent)] hover:underline transition-colors">{compareBaseId.slice(0, 10)}</a>
                  ) : (
                    <span className="font-[family-name:var(--font-ibm-plex-mono)] font-medium text-[var(--color-text)]">{compareBaseId.slice(0, 10)}</span>
                  )}
                  {" and "}
                  {effectiveRepoUrl ? (
                    <a href={`${effectiveRepoUrl}/commit/${run.id}`} target="_blank" rel="noopener noreferrer" className="font-[family-name:var(--font-ibm-plex-mono)] font-medium text-[var(--color-accent)] hover:underline transition-colors">{run.id.slice(0, 10)}</a>
                  ) : (
                    <span className="font-[family-name:var(--font-ibm-plex-mono)] font-medium text-[var(--color-text)]">{run.id.slice(0, 10)}</span>
                  )}
                </>
              ) : (
                <span className="text-[var(--color-text-tertiary)]">Select an ancestor to compare</span>
              )}
            </div>
            <div ref={scrollRef} className="overflow-x-auto pt-1 pb-4">
              <div className="flex items-center min-w-max px-1">
                {chain.map((ancestor, i) => {
                  const isSelected = ancestor.id === run.id;
                  const isBase = ancestor.id === compareBaseId;
                  const color = getAgentColor(ancestor.agent_id);

                  return (
                    <div key={ancestor.id} className="flex items-center">
                      {i > 0 && <div className="w-8 h-px bg-[var(--color-border)] mx-0.5" />}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!isSelected) setCompareBaseId(ancestor.id);
                        }}
                        disabled={isSelected}
                        className={`
                          relative flex flex-col items-center gap-1 px-3 py-2 rounded-lg transition-all group
                          ${isSelected
                            ? "bg-[var(--color-text)] cursor-default"
                            : isBase
                              ? "bg-blue-50 ring-2 ring-blue-400 hover:ring-blue-500 cursor-pointer"
                              : "bg-[var(--color-layer-2)] hover:bg-[var(--color-border)] cursor-pointer"
                          }
                        `}
                      >
                        <div className="flex items-center gap-1.5">
                          <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                          <span className={`text-xs font-semibold font-[family-name:var(--font-ibm-plex-mono)] tabular-nums ${isSelected ? "text-white" : "text-[var(--color-text)]"}`}>
                            {ancestor.score?.toFixed(2) ?? "\u2014"}
                          </span>
                        </div>
                        <span className={`text-[10px] leading-none whitespace-nowrap ${isSelected ? "text-gray-400" : "text-[var(--color-text-tertiary)]"}`}>
                          {ancestor.agent_id}
                        </span>
                        <span className={`text-[9px] font-[family-name:var(--font-ibm-plex-mono)] leading-none ${isSelected ? "text-gray-500" : "text-[var(--color-text-tertiary)]"}`}>
                          {ancestor.id.slice(0, 7)}
                        </span>
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* GitHub diff content */}
            {(chain.length <= 1 || compareBaseId !== run.id) && (
              <div className="mt-3 relative">
                {diff ? (
                  <div className={`transition-opacity duration-200 ${diffLoading ? "opacity-30 pointer-events-none" : ""}`}>
                    <DiffViewer diff={diff} />
                  </div>
                ) : !diffLoading ? (
                  <div className="flex items-center justify-center h-20 text-sm text-[var(--color-text-tertiary)]">
                    Could not load diff &mdash; commits may not exist on GitHub
                  </div>
                ) : null}
                {diffLoading && (
                  <div className={`flex items-center justify-center text-sm text-[var(--color-text-tertiary)] ${diff ? "absolute inset-0" : "h-20"}`}>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Fetching diff from GitHub...
                  </div>
                )}
              </div>
            )}
          </div>
          </>)}

        </div>
      </div>
    </div>
  );
}
