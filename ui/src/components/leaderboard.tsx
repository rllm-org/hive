"use client";

import { useLeaderboard } from "@/hooks/use-runs";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";

interface LeaderboardProps {
  taskId: string;
  onRunClick?: (runId: string) => void;
}

export function Leaderboard({ taskId, onRunClick }: LeaderboardProps) {
  const data = useLeaderboard(taskId, "best_runs");
  if (!data || data.view !== "best_runs") return null;

  // Build dense ranks: tied scores share the same rank
  const ranks: number[] = [];
  let rank = 1;
  for (let i = 0; i < data.runs.length; i++) {
    if (i > 0 && data.runs[i].score !== data.runs[i - 1].score) {
      rank = i + 1;
    }
    ranks.push(rank);
  }
  const bestScore = data.runs.length > 0 ? data.runs[0].score : null;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="pb-1 shrink-0" />
      <div className="flex-1 overflow-y-auto min-h-0">
        {data.runs.map((run: Pick<Run, "id" | "agent_id" | "branch" | "parent_id" | "tldr" | "score" | "verified" | "created_at" | "fork_url">, i: number) => {
          const isWinner = run.score !== null && run.score === bestScore;
          return (
            <div
              key={run.id}
              onClick={() => onRunClick?.(run.id)}
              className={`flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--color-layer-1)] cursor-pointer border-b border-solid border-[var(--color-border-light)] last:border-0 transition-colors ${isWinner ? "bg-blue-50/50" : ""}`}
            >
              <span className={`w-5 text-right shrink-0 font-[family-name:var(--font-ibm-plex-mono)] text-xs ${isWinner ? "text-[#3f72af] font-semibold" : "text-[var(--color-text-tertiary)]"}`}>
                {String(ranks[i]).padStart(2, "0")}
              </span>
              <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold shadow-sm" style={{ background: `linear-gradient(135deg, ${getAgentColor(run.agent_id)}, ${getAgentColor(run.agent_id)}bb)` }}>
                {run.agent_id.split("-").map((w) => w[0]?.toUpperCase()).join("").slice(0, 2)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-semibold text-[var(--color-text)] truncate">
                    {run.agent_id}
                  </span>
                </div>
                <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5 truncate">{run.tldr}</div>
              </div>
              <span className="font-[family-name:var(--font-ibm-plex-mono)] text-sm font-medium tabular-nums shrink-0 text-[var(--color-text)]">
                {run.score?.toFixed(3) ?? "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
