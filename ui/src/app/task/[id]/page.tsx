"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useContext } from "@/hooks/use-context";
import { useRuns } from "@/hooks/use-runs";
import { useFeed } from "@/hooks/use-feed";
import { ChartToggle } from "@/components/chart-toggle";
import { Leaderboard } from "@/components/leaderboard";
import { Feed } from "@/components/feed";
import { RunDetail } from "@/components/run-detail";
import { Run } from "@/types/api";

export default function TaskDetailPage() {
  const params = useParams();
  const taskId = params.id as string;
  const { data: context, loading, error } = useContext(taskId);
  const runs = useRuns(taskId);
  const { items } = useFeed(taskId);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--color-bg)]">
        <div className="text-sm text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    );
  }

  if (error || !context) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--color-bg)]">
        <div className="text-sm text-[var(--color-text-secondary)]">{error ?? "Task not found"}</div>
      </div>
    );
  }

  const handleRunClick = (run: Run) => setSelectedRun(run);
  const handleRunIdClick = (runId: string) => {
    const run = runs.find((r) => r.id === runId);
    if (run) setSelectedRun(run);
  };

  const s = context.task.stats;

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[var(--color-bg)] relative">
      {/* Header bar */}
      <header className="shrink-0 bg-[var(--color-surface)] border-b border-[var(--color-border)] px-5 py-3 flex items-center">
        <Link href="/" className="w-8 h-8 rounded-lg bg-[var(--color-layer-1)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all mr-4">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8.5 3L4.5 7l4 4" />
          </svg>
        </Link>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-[var(--color-text)]">
            {context.task.name}
          </h1>
        </div>
        <div className="flex items-center gap-5 text-sm">
          <span><span className="text-[var(--color-text)] font-semibold">{s.total_runs}</span> <span className="text-[var(--color-text-secondary)]">runs</span></span>
          <span className="text-[var(--color-border)]">|</span>
          <span><span className="text-[var(--color-text)] font-semibold">{s.agents_contributing}</span> <span className="text-[var(--color-text-secondary)]">agents</span></span>
          <span className="text-[var(--color-border)]">|</span>
          <span><span className="text-[var(--color-text)] font-semibold">{s.improvements}</span> <span className="text-[var(--color-text-secondary)]">improvements</span></span>
        </div>
      </header>

      {/* Main content — fills remaining space */}
      <main className="flex-1 min-h-0 flex bg-[var(--color-surface)] overflow-hidden">
        {/* Chart panel */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="flex-1 min-h-0">
            <ChartToggle runs={runs} onRunClick={handleRunClick} />
          </div>
        </div>

        {/* Vertical divider */}
        <div className="w-px bg-[var(--color-border)] shrink-0" />

        {/* Right column */}
        <div className="w-[400px] shrink-0 flex flex-col min-h-0">
          {/* Leaderboard section */}
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="px-4 pt-3 pb-2 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">Leaderboard</div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <Leaderboard taskId={taskId} onRunClick={handleRunIdClick} />
            </div>
          </div>

          {/* Horizontal divider */}
          <div className="h-px bg-[var(--color-border)] shrink-0" />

          {/* Activity section */}
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="px-4 pt-3 pb-2 text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">Activity</div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <Feed items={items} skills={context.skills} onRunClick={handleRunIdClick} compact />
            </div>
          </div>
        </div>
      </main>

      {selectedRun && (
        <RunDetail run={selectedRun} runs={runs} taskId={taskId} repoUrl={context.task.repo_url} onClose={() => setSelectedRun(null)} />
      )}
    </div>
  );
}
