"use client";

import { useState } from "react";
import { ScoreChart } from "./score-chart";
import { EvolutionTree } from "./evolution-tree";
import { Run } from "@/types/api";

interface ChartToggleProps {
  runs: Run[];
  onRunClick?: (run: Run) => void;
}

export function ChartToggle({ runs, onRunClick }: ChartToggleProps) {
  const [view, setView] = useState<"score" | "tree">("score");

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex items-center gap-1 px-4 pt-3 pb-2 shrink-0">
        <span className="text-xs font-bold text-[var(--color-text)] uppercase tracking-wide mr-auto">Graph</span>
        {(["score", "tree"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1 font-medium text-xs rounded-lg transition-all ${
              view === v
                ? "bg-[var(--color-accent-50)] text-[var(--color-accent-700)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)]"
            }`}
          >
            {v === "score" ? "Score" : "Tree"}
          </button>
        ))}
      </div>
      <div className="flex-1 min-h-0 px-1 pb-1">
        {view === "score" ? (
          <div className="h-full">
            <ScoreChart runs={runs} onRunClick={onRunClick} />
          </div>
        ) : (
          <EvolutionTree runs={runs} onRunClick={onRunClick} />
        )}
      </div>
    </div>
  );
}
