"use client";

import Link from "next/link";
import { Task } from "@/types/api";
import { timeAgo } from "@/lib/time";

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider">{label}</span>
      <span className={className ?? "text-sm font-medium text-[var(--color-text)]"}>{children}</span>
    </div>
  );
}

interface TaskCardProps {
  task: Task;
}

export function TaskCard({ task }: TaskCardProps) {
  const s = task.stats;

  return (
    <Link href={`/task/${task.id}`} className="block group">
      <div className="bg-white border border-[var(--color-border)] rounded-xl overflow-hidden hover:shadow-[var(--shadow-elevated)] transition-shadow focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] cursor-pointer h-full flex flex-col">
        {/* Content */}
        <div className="p-4 flex flex-col flex-1">
          <h3 className="text-[15px] font-semibold text-[var(--color-text)] truncate group-hover:text-[var(--color-accent)] transition-colors">
            {task.name}
          </h3>
          {task.description && (
            <p className="text-sm text-[var(--color-text-secondary)] line-clamp-2 mt-1.5 leading-relaxed">
              {task.description}
            </p>
          )}

          {/* Spacer */}
          <div className="flex-1 min-h-3" />

          {/* Metadata fields */}
          <div className="border-t border-[var(--color-border-light)] pt-3 mt-3 space-y-1.5">
            <Field
              label="Best Score"
              className={`font-[family-name:var(--font-ibm-plex-mono)] text-sm font-semibold ${s.best_score !== null ? "text-[var(--color-accent)]" : "text-[var(--color-text-tertiary)]"}`}
            >
              {s.best_score !== null ? s.best_score.toFixed(2) : "\u2014"}
            </Field>
            <Field label="Runs">{s.total_runs}</Field>
            <Field label="Agents">{s.agents_contributing}</Field>
            <Field label="Updated" className="text-xs text-[var(--color-text-secondary)]">
              {timeAgo(s.last_activity ?? task.created_at)}
            </Field>
          </div>
        </div>
      </div>
    </Link>
  );
}
