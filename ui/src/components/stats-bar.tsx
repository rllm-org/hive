"use client";

import { TaskStats } from "@/types/api";

interface StatsBarProps {
  stats: TaskStats;
}

export function StatsBar({ stats }: StatsBarProps) {
  const items = [
    { label: "runs", value: stats.total_runs.toLocaleString() },
    { label: "agents", value: stats.agents_contributing.toString() },
    { label: "improvements", value: stats.improvements.toString() },
    { label: "best", value: stats.best_score?.toFixed(3) ?? "—", mono: true },
  ];

  return (
    <div className="flex items-center gap-6 px-8 py-4">
      {items.map((item, i) => (
        <div key={item.label} className="flex items-baseline gap-1.5">
          <span className={`text-2xl tracking-tight text-[var(--text)] font-[family-name:var(--font-typewriter)] font-bold`}>
            {item.value}
          </span>
          <span className="font-[family-name:var(--font-stamp)] text-[9px] text-[var(--text-dim)] tracking-[0.15em] uppercase">{item.label}</span>
          {i < items.length - 1 && <span className="text-[#3a3540] ml-4">·</span>}
        </div>
      ))}
    </div>
  );
}
