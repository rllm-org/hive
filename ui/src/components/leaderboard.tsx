"use client";

import { useLeaderboard } from "@/hooks/use-runs";
import { Run, ContributorEntry } from "@/types/api";
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
  onRunClick?: (runId: string) => void;
}

export function Leaderboard({ taskId, view, onRunClick }: LeaderboardProps) {
  const data = useLeaderboard(taskId, view);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto min-h-0">
        {data?.view === "best_runs" && (
          <BestScoreList runs={data.runs} onRunClick={onRunClick} />
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

function effectiveRunScore(r: { score: number | null; verified_score?: number | null }): number | null {
  if (r.verified_score != null) return r.verified_score;
  return r.score;
}

function BestScoreList({
  runs,
  onRunClick,
}: {
  runs: Pick<Run, "id" | "agent_id" | "branch" | "parent_id" | "tldr" | "score" | "verified_score" | "verified" | "created_at" | "fork_url">[];
  onRunClick?: (runId: string) => void;
}) {
  const ranks = buildDenseRanks(runs, (r) => effectiveRunScore(r));
  const bestScore = runs.length > 0 ? effectiveRunScore(runs[0]) : null;

  return (
    <>
      {runs.map((run, i) => {
        const eff = effectiveRunScore(run);
        const isWinner = eff !== null && eff === bestScore;
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
              </div>
              <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5 truncate">{run.tldr}</div>
            </div>
            <Score value={eff} className="text-sm shrink-0 text-[var(--color-text)]" />
          </div>
        );
      })}
    </>
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
