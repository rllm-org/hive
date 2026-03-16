"use client";

import { useMemo, useState, useRef, useEffect, useCallback } from "react";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";
import { buildTree, layoutTree } from "@/lib/tree-layout";
import { resolveRun, buildRunMap } from "@/lib/run-utils";

interface EvolutionTreeProps {
  runs: Run[];
  onRunClick?: (run: Run) => void;
}

const NODE_W = 220;
const NODE_H = 68;
const GAP_X = 28;
const GAP_Y = 56;

const MIN_ZOOM = 0.15;
const MAX_ZOOM = 3;
const ZOOM_STEP = 1.15;

function clampZoom(z: number) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
}

function getBestLineage(runs: Run[]): { ids: Set<string>; chains: Set<string>[] } {
  if (runs.length === 0) return { ids: new Set(), chains: [] };

  const scored = runs.filter((r) => r.score !== null);
  if (scored.length === 0) return { ids: new Set(), chains: [] };

  const bestScore = Math.max(...scored.map((r) => r.score!));
  const winners = scored.filter((r) => r.score === bestScore);
  const byId = buildRunMap(runs);
  const ids = new Set<string>();
  const chains: Set<string>[] = [];

  for (const winner of winners) {
    const chain = new Set<string>();
    let current: Run | undefined = winner;
    while (current) {
      ids.add(current.id);
      chain.add(current.id);
      current = current.parent_id ? resolveRun(current.parent_id, byId) : undefined;
    }
    chains.push(chain);
  }

  return { ids, chains };
}

export function EvolutionTree({ runs, onRunClick }: EvolutionTreeProps) {
  const { nodes, edges, width, height } = useMemo(() => {
    const roots = buildTree(runs);
    return layoutTree(roots, NODE_W, NODE_H, GAP_X, GAP_Y);
  }, [runs]);

  const { ids: bestLineage, chains: bestChains } = useMemo(() => getBestLineage(runs), [runs]);

  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 10, y: 10 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  // Use refs for zoom/pan so event handlers always see latest values
  const zoomRef = useRef(zoom);
  const panRef = useRef(pan);
  zoomRef.current = zoom;
  panRef.current = pan;

  const zoomToward = useCallback((clientX: number, clientY: number, newZoom: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const cx = clientX - rect.left;
    const cy = clientY - rect.top;
    const oldZoom = zoomRef.current;
    const oldPan = panRef.current;
    const ratio = newZoom / oldZoom;
    setPan({ x: cx - (cx - oldPan.x) * ratio, y: cy - (cy - oldPan.y) * ratio });
    setZoom(newZoom);
  }, []);

  const zoomToCenter = useCallback((newZoom: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    zoomToward(rect.left + rect.width / 2, rect.top + rect.height / 2, newZoom);
  }, [zoomToward]);

  // Wheel: pinch-to-zoom (ctrlKey) or pan
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        // Pinch-to-zoom or ctrl+scroll
        const factor = e.deltaY > 0 ? 1 / ZOOM_STEP : ZOOM_STEP;
        const newZoom = clampZoom(zoomRef.current * factor);
        zoomToward(e.clientX, e.clientY, newZoom);
      } else {
        // Plain scroll → pan
        setPan((p) => ({ x: p.x - e.deltaX, y: p.y - e.deltaY }));
      }
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomToward]);

  // Keyboard: Cmd/Ctrl + =/-/0
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "=" || e.key === "+") {
        e.preventDefault();
        zoomToCenter(clampZoom(zoomRef.current * ZOOM_STEP));
      } else if (e.key === "-") {
        e.preventDefault();
        zoomToCenter(clampZoom(zoomRef.current / ZOOM_STEP));
      } else if (e.key === "0") {
        e.preventDefault();
        setZoom(1);
        setPan({ x: 10, y: 10 });
      }
    };

    el.addEventListener("keydown", onKeyDown);
    return () => el.removeEventListener("keydown", onKeyDown);
  }, [zoomToCenter]);

  // Pointer drag-to-pan
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    // Only pan on primary button (left click)
    if (e.button !== 0) return;
    setIsDragging(true);
    dragStart.current = { x: e.clientX, y: e.clientY, panX: panRef.current.x, panY: panRef.current.y };
    (e.target as Element).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragStart.current) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    setPan({ x: dragStart.current.panX + dx, y: dragStart.current.panY + dy });
  }, []);

  const onPointerUp = useCallback(() => {
    setIsDragging(false);
    dragStart.current = null;
  }, []);

  const zoomPct = Math.round(zoom * 100);
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);
  const modKey = isMac ? "\u2318" : "Ctrl+";

  return (
    <div
      ref={containerRef}
      className="overflow-hidden h-full w-full relative outline-none"
      tabIndex={0}
      style={{ cursor: isDragging ? "grabbing" : "grab" }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      <svg width="100%" height="100%">
        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          {/* Edges */}
          {edges.map((e, i) => {
            const x1 = e.parent.x + NODE_W / 2;
            const y1 = e.parent.y + NODE_H;
            const x2 = e.child.x + NODE_W / 2;
            const y2 = e.child.y;
            const my = (y1 + y2) / 2;
            const inLineage = bestChains.some((c) => c.has(e.parent.run.id) && c.has(e.child.run.id));
            return (
              <path key={i} d={`M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`}
                fill="none"
                stroke={inLineage ? "#3f72af" : "#e5e7eb"}
                strokeWidth={inLineage ? 2 : 1.5} />
            );
          })}

          {/* Nodes */}
          {nodes.map((node) => {
            const inLineage = bestLineage.has(node.run.id);
            return (
              <g key={node.run.id} transform={`translate(${node.x}, ${node.y})`}
                onClick={() => onRunClick?.(node.run)} className="cursor-pointer">
                <rect width={NODE_W} height={NODE_H} rx={8}
                  fill={inLineage ? "#eff6ff" : "#ffffff"}
                  stroke={inLineage ? "#3f72af" : "#e5e7eb"}
                  strokeWidth={inLineage ? 1.5 : 1} />
                <text x={NODE_W / 2} y={24} fill="#111827" fontSize={12} fontFamily="'IBM Plex Mono', monospace" textAnchor="middle">
                  {node.run.tldr.length > 24 ? node.run.tldr.slice(0, 24) + "..." : node.run.tldr}
                </text>
                <text x={NODE_W / 2} y={44} fill="#111827" fontSize={16} fontFamily="'DM Sans', sans-serif" fontWeight={600} textAnchor="middle">
                  {node.run.agent_id.length > 20 ? node.run.agent_id.slice(0, 20) + "…" : node.run.agent_id}
                </text>
                {node.run.score !== null && (
                  <text x={NODE_W / 2} y={61}
                    fill={inLineage ? "#3f72af" : "#6b7280"}
                    fontSize={10}
                    fontWeight={inLineage ? 600 : 400}
                    fontFamily="'IBM Plex Mono', monospace" textAnchor="middle">
                    {node.run.score.toFixed(3)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Controls overlay */}
      <div className="absolute bottom-2 right-2 flex items-center gap-1.5">
        <div className="px-2 py-1 rounded text-[10px] bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)] leading-tight select-none">
          Scroll to pan · Pinch or <kbd className="font-[family-name:var(--font-ibm-plex-mono)]">{modKey}+/{modKey}&ndash;</kbd> to zoom · <kbd className="font-[family-name:var(--font-ibm-plex-mono)]">{modKey}0</kbd> reset
        </div>
        {zoomPct !== 100 && (
          <button
            onClick={() => { setZoom(1); setPan({ x: 10, y: 10 }); }}
            className="px-2 py-1 rounded text-[10px] font-[family-name:var(--font-ibm-plex-mono)] bg-[var(--color-layer-2)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border)] transition-colors"
          >
            {zoomPct}%
          </button>
        )}
      </div>
    </div>
  );
}
