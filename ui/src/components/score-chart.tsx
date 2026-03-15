"use client";

import React, { useMemo } from "react";
import { ResponsiveLine } from "@nivo/line";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";

interface ScoreChartProps {
  runs: Run[];
  onRunClick?: (run: Run) => void;
}

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function findBestLineage(runs: Run[]): Set<string> {
  const runMap = new Map<string, Run>();
  for (const r of runs) runMap.set(r.id, r);
  let best: Run | null = null;
  for (const r of runs) {
    if (r.score !== null && (!best || r.score > best.score!)) best = r;
  }
  if (!best) return new Set();
  const lineage = new Set<string>();
  let current: Run | undefined = best;
  while (current) {
    lineage.add(current.id);
    current = current.parent_id ? runMap.get(current.parent_id) : undefined;
  }
  return lineage;
}

interface PointData {
  idx: number;
  run: Run;
  isLineage: boolean;
}

export function ScoreChart({ runs, onRunClick }: ScoreChartProps) {
  const [hoveredRun, setHoveredRun] = React.useState<{ run: Run; x: number; y: number } | null>(null);

  const { lineData, allPoints, yMin, yMax, xMax } = useMemo(() => {
    const scored = runs
      .filter((r) => r.score !== null)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    const lineageIds = findBestLineage(scored);

    const linePoints = scored
      .filter((r) => lineageIds.has(r.id))
      .map((r) => ({ x: scored.indexOf(r), y: r.score! }));

    const allPoints: PointData[] = scored.map((run, i) => ({
      idx: i,
      run,
      isLineage: lineageIds.has(run.id),
    }));

    const allScores = scored.map((r) => r.score!);
    const range = Math.max(...allScores) - Math.min(...allScores);

    return {
      lineData: [{ id: "lineage", data: linePoints }],
      allPoints,
      yMin: Math.min(...allScores) - range * 0.05,
      yMax: Math.max(...allScores) + range * 0.05,
      xMax: scored.length - 1,
    };
  }, [runs]);

  // SVG filter + custom layer for string-like line
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const StringLayer = ({ xScale, yScale }: any) => {
    const lineagePoints = allPoints
      .filter((p) => p.isLineage)
      .sort((a, b) => a.idx - b.idx);

    if (lineagePoints.length < 2) return null;

    const pathD = lineagePoints
      .map((p, i) => {
        const x = (xScale as (v: number) => number)(p.idx);
        const y = (yScale as (v: number) => number)(p.run.score!);
        return `${i === 0 ? "M" : "L"} ${x} ${y}`;
      })
      .join(" ");

    return (
      <g>
        <defs>
          <filter id="string-texture">
            <feTurbulence type="turbulence" baseFrequency="0.04" numOctaves="4" result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.5" />
          </filter>
        </defs>
        {/* Shadow/thickness for string feel */}
        <path d={pathD} fill="none" stroke="#8b0000" strokeWidth={3} opacity={0.3} strokeLinecap="round" strokeLinejoin="round" filter="url(#string-texture)" />
        {/* Main string */}
        <path d={pathD} fill="none" stroke="#cc3333" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" filter="url(#string-texture)" />
      </g>
    );
  };

  // Custom layer: draw pin dots on top of the string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const PinLayer = ({ xScale, yScale }: any) => {
    return (
      <g>
        {allPoints.map((p) => {
          const cx = (xScale as (v: number) => number)(p.idx);
          const cy = (yScale as (v: number) => number)(p.run.score!);
          const color = getAgentColor(p.run.agent_id);

          if (!p.isLineage) {
            return (
              <circle
                key={p.run.id}
                cx={cx} cy={cy} r={3.5}
                fill="#8b7355" stroke="#faf3e6" strokeWidth={1}
                opacity={0.5}
                className="cursor-pointer"
                onMouseEnter={(e) => {
                  setHoveredRun({ run: p.run, x: cx, y: cy });
                }}
                onMouseLeave={() => setHoveredRun(null)}
                onClick={() => onRunClick?.(p.run)}
              />
            );
          }

          return (
            <circle
              key={p.run.id}
              cx={cx} cy={cy} r={6}
              fill={color} stroke="#faf3e6" strokeWidth={2}
              className="cursor-pointer"
              onMouseEnter={() => setHoveredRun({ run: p.run, x: cx, y: cy })}
              onMouseLeave={() => setHoveredRun(null)}
              onClick={() => onRunClick?.(p.run)}
            />
          );
        })}
      </g>
    );
  };

  return (
    <div className="h-full w-full relative">
      <ResponsiveLine
        data={lineData}
        xScale={{ type: "linear", min: 0, max: xMax }}
        yScale={{ type: "linear", min: yMin, max: yMax }}
        margin={{ top: 4, right: 24, bottom: 40, left: 56 }}
        colors={["#cc3333"]}
        lineWidth={1.5}
        curve="linear"
        enablePoints={false}
        enableGridX={false}
        gridYValues={5}
        theme={{
          grid: { line: { stroke: "#d8d0c0", strokeWidth: 0.5, strokeDasharray: "4 3" } },
          axis: {
            ticks: { text: { fill: "#8b7355", fontSize: 11, fontFamily: "'Courier Prime', monospace" } },
            legend: { text: { fill: "#8b7355", fontSize: 11, fontFamily: "'Courier Prime', monospace" } },
          },
        }}
        axisBottom={{
          tickSize: 0,
          tickPadding: 8,
          format: (v) => `#${v}`,
          legend: "Experiment #",
          legendOffset: 30,
          legendPosition: "middle",
        }}
        axisLeft={{
          tickSize: 0,
          tickPadding: 8,
          format: (v) => Number(v).toFixed(2),
          legend: "Score",
          legendOffset: -46,
          legendPosition: "middle",
        }}
        isInteractive={false}
        animate={false}
        layers={[
          "grid",
          "axes",
          StringLayer,
          PinLayer,
        ]}
      />

      {/* Tooltip */}
      {hoveredRun && (
        <div
          className="absolute pointer-events-none z-20 paper-card p-3 max-w-xs"
          style={{
            left: hoveredRun.x + 70,
            top: hoveredRun.y - 10,
            transform: hoveredRun.x > 500 ? "translateX(-110%)" : undefined,
          }}
        >
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: getAgentColor(hoveredRun.run.agent_id) }} />
            <span className="font-[family-name:var(--font-handwritten)] text-[16px] font-semibold text-[var(--accent-blue)]">
              {hoveredRun.run.agent_id}
            </span>
            <span className="text-[var(--text-dim)] text-[11px] font-[family-name:var(--font-typewriter)]">{relativeTime(hoveredRun.run.created_at)}</span>
          </div>
          <div className="font-[family-name:var(--font-typewriter)] text-lg font-bold text-[var(--text-dark)]">
            {hoveredRun.run.score?.toFixed(3)}
          </div>
          <div className="font-[family-name:var(--font-typewriter)] text-[11px] text-[var(--text-dim)] mt-0.5">{hoveredRun.run.tldr}</div>
        </div>
      )}
    </div>
  );
}
