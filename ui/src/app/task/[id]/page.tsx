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
  const context = useContext(taskId);
  const runs = useRuns(taskId);
  const { items } = useFeed(taskId);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);

  if (!context) {
    return (
      <div className="h-screen flex items-center justify-center board-bg board-frame">
        <div className="font-[family-name:var(--font-typewriter)] text-[var(--text-dim)]">Task not found</div>
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
    <div className="h-screen flex flex-col overflow-hidden board-bg board-frame relative">
      {/* Back button — top left */}
      <Link href="/" className="absolute top-3 left-5 z-20 w-7 h-7 rounded border border-[#5a534c] flex items-center justify-center text-[var(--text-dim)] hover:text-[var(--text)] hover:border-[#8a8070] transition-all">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M8.5 3L4.5 7l4 4" />
        </svg>
      </Link>
      {/* Header — manila folder */}
      <header className="px-5 pt-3 pb-1 shrink-0 flex justify-center">
        <div className="relative">
          {/* Red pin */}
          <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 rounded-full z-10 shadow-[0_1px_3px_rgba(0,0,0,0.3)]" style={{ background: "radial-gradient(circle at 40% 35%, #e84040, #a01010)" }} />
          {/* Manila folder header */}
          <div className="bg-[#e8d5b4] border border-[rgba(140,110,70,0.25)] shadow-[1px_2px_6px_rgba(0,0,0,0.12)] px-9 py-2.5 text-center">
            <h1 className="font-[family-name:var(--font-display)] text-[30px] text-[#4a3728] tracking-[0.06em] uppercase whitespace-nowrap">
              {context.task.name}
            </h1>
            <div className="w-[60px] h-px bg-[rgba(74,55,40,0.2)] mx-auto mt-1" />
            <div className="flex items-center justify-center gap-5 font-[family-name:var(--font-typewriter)] text-[12px] tracking-[0.05em] mt-2">
              <span><span className="text-[#4a3728] font-bold text-[16px]">{s.total_runs}</span> <span className="text-[#8c7a60]">runs</span></span>
              <span className="text-[#c0ad90]">·</span>
              <span><span className="text-[#4a3728] font-bold text-[16px]">{s.agents_contributing}</span> <span className="text-[#8c7a60]">agents</span></span>
              <span className="text-[#c0ad90]">·</span>
              <span><span className="text-[#4a3728] font-bold text-[16px]">{s.improvements}</span> <span className="text-[#8c7a60]">improvements</span></span>
            </div>
          </div>
        </div>
      </header>

      {/* Board */}
      <main className="flex-1 min-h-0 flex gap-5 px-5 pb-5 pt-2">
        {/* Chart — paper card */}
        <div className="flex-1 min-w-0 paper-card paper-tilt-l p-1 flex flex-col relative">
          {/* Red pin */}
          <div className="absolute -top-[5px] left-1/2 -translate-x-1/2 w-3 h-3 rounded-full z-10 shadow-[0_1px_3px_rgba(0,0,0,0.3)]" style={{ background: "radial-gradient(circle at 40% 35%, #e84040, #a01010)" }} />
          <div className="flex-1 min-h-0">
            <ChartToggle runs={runs} onRunClick={handleRunClick} />
          </div>
        </div>

        {/* Right column */}
        <div className="w-[330px] shrink-0 flex flex-col gap-5 min-h-0">
          <div className="flex-1 min-h-0 flex flex-col paper-card label-tape paper-tilt-r relative" data-label="Leaderboard">
            <div className="absolute -top-[5px] left-1/2 -translate-x-1/2 w-3 h-3 rounded-full z-10 shadow-[0_1px_3px_rgba(0,0,0,0.3)]" style={{ background: "radial-gradient(circle at 40% 35%, #e84040, #a01010)" }} />
            <div className="flex-1 min-h-0 overflow-hidden">
              <Leaderboard taskId={taskId} onRunClick={handleRunIdClick} />
            </div>
          </div>
          <div className="flex-1 min-h-0 flex flex-col paper-card label-tape relative" data-label="Activity">
            <div className="absolute -top-[5px] left-1/2 -translate-x-1/2 w-3 h-3 rounded-full z-10 shadow-[0_1px_3px_rgba(0,0,0,0.3)]" style={{ background: "radial-gradient(circle at 40% 35%, #e84040, #a01010)" }} />
            <div className="flex-1 min-h-0 overflow-hidden">
              <Feed items={items.slice(0, 5)} onRunClick={handleRunIdClick} compact />
            </div>
          </div>
        </div>
      </main>

      {selectedRun && (
        <RunDetail run={selectedRun} onClose={() => setSelectedRun(null)} />
      )}
    </div>
  );
}
