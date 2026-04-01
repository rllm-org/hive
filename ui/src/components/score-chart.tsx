"use client";

import React, { useMemo, useState, useEffect, useRef } from "react";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";
import { resolveRun, resolveId, buildRunMap } from "@/lib/run-utils";
import { timeAgo } from "@/lib/time";
import { LuCrown } from "react-icons/lu";

interface ScoreChartProps {
  runs: Run[];
  onRunClick?: (run: Run) => void;
  showAxes?: boolean;
  animate?: boolean;
  showBest?: boolean;
  hideGrid?: boolean;
}

function findBestLineage(runs: Run[]): { ids: Set<string>; chains: Set<string>[] } {
  const runMap = buildRunMap(runs);
  const scored = runs.filter((r) => r.score !== null);
  if (scored.length === 0) return { ids: new Set(), chains: [] };

  const bestScore = Math.max(...scored.map((r) => r.score!));
  const winners = scored.filter((r) => r.score === bestScore);
  const ids = new Set<string>();
  const chains: Set<string>[] = [];

  for (const winner of winners) {
    const chain = new Set<string>();
    let current: Run | undefined = winner;
    while (current) {
      ids.add(current.id);
      chain.add(current.id);
      current = current.parent_id ? resolveRun(current.parent_id, runMap) : undefined;
    }
    chains.push(chain);
  }

  return { ids, chains };
}

interface PointData {
  idx: number;
  run: Run;
  isLineage: boolean;
}

export function ScoreChart({ runs, onRunClick, showAxes = false, animate = false, showBest = false, hideGrid = false }: ScoreChartProps) {
  const [hoveredRun, setHoveredRun] = React.useState<{ run: Run; x: number; y: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const { allPoints, pointsByIdx, edges, lineageChains, yMin, yMax } = useMemo(() => {
    const scored = runs
      .filter((r) => r.score !== null && r.valid !== false)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    const { ids: lineageIds, chains: lineageChains } = findBestLineage(scored);

    const allPoints: PointData[] = scored.map((run, i) => ({
      idx: i + 1,
      run,
      isLineage: lineageIds.has(run.id),
    }));

    const idxMap = new Map<string, number>();
    scored.forEach((r, i) => idxMap.set(r.id, i + 1));

    const edges: { parentIdx: number; childIdx: number; isBestLineage: boolean }[] = [];
    for (const run of scored) {
      if (run.parent_id) {
        const parentFullId = resolveId(run.parent_id, idxMap.keys());
        if (parentFullId !== undefined) {
          edges.push({
            parentIdx: idxMap.get(parentFullId)!,
            childIdx: idxMap.get(run.id)!,
            isBestLineage: lineageChains.some((c) => c.has(run.id) && c.has(parentFullId)),
          });
        }
      }
    }

    const allScores = scored.map((r) => r.score!);
    const range = Math.max(...allScores) - Math.min(...allScores);

    const pointsByIdx = new Map<number, PointData>();
    for (const p of allPoints) pointsByIdx.set(p.idx, p);

    return {
      allPoints,
      pointsByIdx,
      edges,
      lineageChains,
      yMin: Math.min(...allScores) - range * 0.05,
      yMax: Math.max(...allScores) + range * 0.05,
    };
  }, [runs]);

  // Progressive build animation
  const totalPoints = allPoints.length;
  const [visibleCount, setVisibleCount] = useState(animate ? 0 : totalPoints);
  const prevRunsLen = useRef(runs.length);

  useEffect(() => {
    if (!animate) {
      setVisibleCount(totalPoints);
      return;
    }
    if (Math.abs(runs.length - prevRunsLen.current) > 2) {
      setVisibleCount(0);
    }
    prevRunsLen.current = runs.length;

    if (visibleCount >= totalPoints) return;
    const speed = Math.max(8, 40 - totalPoints * 0.3);
    const timer = setTimeout(() => {
      setVisibleCount((c) => Math.min(c + 1, totalPoints));
    }, speed);
    return () => clearTimeout(timer);
  }, [animate, totalPoints, visibleCount, runs.length]);

  const visiblePoints = useMemo(() => animate ? allPoints.slice(0, visibleCount) : allPoints, [allPoints, visibleCount, animate]);
  const visibleEdges = useMemo(() => animate ? edges.filter((e) => e.childIdx <= visibleCount && e.parentIdx <= visibleCount) : edges, [edges, visibleCount, animate]);
  const visibleChains = useMemo(() => {
    if (!animate) return lineageChains;
    return lineageChains.map((chain) => {
      const filtered = new Set<string>();
      for (const id of chain) {
        const p = allPoints.find((pt) => pt.run.id === id);
        if (p && p.idx <= visibleCount) filtered.add(id);
      }
      return filtered;
    });
  }, [lineageChains, allPoints, visibleCount, animate]);

  // Layout
  const padLeft = showAxes ? 56 : 16;
  const padRight = 16;
  const padTop = 16;
  const padBottom = showAxes ? 36 : 16;
  const w = size.width;
  const h = size.height;
  const effectiveMax = Math.max(totalPoints, 2);
  const xScale = (v: number) => padLeft + ((v - 1) / (effectiveMax - 1)) * (w - padLeft - padRight);
  const yRange = yMax - yMin;
  const yScale = (v: number) => yRange === 0 ? h / 2 : h - padBottom - ((v - yMin) / yRange) * (h - padTop - padBottom);

  // Ticks
  const xTickCount = Math.min(15, effectiveMax);
  const xStep = Math.max(1, Math.ceil(effectiveMax / xTickCount));
  const xTicks = Array.from({ length: effectiveMax }, (_, i) => i + 1).filter((v) => (v - 1) % xStep === 0);
  const yTickCount = 5;
  const yStep = yRange / yTickCount;
  const yTicks = Array.from({ length: yTickCount + 1 }, (_, i) => yMin + i * yStep);

  return (
    <div ref={containerRef} className="h-full w-full relative overflow-visible" role="img" aria-label="Score progression chart">
      {w > 0 && h > 0 && (
        <svg width={w} height={h}>
          {showAxes && (
            <>
              {yTicks.map((v, i) => (
                <g key={`y-${i}`}>
                  {!hideGrid && <line x1={padLeft} y1={yScale(v)} x2={w - padRight} y2={yScale(v)} stroke="var(--color-border)" strokeWidth={0.5} strokeDasharray="4 3" />}
                  <text x={padLeft - 8} y={yScale(v)} textAnchor="end" dominantBaseline="middle" fill="var(--color-text-tertiary)" fontSize={11} fontFamily="'IBM Plex Mono', monospace">
                    {v.toFixed(yRange > 100 ? 0 : 3)}
                  </text>
                </g>
              ))}
              {xTicks.map((v) => (
                <text key={`x-${v}`} x={xScale(v)} y={h - padBottom + 20} textAnchor="middle" fill="var(--color-text-tertiary)" fontSize={11} fontFamily="'IBM Plex Mono', monospace">
                  {v}
                </text>
              ))}
              <text x={w / 2} y={h - 4} textAnchor="middle" fill="var(--color-text-tertiary)" fontSize={11} fontFamily="'IBM Plex Mono', monospace">Experiment</text>
              <text x={14} y={h / 2} textAnchor="middle" dominantBaseline="middle" fill="var(--color-text-tertiary)" fontSize={11} fontFamily="'IBM Plex Mono', monospace" transform={`rotate(-90, 14, ${h / 2})`}>Score</text>
            </>
          )}
          {/* Non-best edges */}
          <g>
            {visibleEdges.filter(e => !e.isBestLineage).map((e, i) => {
              const parentPt = pointsByIdx.get(e.parentIdx);
              const childPt = pointsByIdx.get(e.childIdx);
              if (!parentPt || !childPt) return null;
              return (
                <line key={i} x1={xScale(e.parentIdx)} y1={yScale(parentPt.run.score!)} x2={xScale(e.childIdx)} y2={yScale(childPt.run.score!)}
                  stroke="var(--color-border)" strokeWidth={1} opacity={0.6} />
              );
            })}
          </g>
          {/* Best lineage paths */}
          <g>
            {visibleChains.map((chain, ci) => {
              const pts = visiblePoints
                .filter((p) => chain.has(p.run.id))
                .sort((a, b) => a.idx - b.idx);
              if (pts.length < 2) return null;
              const pathD = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.idx)} ${yScale(p.run.score!)}`).join(" ");
              return (
                <g key={ci}>
                  <path d={pathD} fill="none" stroke="var(--color-accent-hover)" strokeWidth={2.5} opacity={0.15} strokeLinecap="round" strokeLinejoin="round" />
                  <path d={pathD} fill="none" stroke="var(--color-accent)" strokeWidth={1.2} opacity={0.4} strokeLinecap="round" strokeLinejoin="round" />
                </g>
              );
            })}
          </g>
          {/* Points */}
          <g>
            {visiblePoints.map((p) => {
              const cx = xScale(p.idx);
              const cy = yScale(p.run.score!);
              const color = getAgentColor(p.run.agent_id);
              return p.isLineage ? (
                <circle key={p.run.id} cx={cx} cy={cy} r={6}
                  fill={color} stroke="var(--color-surface)" strokeWidth={2}
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredRun({ run: p.run, x: cx, y: cy })}
                  onMouseLeave={() => setHoveredRun(null)}
                  onClick={() => onRunClick?.(p.run)} />
              ) : (
                <circle key={p.run.id} cx={cx} cy={cy} r={3.5}
                  fill={color} stroke="var(--color-surface)" strokeWidth={1} opacity={0.35}
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredRun({ run: p.run, x: cx, y: cy })}
                  onMouseLeave={() => setHoveredRun(null)}
                  onClick={() => onRunClick?.(p.run)} />
              );
            })}
          </g>
        </svg>
      )}
      {/* Best run indicator */}
      {showBest && visibleCount >= totalPoints && w > 0 && h > 0 && (() => {
        const best = visiblePoints.filter((p) => p.isLineage).sort((a, b) => b.run.score! - a.run.score!)[0];
        if (!best) return null;
        const bx = xScale(best.idx);
        const by = yScale(best.run.score!);
        return (
          <div
            className="absolute pointer-events-none"
            style={{ left: bx, top: Math.max(0, by - 26), transform: "translateX(-50%)" }}
          >
            <LuCrown className="w-4 h-4 text-[var(--color-accent)]" />
          </div>
        );
      })()}
      {/* Tooltip */}
      {hoveredRun && (
        <div
          className="absolute pointer-events-none z-20 card p-3 w-max max-w-xs"
          style={{
            left: hoveredRun.x + 70,
            top: hoveredRun.y - 10,
            transform: hoveredRun.x > w * 0.6 ? "translateX(-110%)" : undefined,
          }}
        >
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: getAgentColor(hoveredRun.run.agent_id) }} />
            <span className="text-sm font-semibold text-[var(--color-text)]">{hoveredRun.run.agent_id}</span>
            <span className="text-[var(--color-text-secondary)] text-[11px]">{timeAgo(hoveredRun.run.created_at)}</span>
          </div>
          <div className="font-[family-name:var(--font-ibm-plex-mono)] text-lg font-bold text-[var(--color-text)]">{hoveredRun.run.score?.toFixed(3)}</div>
          <div className="text-xs text-[var(--color-text-secondary)] mt-0.5">{hoveredRun.run.tldr}</div>
        </div>
      )}
    </div>
  );
}
