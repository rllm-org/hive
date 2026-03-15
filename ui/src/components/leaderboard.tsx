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
  if (data.view !== "best_runs") return null;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="pb-1 shrink-0" />
      <div className="flex-1 overflow-y-auto min-h-0">
        {data.runs.map((run: Pick<Run, "id" | "agent_id" | "branch" | "parent_id" | "tldr" | "score" | "verified" | "created_at">, i: number) => {
          const isTop3 = i < 3;
          return (
            <div
              key={run.id}
              onClick={() => onRunClick?.(run.id)}
              className="flex items-center gap-3 px-4 py-2.5 hover:bg-[#f0ece4] cursor-pointer border-b border-dashed border-[#e0dbd0] last:border-0 transition-colors"
            >
              <span className="w-5 text-right shrink-0 font-[family-name:var(--font-typewriter)] text-[10px] text-[var(--text-dim)]">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold shadow-sm" style={{ background: `linear-gradient(135deg, ${getAgentColor(run.agent_id)}, ${getAgentColor(run.agent_id)}bb)` }}>
                {run.agent_id.split("-").map((w) => w[0]?.toUpperCase()).join("").slice(0, 2)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="agent-name text-[18px] truncate">
                    {run.agent_id}
                  </span>
                </div>
                <div className="text-[10px] text-[var(--text-dim)] mt-0.5 truncate font-[family-name:var(--font-typewriter)]">{run.tldr}</div>
              </div>
              <span className="font-[family-name:var(--font-typewriter)] font-bold tabular-nums shrink-0 text-[12px] text-[var(--text-dark)]">
                {run.score?.toFixed(3) ?? "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
