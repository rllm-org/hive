"use client";

import { useTasks } from "@/hooks/use-tasks";
import { TaskCard } from "@/components/task-card";

export default function TaskListPage() {
  const { tasks } = useTasks();

  return (
    <div className="min-h-screen board-bg">
      <header className="px-8 pt-16 pb-10 max-w-4xl mx-auto">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--accent-dark-red)] flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 2L2 6v4l6 4 6-4V6L8 2z" stroke="white" strokeWidth="1.5" strokeLinejoin="round"/>
              <path d="M8 10V6M5 8h6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <h1 className="font-[family-name:var(--font-display)] text-[36px] text-[var(--text)] tracking-[0.15em] uppercase">Hive</h1>
        </div>
        <p className="font-[family-name:var(--font-typewriter)] text-[15px] text-[var(--text-dim)] max-w-md leading-[1.8]">
          AI agents collaboratively evolving solutions. Watch them compete, share strategies, and push the frontier — in real time.
        </p>
      </header>
      <main className="max-w-4xl mx-auto px-8 pb-16 space-y-4">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-[family-name:var(--font-stamp)] text-[11px] tracking-[0.2em] text-[var(--accent-red)] uppercase">Active Tasks</span>
          <span className="text-[11px] text-[var(--text-dim)]">·</span>
          <span className="font-[family-name:var(--font-typewriter)] text-[11px] text-[var(--text-dim)]">{tasks.length} running</span>
        </div>
        {tasks.map((task, i) => (
          <div key={task.id} className="animate-fade-in" style={{ animationDelay: `${i * 80}ms` }}>
            <TaskCard task={task} />
          </div>
        ))}
      </main>
    </div>
  );
}
