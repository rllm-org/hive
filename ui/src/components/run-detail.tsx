"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";
import { timeAgo } from "@/lib/time";
import { DiffViewer } from "@/components/diff-viewer";
import { fetchGitHubDiff, getGitHubCompareUrl } from "@/lib/github-diff";
import { apiFetch } from "@/lib/api";
import { resolveRun, resolveId, buildRunMap } from "@/lib/run-utils";
import { Modal, ModalCloseButton } from "@/components/shared/modal";
import { GitHubIcon } from "@/components/shared/github-icon";
import { Score } from "@/components/shared/score";

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
  const [compareBaseId, setCompareBaseId] = useState<string>(() => {
    return run.parent_id
      ? (resolveId(run.parent_id, runs.map((r) => r.id)) ?? run.id)
      : run.id;
  });
  const [hasAutoSelectedSeed, setHasAutoSelectedSeed] = useState(false);
  const [diff, setDiff] = useState<string | null>(null);
  const [diffRateLimited, setDiffRateLimited] = useState(false);
  const [diffLoading, setDiffLoading] = useState(false);

  const rawChain = useMemo(() => buildAncestorChain(run, runs), [run, runs]);

  useEffect(() => {
    apiFetch<FullRun>(`/tasks/${taskId}/runs/${run.id}`)
      .then(setFullRun)
      .catch(() => setFullRun(null));
  }, [run.id, taskId]);

  const effectiveRepoUrl = fullRun?.fork_url ?? fullRun?.repo_url ?? repoUrl;

  // Build the seed SHA — the commit before the first run in the chain
  const seedSha = fullRun?.base_sha ?? (rawChain.length > 0 ? `${rawChain[0].id}~1` : null);

  // Prepend a synthetic "seed" node to the chain
  const chain = useMemo(() => {
    if (!seedSha || rawChain.length === 0) return rawChain;
    const seed: Run = {
      id: seedSha,
      task_id: taskId,
      agent_id: "seed",
      branch: "",
      parent_id: null,
      tldr: "seed",
      message: "",
      score: null,
      verified: false,
      created_at: rawChain[0].created_at,
    };
    return [seed, ...rawChain];
  }, [rawChain, seedSha, taskId]);

  // Auto-select seed as diff base when run has no parent
  useEffect(() => {
    if (!hasAutoSelectedSeed && !run.parent_id && seedSha && compareBaseId === run.id) {
      setCompareBaseId(seedSha);
      setHasAutoSelectedSeed(true);
    }
  }, [hasAutoSelectedSeed, run.parent_id, seedSha, compareBaseId, run.id]);

  useEffect(() => {
    if (compareBaseId === run.id && chain.length > 1) {
      setDiff(null);
      return;
    }
    const base = compareBaseId === run.id ? (seedSha ?? `${run.id}~1`) : compareBaseId;
    let cancelled = false;
    setDiffLoading(true);
    setDiffRateLimited(false);
    fetchGitHubDiff(base, run.id, effectiveRepoUrl).then((result) => {
      if (!cancelled) {
        if (result.status === "ok") {
          setDiff(result.diff);
        } else {
          setDiff(null);
          if (result.status === "rate_limited") setDiffRateLimited(true);
        }
        setDiffLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [compareBaseId, run.id, effectiveRepoUrl, chain.length, seedSha]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [chain]);

  const agentColor = getAgentColor(run.agent_id);
  const message = fullRun?.message;

  return (
    <Modal onClose={onClose}>
      {/* Header with metadata bar */}
      <div className="px-6 pt-5 shrink-0">
        {/* Metadata row */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary)]">
            <Score value={run.score} className="text-sm font-semibold text-[var(--color-text)]" />
          </div>
          <ModalCloseButton onClick={onClose} />
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
          <span className="text-xs text-[var(--color-text-tertiary)]">{timeAgo(run.created_at)}</span>
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
                <GitHubIcon className="w-3.5 h-3.5" />
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
                {effectiveRepoUrl && (
                  <a
                    href={getGitHubCompareUrl(effectiveRepoUrl, compareBaseId, run.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex align-text-bottom ml-1.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] transition-colors"
                    title="View on GitHub"
                  ><GitHubIcon className="w-3.5 h-3.5" />
                  </a>
                )}
              </>
            ) : (
              <span className="text-[var(--color-text-tertiary)]">Select an ancestor to compare</span>
            )}
          </div>
          <div ref={scrollRef} className="overflow-x-auto pt-1 pb-4">
            <div className="flex items-center min-w-max px-1">
              {chain.map((ancestor, i) => {
                const isSeed = ancestor.agent_id === "seed";
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
                      {isSeed ? (
                        <>
                          <span className={`text-xs font-semibold ${isBase ? "text-blue-600" : "text-[var(--color-text)]"}`}>
                            Base
                          </span>
                          <span className={`text-[9px] font-[family-name:var(--font-ibm-plex-mono)] leading-none ${isBase ? "text-blue-400" : "text-[var(--color-text-tertiary)]"}`}>
                            {ancestor.id.slice(0, 7)}
                          </span>
                        </>
                      ) : (
                        <>
                          <div className="flex items-center gap-1.5">
                            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                            <Score value={ancestor.score} decimals={2} className={`text-xs font-semibold ${isSelected ? "text-white" : "text-[var(--color-text)]"}`} />
                          </div>
                          <span className={`text-[10px] leading-none whitespace-nowrap ${isSelected ? "text-gray-400" : "text-[var(--color-text-tertiary)]"}`}>
                            {ancestor.agent_id}
                          </span>
                          <span className={`text-[9px] font-[family-name:var(--font-ibm-plex-mono)] leading-none ${isSelected ? "text-gray-500" : "text-[var(--color-text-tertiary)]"}`}>
                            {ancestor.id.slice(0, 7)}
                          </span>
                        </>
                      )}
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
                <div className="flex flex-col items-center justify-center h-20 gap-1 text-sm text-[var(--color-text-tertiary)]">
                  <span>{diffRateLimited
                    ? "GitHub API rate limit exceeded"
                    : <>Could not load diff &mdash; commits may not exist on GitHub</>}</span>
                  {effectiveRepoUrl && (
                    <a
                      href={getGitHubCompareUrl(effectiveRepoUrl, compareBaseId === run.id ? (seedSha ?? `${run.id}~1`) : compareBaseId, run.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[var(--color-accent)] hover:underline"
                    >View on GitHub</a>
                  )}
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
    </Modal>
  );
}
