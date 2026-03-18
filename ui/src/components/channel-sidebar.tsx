"use client";

import Link from "next/link";
import { Task } from "@/types/api";

interface ChannelSidebarProps {
  tasks: Task[];
  activeTaskId?: string;
  onTaskClick?: (taskId: string) => void;
  postCounts?: Record<string, number>;
}

export function ChannelSidebar({ tasks, activeTaskId, onTaskClick, postCounts }: ChannelSidebarProps) {
  return (
    <>
      {/* Mobile: horizontal scrollable pills */}
      <div className="md:hidden w-full overflow-x-auto -mx-2 px-2 pb-2">
        <div className="flex gap-2 w-max">
          {tasks.map((task) => {
            const isActive = activeTaskId === task.id;
            const count = postCounts?.[task.id] ?? task.stats?.total_posts ?? 0;
            const cls = `flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              isActive
                ? "bg-[var(--color-accent)] text-white"
                : "bg-[var(--color-layer-2)] text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-3)]"
            }`;

            if (onTaskClick) {
              return (
                <button key={task.id} onClick={() => onTaskClick(task.id)} className={cls}>
                  {task.name || task.id}
                  {count > 0 && (
                    <span className={`tabular-nums ${isActive ? "text-white/70" : "text-[var(--color-text-tertiary)]"}`}>
                      {count}
                    </span>
                  )}
                </button>
              );
            }

            return (
              <Link key={task.id} href={`/h/${task.id}`} className={cls}>
                {task.name || task.id}
                {count > 0 && (
                  <span className="text-[var(--color-text-tertiary)]">{count}</span>
                )}
              </Link>
            );
          })}
        </div>
      </div>

      {/* Desktop: vertical sidebar */}
      <aside className="hidden md:block w-60 shrink-0 overflow-y-auto border-r border-[var(--color-border)] pr-3">
        <div className="space-y-0.5">
          {tasks.map((task) => {
            const isActive = activeTaskId === task.id;
            const count = postCounts?.[task.id] ?? task.stats?.total_posts ?? 0;
            const cls = `flex items-center justify-between gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
              isActive
                ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)]"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)] hover:text-[var(--color-text)]"
            }`;

            const content = (
              <>
                <span className={`truncate ${isActive ? "" : "text-[var(--color-text)]"}`}>
                  {task.name || task.id}
                </span>
                {count > 0 && (
                  <span className="shrink-0 tabular-nums text-xs text-[var(--color-text-tertiary)]">
                    {count}
                  </span>
                )}
              </>
            );

            if (onTaskClick) {
              return (
                <button
                  key={task.id}
                  onClick={() => onTaskClick(task.id)}
                  className={`${cls} w-full text-left`}
                >
                  {content}
                </button>
              );
            }

            return (
              <Link
                key={task.id}
                href={`/h/${task.id}`}
                className={cls}
              >
                {content}
              </Link>
            );
          })}
        </div>
      </aside>
    </>
  );
}
