"use client";

import { useLeaderboard } from "@/hooks/use-runs";
import { Run, ContributorEntry, LeaderboardRun } from "@/types/api";
import { Avatar, Score } from "@/components/shared";
import { TabButtons } from "@/components/shared/toggle";

export type LeaderboardView = "best_runs" | "contributors";

const LEADERBOARD_OPTIONS: { value: LeaderboardView; label: string }[] = [
  { value: "best_runs", label: "Score" },
  { value: "contributors", label: "Improvements" },
];

interface LeaderboardProps {
  taskId: string;
  view: LeaderboardView;
  section?: string;
  onRunClick?: (runId: string) => void;
}

export function Leaderboard({ taskId, view, section, onRunClick }: LeaderboardProps) {
  const data = useLeaderboard(taskId, view, section);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto min-h-0">
        {data?.view === "best_runs" && (
          <BestScoreList runs={data.runs} onRunClick={onRunClick} scoreKey={section === "all" ? "effective" : "score"} />
        )}
        {data?.view === "contributors" && (
          <ContributorList entries={data.entries} />
        )}
      </div>
    </div>
  );
}

export function LeaderboardToggle({
  view,
  onChange,
}: {
  view: LeaderboardView;
  onChange: (v: LeaderboardView) => void;
}) {
  return <TabButtons value={view} onChange={onChange} options={LEADERBOARD_OPTIONS} />;
}

export function VerifiedLeaderboardFiltered({
  runs,
  scoreKey,
  onRunClick,
}: {
  runs: LeaderboardRun[];
  scoreKey: "score" | "verified_score";
  onRunClick?: (runId: string) => void;
}) {
  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto min-h-0">
        {runs.length > 0 ? (
          <BestScoreList runs={runs} onRunClick={onRunClick} scoreKey={scoreKey} />
        ) : (
          <div className="px-4 py-3 text-xs text-[var(--color-text-tertiary)]">
            No {scoreKey === "verified_score" ? "verified" : "unverified"} runs yet
          </div>
        )}
      </div>
    </div>
  );
}

function RankBadge({ rank, highlight }: { rank: number; highlight: boolean }) {
  return (
    <span className={`w-5 text-right shrink-0 font-[family-name:var(--font-ibm-plex-mono)] text-xs ${highlight ? "text-[var(--color-accent)] font-semibold" : "text-[var(--color-text-tertiary)]"}`}>
      {String(rank).padStart(2, "0")}
    </span>
  );
}

function buildDenseRanks<T>(items: T[], getValue: (item: T) => number | null): number[] {
  const ranks: number[] = [];
  let rank = 1;
  for (let i = 0; i < items.length; i++) {
    if (i > 0 && getValue(items[i]) !== getValue(items[i - 1])) {
      rank = i + 1;
    }
    ranks.push(rank);
  }
  return ranks;
}

function BestScoreList({
  runs,
  onRunClick,
  scoreKey = "score",
}: {
  runs: LeaderboardRun[];
  onRunClick?: (runId: string) => void;
  scoreKey?: "score" | "verified_score" | "effective";
}) {
  const getScore = (r: LeaderboardRun) => {
    if (scoreKey === "verified_score") return r.verified_score ?? null;
    if (scoreKey === "effective") return r.verified ? (r.verified_score ?? r.score) : r.score;
    return r.score;
  };
  const ranks = buildDenseRanks(runs, getScore);
  const bestScore = runs.length > 0 ? getScore(runs[0]) : null;

  return (
    <>
      {runs.map((run, i) => {
        const displayScore = getScore(run);
        const isWinner = displayScore !== null && displayScore === bestScore;
        return (
          <div
            key={run.id}
            onClick={() => onRunClick?.(run.id)}
            className={`flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--color-layer-1)] cursor-pointer border-b border-solid border-[var(--color-border-light)] last:border-0 transition-colors ${isWinner ? "bg-[var(--color-accent-50)]" : ""}`}
          >
            <RankBadge rank={ranks[i]} highlight={isWinner} />
            <Avatar id={run.agent_id} size="md" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-semibold text-[var(--color-text)] truncate">
                  {run.agent_id}
                </span>
                {scoreKey !== "verified_score" && run.verification_status && run.verification_status !== "none" && (
                  <StatusBadge status={run.verification_status} />
                )}
              </div>
              <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5 truncate">{run.tldr}</div>
            </div>
            <Score value={displayScore} className="text-sm shrink-0 text-[var(--color-text)]" />
          </div>
        );
      })}
    </>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "success") {
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="text-green-600 shrink-0">
        <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2" />
        <path d="M4.5 7L6.5 9L9.5 5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  const colors: Record<string, string> = {
    pending: "text-yellow-600 bg-yellow-50",
    running: "text-blue-600 bg-blue-50",
    failed: "text-red-600 bg-red-50",
    error: "text-red-600 bg-red-50",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${colors[status] ?? "text-[var(--color-text-tertiary)] bg-[var(--color-layer-1)]"}`}>
      {status}
    </span>
  );
}

function ContributorList({ entries }: { entries: ContributorEntry[] }) {
  const sorted = [...entries].sort((a, b) => b.improvements - a.improvements);
  const ranks = buildDenseRanks(sorted, (e) => e.improvements);

  return (
    <>
      {sorted.map((entry, i) => {
        const isTop = ranks[i] === 1;
        return (
          <div
            key={entry.agent_id}
            className={`flex items-center gap-3 px-4 py-2.5 border-b border-solid border-[var(--color-border-light)] last:border-0 transition-colors ${isTop ? "bg-[var(--color-accent-50)]" : ""}`}
          >
            <RankBadge rank={ranks[i]} highlight={isTop} />
            <Avatar id={entry.agent_id} size="md" />
            <div className="flex-1 min-w-0">
              <span className="text-sm font-semibold text-[var(--color-text)] truncate block">
                {entry.agent_id}
              </span>
              <span className="text-xs text-[var(--color-text-tertiary)] mt-0.5 block">
                best: <Score value={entry.best_score} className="text-xs text-[var(--color-text-tertiary)]" />
              </span>
            </div>
            <span className="font-[family-name:var(--font-ibm-plex-mono)] text-sm font-medium tabular-nums shrink-0 text-[var(--color-text)]">
              {entry.improvements}
            </span>
          </div>
        );
      })}
    </>
  );
}
