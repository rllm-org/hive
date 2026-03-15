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
      <div className="flex items-center gap-1 px-2 pt-2 pb-1 shrink-0">
        <span className="mr-auto" />
        {(["score", "tree"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1 rounded text-[11px] font-[family-name:var(--font-typewriter)] transition-all ${
              view === v
                ? "bg-[var(--bg-dark-card)] text-[var(--text)]"
                : "text-[var(--text-dim)] hover:text-[var(--text-dark)] hover:bg-[#f0ede6]"
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
