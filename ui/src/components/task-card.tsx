"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Task, Run, taskPath as tp } from "@/types/api";
import { timeAgo } from "@/lib/time";
import { useGraph } from "@/hooks/use-graph";
import { buildRunMap, resolveRun } from "@/lib/run-utils";
import { LuGithub } from "react-icons/lu";

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider">{label}</span>
      <span className={className ?? "text-sm font-medium text-[var(--color-text)]"}>{children}</span>
    </div>
  );
}

function Sparkline({ taskPath }: { taskPath: string }) {
  const { runs } = useGraph(taskPath);

  const { allPath, lineagePath } = useMemo(() => {
    const scored = runs
      .filter((r) => r.score !== null && r.valid !== false)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    if (scored.length < 2) return { allPath: null, lineagePath: null };

    const scores = scored.map((r) => r.score!);
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    const range = max - min || 1;
    const w = 200;
    const h = 40;
    const pad = 2;

    const toY = (score: number) => pad + (1 - (score - min) / range) * (h - pad * 2);
    const toX = (i: number) => (i / (scored.length - 1)) * w;

    // All runs path
    const allPath = scored
      .map((r, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(r.score!)}`)
      .join(" ");

    // Best lineage path
    const runMap = buildRunMap(scored);
    const bestScore = Math.max(...scores);
    const winner = scored.find((r) => r.score === bestScore);
    let lineagePath: string | null = null;

    if (winner) {
      const lineageIds = new Set<string>();
      let cur: Run | undefined = winner;
      while (cur) {
        lineageIds.add(cur.id);
        cur = cur.parent_id ? resolveRun(cur.parent_id, runMap) : undefined;
      }

      const idxMap = new Map<string, number>();
      scored.forEach((r, i) => idxMap.set(r.id, i));

      const pts = scored
        .filter((r) => lineageIds.has(r.id))
        .sort((a, b) => (idxMap.get(a.id) ?? 0) - (idxMap.get(b.id) ?? 0));

      if (pts.length >= 2) {
        lineagePath = pts
          .map((r, i) => `${i === 0 ? "M" : "L"} ${toX(idxMap.get(r.id)!)} ${toY(r.score!)}`)
          .join(" ");
      }
    }

    return { allPath, lineagePath };
  }, [runs]);

  if (!allPath) return null;

  return (
    <svg viewBox="0 0 200 40" className="w-full h-10" preserveAspectRatio="none">
      <path d={allPath} fill="none" stroke="var(--color-text-tertiary)" strokeWidth={1} opacity={0.5} strokeLinecap="round" strokeLinejoin="round" />
      {lineagePath && (
        <path d={lineagePath} fill="none" stroke="var(--color-accent)" strokeWidth={1.5} opacity={0.7} strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

interface TaskCardProps {
  task: Task;
  linkPrefix?: string;
  ownerName?: string;
  ownerAvatar?: string | null;
}

export function TaskCard({ task, linkPrefix = "/task", ownerName, ownerAvatar }: TaskCardProps) {
  const s = task.stats;

  return (
    <Link href={`${linkPrefix}/${tp(task)}`} className="block group">
      <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-none overflow-hidden hover:shadow-[var(--shadow-elevated)] transition-shadow focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] cursor-pointer h-full flex flex-col">
        {/* Sparkline */}
        <div className="px-4 pt-3">
          <Sparkline taskPath={tp(task)} />
        </div>
        {/* Content */}
        <div className="p-4 flex flex-col flex-1">
          <div className="flex items-center gap-1 mb-1 -ml-0.5">
            {ownerName ? (
              <>
                {ownerAvatar ? (
                  <img src={ownerAvatar} alt={ownerName} className="w-4 h-4 rounded-full" />
                ) : (
                  <LuGithub size={12} className="text-[var(--color-text-tertiary)]" />
                )}
                <span className="text-[11px] font-medium text-[var(--color-text-tertiary)] tracking-tight">{ownerName}</span>
              </>
            ) : (
              <>
                <img src="/hive-logo.svg" alt="Hive" className="w-4 h-4" />
                <span className="text-[11px] font-medium text-[var(--color-text-tertiary)] tracking-tight">Hive Team</span>
              </>
            )}
          </div>
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
              {s.best_score !== null ? s.best_score.toFixed(3) : "\u2014"}
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
