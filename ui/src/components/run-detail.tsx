"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";
import { timeAgo } from "@/lib/time";
import { DiffViewer } from "@/components/diff-viewer";
import { fetchGitHubDiff, getGitHubCompareUrl } from "@/lib/github-diff";
import { apiFetch, apiPatch, apiDelete } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getAuthHeader } from "@/lib/auth";
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
  onRunUpdated?: () => void;
  isOwner?: boolean;
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

export function RunDetail({ run, runs, taskId, repoUrl, onClose, onRunUpdated, isOwner }: RunDetailProps) {
  const [fullRun, setFullRun] = useState<FullRun | null>(null);
  const { isAdmin } = useAuth();
  const canManage = isAdmin || !!isOwner;
  const [menuOpen, setMenuOpen] = useState(false);
  const [showAdminDialog, setShowAdminDialog] = useState<"invalidate" | "delete" | null>(null);
  const [adminError, setAdminError] = useState("");
  const [isValid, setIsValid] = useState(run.valid !== false);
  const [adminLoading, setAdminLoading] = useState(false);
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

  // Wait for fullRun to load before fetching diffs so we have the correct repo URL
  useEffect(() => {
    if (!fullRun) {
      setDiffLoading(true);
      return;
    }
    if (compareBaseId === run.id && chain.length > 1) {
      setDiff(null);
      setDiffLoading(false);
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
  }, [fullRun, compareBaseId, run.id, effectiveRepoUrl, chain.length, seedSha]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [chain]);

  const agentColor = getAgentColor(run.agent_id);
  const message = fullRun?.message;

  const handleToggleValid = async () => {
    setAdminLoading(true);
    setAdminError("");
    try {
      await apiPatch(`/tasks/${taskId}/runs/${run.id}`, { valid: !isValid }, getAuthHeader());
      setIsValid(!isValid);
      setShowAdminDialog(null);
      onRunUpdated?.();
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : "Failed");
    } finally {
      setAdminLoading(false);
    }
  };

  const handleDeleteRun = async () => {
    setAdminLoading(true);
    setAdminError("");
    try {
      await apiDelete(`/tasks/${taskId}/runs/${run.id}`, getAuthHeader());
      setShowAdminDialog(null);
      onClose();
      onRunUpdated?.();
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : "Failed");
    } finally {
      setAdminLoading(false);
    }
  };

  return (
    <>
    {!showAdminDialog && (
    <Modal onClose={onClose}>
      {/* Header with metadata bar */}
      <div className="px-6 pt-5 shrink-0">
        {/* Metadata row */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3 text-xs text-[var(--color-text-secondary)]">
            <Score value={run.score} className="text-sm font-semibold text-[var(--color-text)]" />
            {!isValid && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide bg-red-500/10 text-red-500 border border-red-500/20">
                Invalid
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {canManage && (
              <div className="relative">
                <button
                  onClick={() => setMenuOpen(!menuOpen)}
                  className="w-7 h-7 flex items-center justify-center rounded-md text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                    <circle cx="7" cy="3" r="1.2" />
                    <circle cx="7" cy="7" r="1.2" />
                    <circle cx="7" cy="11" r="1.2" />
                  </svg>
                </button>
                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                    <div className="absolute right-0 top-8 z-20 bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 min-w-[160px]">
                      <button
                        onClick={() => { setMenuOpen(false); setShowAdminDialog("invalidate"); }}
                        className={`w-full text-left px-3 py-2 text-xs font-medium transition-colors ${isValid ? "text-red-500 hover:bg-red-500/10" : "text-emerald-600 hover:bg-emerald-500/10"}`}
                      >
                        {isValid ? "Invalidate run" : "Re-validate run"}
                      </button>
                      <button
                        onClick={() => { setMenuOpen(false); setShowAdminDialog("delete"); }}
                        className="w-full text-left px-3 py-2 text-xs font-medium text-red-500 hover:bg-red-500/10 transition-colors"
                      >
                        Delete run
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
            <ModalCloseButton onClick={onClose} />
          </div>
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
                          ? "bg-[var(--color-layer-3)] cursor-default"
                          : isBase
                            ? "bg-[var(--color-accent-50)] ring-2 ring-[var(--color-accent)] hover:ring-[var(--color-accent-hover)] cursor-pointer"
                            : "bg-[var(--color-layer-2)] hover:bg-[var(--color-border)] cursor-pointer"
                        }
                      `}
                    >
                      {isSeed ? (
                        <>
                          <span className={`text-xs font-semibold ${isBase ? "text-[var(--color-accent)]" : "text-[var(--color-text)]"}`}>
                            Base
                          </span>
                          <span className={`text-[9px] font-[family-name:var(--font-ibm-plex-mono)] leading-none ${isBase ? "text-[var(--color-accent)]/60" : "text-[var(--color-text-tertiary)]"}`}>
                            {ancestor.id.slice(0, 7)}
                          </span>
                        </>
                      ) : (
                        <>
                          <div className="flex items-center gap-1.5">
                            <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                            <Score value={ancestor.score} decimals={2} className={`text-xs font-semibold ${isSelected ? "text-[var(--color-text)]" : "text-[var(--color-text)]"}`} />
                          </div>
                          <span className={`text-[10px] leading-none whitespace-nowrap ${isSelected ? "text-[var(--color-text-secondary)]" : "text-[var(--color-text-tertiary)]"}`}>
                            {ancestor.agent_id}
                          </span>
                          <span className={`text-[9px] font-[family-name:var(--font-ibm-plex-mono)] leading-none ${isSelected ? "text-[var(--color-text-tertiary)]" : "text-[var(--color-text-tertiary)]"}`}>
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
                <div className="flex items-center justify-center h-20 text-sm text-[var(--color-text-tertiary)]">
                  {diffRateLimited
                    ? "GitHub API rate limit exceeded — try again later"
                    : !run.parent_id && compareBaseId === run.id
                    ? "First run — no parent to compare"
                    : "Could not load diff — commits may not be available on GitHub"}
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
    )}

    {/* Admin confirm popup */}
    {showAdminDialog && (
      <div className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30" onClick={() => { setShowAdminDialog(null); setAdminError(""); }}>
        <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[380px] animate-fade-in" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
            <h2 className="text-base font-semibold text-[var(--color-text)]">
              {showAdminDialog === "delete" ? "Delete Run" : isValid ? "Invalidate Run" : "Re-validate Run"}
            </h2>
            <button
              onClick={() => { setShowAdminDialog(null); setAdminError(""); }}
              className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M3 3l8 8M11 3l-8 8" />
              </svg>
            </button>
          </div>
          <div className="px-6 py-5 space-y-4">
            <p className={`text-sm ${showAdminDialog === "delete" ? "text-red-500" : "text-[var(--color-text-secondary)]"}`}>
              {showAdminDialog === "delete"
                ? "This will permanently delete this run and its associated posts and comments. This cannot be undone."
                : isValid
                  ? "This run will be excluded from the leaderboard but will remain visible in the evolution tree."
                  : "This run will be restored to the leaderboard."}
            </p>
            {adminError && <p className="text-xs text-red-500">{adminError}</p>}
            <div className="flex items-center gap-2">
              <button
                onClick={showAdminDialog === "delete" ? handleDeleteRun : handleToggleValid}
                disabled={adminLoading}
                className={`px-4 py-2 text-sm font-medium text-white disabled:opacity-50 transition-colors ${
                  showAdminDialog === "delete" || isValid
                    ? "bg-red-500 hover:bg-red-600"
                    : "bg-emerald-600 hover:bg-emerald-700"
                }`}
              >
                {adminLoading ? "..." : showAdminDialog === "delete" ? "Delete run" : isValid ? "Invalidate" : "Re-validate"}
              </button>
              <button
                onClick={() => { setShowAdminDialog(null); setAdminError(""); }}
                className="px-4 py-2 text-sm text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    )}
    </>
  );
}
