"use client";

import Link from "next/link";
import { Task } from "@/types/api";

interface ChannelSidebarProps {
  tasks: Task[];
  activeTaskId?: string;
}

export function ChannelSidebar({ tasks, activeTaskId }: ChannelSidebarProps) {
  return (
    <aside className="w-60 shrink-0 overflow-y-auto border-r border-[var(--color-border)] pr-3">
      <h3 className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-tertiary)] mb-2 px-2">
        Channels
      </h3>
      <div className="space-y-0.5">
        {tasks.map((task) => (
          <Link
            key={task.id}
            href={`/h/${task.id}`}
            className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
              activeTaskId === task.id
                ? "bg-[var(--color-accent)]/10 text-[var(--color-accent)]"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)] hover:text-[var(--color-text)]"
            }`}
          >
            <span className="truncate">
              <span className="font-semibold text-[var(--color-accent)]">#</span>
              <span className="underline decoration-[var(--color-border)] underline-offset-2 hover:decoration-[var(--color-text-secondary)]">
                {task.name || task.id}
              </span>
            </span>
            <span className="text-[10px] tabular-nums text-[var(--color-text-tertiary)] shrink-0">
              {task.stats.agents_contributing}
            </span>
          </Link>
        ))}
      </div>
    </aside>
  );
}
