"use client";

import { useState, useMemo } from "react";
import { ScoreChart } from "./score-chart";
import { EvolutionTree } from "./evolution-tree";
import { Run } from "@/types/api";
import { useGraph } from "@/hooks/use-graph";
import { TabButtons } from "@/components/shared/toggle";

type ChartView = "score" | "tree";
export type VerificationFilter = "all" | "verified";

const CHART_OPTIONS: { value: ChartView; label: string }[] = [
  { value: "score", label: "Score" },
  { value: "tree", label: "Tree" },
];

const VERIFICATION_OPTIONS: { value: VerificationFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "verified", label: "Verified" },
];

interface ChartToggleProps {
  taskId: string;
  onRunClick?: (run: Run) => void;
  verificationEnabled?: boolean;
  onVerificationFilterChange?: (filter: VerificationFilter) => void;
}

export function ChartToggle({ taskId, onRunClick, verificationEnabled, onVerificationFilterChange }: ChartToggleProps) {
  const [view, setView] = useState<ChartView>("score");
  const [verificationFilter, setVerificationFilter] = useState<VerificationFilter>("all");
  const { runs } = useGraph(taskId);

  const filteredRuns = useMemo(() => {
    if (!verificationEnabled) return runs;
    if (verificationFilter === "verified") {
      return runs.filter((r) => r.verified);
    }
    return runs;
  }, [runs, verificationEnabled, verificationFilter]);

  const handleVerificationFilterChange = (filter: VerificationFilter) => {
    setVerificationFilter(filter);
    onVerificationFilterChange?.(filter);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex items-center gap-1 px-4 pt-3 pb-2 shrink-0">
        <span className="text-xs font-bold text-[var(--color-text)] uppercase tracking-wide mr-auto">Graph</span>
        <div className="hidden md:flex items-center gap-2">
          {verificationEnabled && (
            <TabButtons value={verificationFilter} onChange={handleVerificationFilterChange} options={VERIFICATION_OPTIONS} />
          )}
          <TabButtons value={view} onChange={setView} options={CHART_OPTIONS} />
        </div>
      </div>
      <div className="flex-1 min-h-0 px-1 pb-1 relative">
        {view === "score" ? (
          <div className="absolute inset-0">
            <ScoreChart runs={filteredRuns} onRunClick={onRunClick} showAxes />
          </div>
        ) : (
          <div className="absolute inset-0">
            <EvolutionTree runs={filteredRuns} onRunClick={onRunClick} />
          </div>
        )}
      </div>
    </div>
  );
}
