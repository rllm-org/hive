"use client";

import { useMemo, forwardRef, CSSProperties } from "react";
import { Run, Task, BestRunsResponse } from "@/types/api";
import { ScoreChart } from "@/components/score-chart";

const lightVars: Record<string, string> = {
  "--color-bg": "#fafbfc",
  "--color-surface": "#ffffff",
  "--color-text": "#111827",
  "--color-text-secondary": "#374151",
  "--color-text-tertiary": "#4b5563",
  "--color-accent": "#2f5f99",
  "--color-border": "#e5e7eb",
  "--color-border-light": "#f1f3f5",
  "--color-accent-50": "#eff6ff",
  "--color-layer-1": "#f9fafb",
  "--color-layer-2": "#f3f4f6",
  "--color-layer-3": "#e5e7eb",
};

const darkVars: Record<string, string> = {
  "--color-bg": "#0f1117",
  "--color-surface": "#1a1d27",
  "--color-text": "#e5e7eb",
  "--color-text-secondary": "#9ca3af",
  "--color-text-tertiary": "#6b7280",
  "--color-accent": "#5b9bd5",
  "--color-border": "#2d3140",
  "--color-border-light": "#232736",
  "--color-accent-50": "#1a2332",
  "--color-layer-1": "#151820",
  "--color-layer-2": "#1e2130",
  "--color-layer-3": "#2d3140",
};

interface ShareImageProps {
  runs: Run[];
  task: Task;
  leaderboardRuns: BestRunsResponse["runs"];
  theme: "light" | "dark";
  title?: string;
  titleFontSize?: number;
}

export const ShareImage = forwardRef<HTMLDivElement, ShareImageProps>(
  function ShareImage({ runs, task, leaderboardRuns, theme, title, titleFontSize: externalFontSize }, ref) {
    const d = theme === "dark";
    const { firstScore, bestScore, pctChange, days } = useMemo(() => {
      const sorted = runs
        .filter((r) => r.score != null && r.valid !== false)
        .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
      const first = sorted[0]?.score ?? null;
      const best = task.stats.best_score;
      const pct = first != null && best != null && first !== 0
        ? ((best - first) / Math.abs(first)) * 100
        : null;
      const d = sorted.length >= 2
        ? Math.ceil((new Date(sorted[sorted.length - 1].created_at).getTime() - new Date(sorted[0].created_at).getTime()) / 86400000)
        : null;
      return { firstScore: first, bestScore: best, pctChange: pct, days: d };
    }, [runs, task.stats.best_score]);

    function formatScore(v: number) {
      return parseFloat(v.toFixed(3)).toString();
    }

    const titleFontSize = externalFontSize ?? 72;

    return (
      <div
        ref={ref}
        className={d ? "dark" : ""}
        style={{
          width: 1250,
          height: 500,
          display: "flex",
          flexDirection: "column",
          position: "relative",
          backgroundColor: d ? "#0f1117" : "#fafbfc",
          color: d ? "#e5e7eb" : "#111827",
          fontFamily: "var(--font-dm-sans), system-ui, sans-serif",
          overflow: "hidden",
          ...(d ? darkVars : lightVars),
        } as CSSProperties}
      >
        {/* Graph with Hive logo overlay */}
        <div style={{ flex: 1, padding: "16px 24px", minHeight: 0, position: "relative" }}>
          <ScoreChart runs={runs} showAxes showBest hideGrid />
          <div style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            transform: "translate(-50%, -50%)",
            display: "flex",
            alignItems: "center",
            gap: 0,
            pointerEvents: "none",
            zIndex: 10,
          }}>
            <img src="/hive-logo-solid.svg" alt="Hive" width={120} height={120} />
            <span style={{ marginLeft: -10, fontSize: 80, fontWeight: 700, letterSpacing: "-0.03em", color: d ? "#e5e7eb" : "#111827" }}>Hive</span>
          </div>
        </div>

        {/* Bottom bar */}
        <div style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          padding: "20px 28px",
          borderTop: `1px solid ${d ? "#1e2130" : "#e5e7eb"}`,
          flexShrink: 0,
          position: "relative",
        }}>
          {/* Left: task name */}
          <div style={{
              fontSize: titleFontSize,
              fontWeight: 400,
              lineHeight: 1.15,
              letterSpacing: "-0.025em",
              color: d ? "#e5e7eb" : "#111827",
              flexShrink: 1,
              minWidth: 0,
            }}
          >
            {title || task.name}
          </div>

          {/* Right: scores */}
          {firstScore != null && bestScore != null && (
            <div style={{
              fontFamily: "var(--font-ibm-plex-mono), monospace",
              fontSize: 48,
              fontWeight: 800,
              letterSpacing: "-0.03em",
              whiteSpace: "nowrap",
              flexShrink: 0,
            }}>
              <span style={{ fontSize: 32, fontWeight: 600, color: d ? "#f87171" : "#dc2626" }}>{formatScore(firstScore)}</span>
              <span style={{ color: d ? "#4b5563" : "#d1d5db", margin: "0 14px", fontSize: 30 }}>→</span>
              <span style={{ color: d ? "#4ade80" : "#16a34a" }}>{formatScore(bestScore)}</span>
            </div>
          )}
        </div>
      </div>
    );
  }
);
