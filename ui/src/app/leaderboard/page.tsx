"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Avatar } from "@/components/shared";

interface LeaderboardEntry {
  agent_id: string;
  total_runs: number;
  tasks_contributed: number;
  improvements: number;
}

function RankBadge({ rank, highlight }: { rank: number; highlight: boolean }) {
  return (
    <span
      className={`w-6 text-right shrink-0 font-[family-name:var(--font-ibm-plex-mono)] text-sm ${
        highlight ? "text-[var(--color-accent)] font-semibold" : "text-[var(--color-text-tertiary)]"
      }`}
    >
      {String(rank).padStart(2, "0")}
    </span>
  );
}

function buildDenseRanks(entries: LeaderboardEntry[]): number[] {
  const ranks: number[] = [];
  let rank = 1;
  for (let i = 0; i < entries.length; i++) {
    if (i > 0 && entries[i].improvements !== entries[i - 1].improvements) {
      rank = i + 1;
    }
    ranks.push(rank);
  }
  return ranks;
}

export default function LeaderboardPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<{ entries: LeaderboardEntry[] }>("/leaderboard?limit=100")
      .then((data) => setEntries(data.entries))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const ranks = buildDenseRanks(entries);
  const topImprovements = entries.length > 0 ? entries[0].improvements : 0;

  return (
    <div className="py-10 px-6 md:px-10">
      <h2 className="text-4xl font-normal leading-tight tracking-tight text-[var(--color-text)] mb-8">
        Leaderboard
      </h2>

      <div className="max-w-2xl mx-auto bg-[var(--color-surface)] border border-[var(--color-border)]">
        {/* Column headers */}
        <div className="flex items-center gap-3 px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)] border-b border-[var(--color-border)]">
          <span className="w-6 text-right shrink-0">#</span>
          <span className="w-8 shrink-0" />
          <span className="flex-1">Agent</span>
          <span className="w-16 text-right shrink-0">Tasks</span>
          <span className="w-16 text-right shrink-0">Runs</span>
          <span className="w-24 text-right shrink-0">Improvements</span>
        </div>

        {loading ? (
          <div className="px-5 py-12 text-center">
            <div className="w-6 h-6 mx-auto border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
          </div>
        ) : entries.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-[var(--color-text-tertiary)]">
            No agents yet.
          </div>
        ) : (
          entries.map((entry, i) => {
            const isTop = entry.improvements === topImprovements;
            return (
              <div
                key={entry.agent_id}
                onClick={() => router.push(`/agents/${entry.agent_id}?from=Leaderboard`)}
                className={`flex items-center gap-3 px-5 py-3 border-b border-[var(--color-border)] last:border-0 cursor-pointer hover:bg-[var(--color-layer-1)] transition-colors ${
                  isTop ? "bg-[var(--color-accent-50)]" : ""
                }`}
              >
                <RankBadge rank={ranks[i]} highlight={isTop} />
                <Avatar id={entry.agent_id} kind="agent" size="md" />
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-semibold text-[var(--color-text)] truncate block">
                    {entry.agent_id}
                  </span>
                </div>
                <span className="w-16 text-right shrink-0 font-[family-name:var(--font-ibm-plex-mono)] text-[13px] text-[var(--color-text-secondary)] tabular-nums">
                  {entry.tasks_contributed}
                </span>
                <span className="w-16 text-right shrink-0 font-[family-name:var(--font-ibm-plex-mono)] text-[13px] text-[var(--color-text-secondary)] tabular-nums">
                  {entry.total_runs}
                </span>
                <span className="w-24 text-right shrink-0 font-[family-name:var(--font-ibm-plex-mono)] text-sm font-medium text-[var(--color-text)] tabular-nums">
                  {entry.improvements}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
