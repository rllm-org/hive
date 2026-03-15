"use client";

import Link from "next/link";
import { Task } from "@/types/api";

interface TaskCardProps {
  task: Task;
}

export function TaskCard({ task }: TaskCardProps) {
  const progress = task.stats.best_score !== null ? task.stats.best_score * 100 : 0;

  return (
    <Link href={`/task/${task.id}`}>
      <div className="group bg-[var(--bg-card)] border border-[#d8d0c0] border-l-[3px] border-l-[var(--accent-red)] rounded p-6 hover:shadow-xl hover:shadow-black/20 hover:-translate-y-0.5 transition-all duration-300 cursor-pointer relative overflow-hidden"
        style={{ boxShadow: "2px 3px 12px rgba(0,0,0,0.25)" }}>
        {/* Progress bar */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-[#e0d8c0]">
          <div
            className="h-full bg-[var(--accent-red)] rounded-r-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="flex items-start justify-between mt-1">
          <div className="flex-1">
            <h2 className="font-[family-name:var(--font-display)] text-[22px] text-[var(--text-dark)] tracking-[0.1em] uppercase group-hover:text-[var(--accent-dark-red)] transition-colors">{task.name}</h2>
            <p className="font-[family-name:var(--font-typewriter)] text-[13px] text-[var(--text-dim)] leading-[1.8] line-clamp-2 mt-1">{task.description}</p>
          </div>
          <div className="ml-4 text-right shrink-0">
            <div className="font-[family-name:var(--font-typewriter)] text-2xl font-bold text-[var(--text-dark)] tracking-tight">
              {task.stats.best_score?.toFixed(2) ?? "—"}
            </div>
            <div className="font-[family-name:var(--font-stamp)] text-[8px] text-[var(--accent-dark-red)] tracking-[0.15em] uppercase mt-0.5">best score</div>
          </div>
        </div>
        <div className="flex items-center gap-4 mt-4 font-[family-name:var(--font-typewriter)] text-[12px] text-[var(--text-dim)]">
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-red)] animate-pulse-slow" />
            <span className="font-bold text-[var(--text-dark)]">{task.stats.total_runs}</span> runs
          </span>
          <span>
            <span className="font-bold text-[var(--text-dark)]">{task.stats.agents_contributing}</span> agents
          </span>
          <span>
            <span className="font-bold text-[var(--text-dark)]">{task.stats.improvements}</span> improvements
          </span>
        </div>
      </div>
    </Link>
  );
}
