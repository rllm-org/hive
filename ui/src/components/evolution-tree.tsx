"use client";

import { useMemo, useState, useRef, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";
import { resolveRun, resolveId, buildRunMap } from "@/lib/run-utils";
import { timeAgo } from "@/lib/time";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

interface EvolutionTreeProps {
  runs: Run[];
  onRunClick?: (run: Run) => void;
}

const ARTIFACT_ID = "__artifact_origin__";

interface GraphNode {
  id: string;
  run: Run;
  isArtifact: boolean;
  inLineage: boolean;
  color: string;
  fx?: number;
  fy?: number;
}

interface GraphLink {
  source: string;
  target: string;
  inLineage: boolean;
  isFromArtifact: boolean;
  siblingCount: number; // total children of the source node
  declined: boolean; // child scored lower than parent
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
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 400 });
  const [cursorStyle, setCursorStyle] = useState("grab");
  const [ready, setReady] = useState(false);

  // Measure container (debounced)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let raf: number;
    const ro = new ResizeObserver((entries) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const { width, height } = entries[0].contentRect;
        if (width > 0 && height > 0) setDimensions({ width, height });
      });
    });
    ro.observe(el);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);

  const { ids: bestLineage, chains: bestChains } = useMemo(() => getBestLineage(runs), [runs]);

  const graphData = useMemo(() => {
    const runIds = new Set(runs.map((r) => r.id));
    const nodeMap = new Map<string, GraphNode>();
    const links: GraphLink[] = [];

    // Build children map for tree layout
    const children = new Map<string, string[]>();
    children.set(ARTIFACT_ID, []);

    // Find roots and build parent→children
    for (const run of runs) {
      const parentFullId = run.parent_id ? resolveId(run.parent_id, runIds.values()) : undefined;
      if (!parentFullId || !runIds.has(parentFullId)) {
        children.get(ARTIFACT_ID)!.push(run.id);
      } else {
        if (!children.has(parentFullId)) children.set(parentFullId, []);
        children.get(parentFullId)!.push(run.id);
      }
    }

    // Sort children by score (best at top) for a clean visual
    const runById = new Map(runs.map((r) => [r.id, r]));
    for (const [, kids] of children) {
      kids.sort((a, b) => {
        const ra = runById.get(a), rb = runById.get(b);
        if (!ra || !rb) return 0;
        return (rb.score ?? 0) - (ra.score ?? 0);
      });
    }

    // Score range for delta scaling
    const scores = runs.filter((r) => r.score !== null).map((r) => r.score!);
    const minScore = scores.length > 0 ? Math.min(...scores) : 0;
    const maxScore = scores.length > 0 ? Math.max(...scores) : 1;
    const scoreRange = maxScore - minScore || 1;

    // Cumulative X constants — nodes always move right
    const BASE_STEP = 40;
    const BONUS_STEP = 200;
    const SMALL_STEP = 30;

    // Count leaves to compute GAP_Y dynamically
    let leafCount = 0;
    function countLeaves(nodeId: string) {
      const kids = children.get(nodeId) || [];
      if (kids.length === 0) { leafCount++; return; }
      for (const kid of kids) countLeaves(kid);
    }
    countLeaves(ARTIFACT_ID);

    // Layout: X = cumulative (always left-to-right), Y = leaf slots (compact)
    const GAP_Y = Math.max(3, Math.min(28, 1500 / Math.max(leafCount, 1)));
    let leafSlot = 0;
    const posMap = new Map<string, { fx: number; fy: number }>();

    function layout(nodeId: string, parentX: number, parentScore: number | null): number {
      let fx: number;
      if (nodeId === ARTIFACT_ID) {
        fx = -60;
      } else {
        const run = runById.get(nodeId);
        const myScore = run?.score ?? null;
        if (myScore === null || parentScore === null) {
          fx = parentX + BASE_STEP;
        } else {
          const scoreDelta = myScore - parentScore;
          if (scoreDelta >= 0) {
            fx = parentX + BASE_STEP + (scoreDelta / scoreRange) * BONUS_STEP;
          } else {
            const factor = Math.max(0.1, 1 - Math.abs(scoreDelta) / scoreRange);
            fx = parentX + factor * SMALL_STEP;
          }
        }
      }

      const kids = children.get(nodeId) || [];
      const currentScore = nodeId === ARTIFACT_ID ? null : (runById.get(nodeId)?.score ?? null);

      if (kids.length === 0) {
        const fy = leafSlot * GAP_Y;
        leafSlot++;
        posMap.set(nodeId, { fx, fy });
        return fy;
      }
      const childYs = kids.map((kid) => layout(kid, fx, currentScore));
      const fy = (childYs[0] + childYs[childYs.length - 1]) / 2;
      posMap.set(nodeId, { fx, fy });
      return fy;
    }
    layout(ARTIFACT_ID, 0, null);

    // Center around y=0
    const allYs = [...posMap.values()].map((p) => p.fy);
    const midY = (Math.min(...allYs) + Math.max(...allYs)) / 2;
    for (const pos of posMap.values()) pos.fy -= midY;

    // Create artifact node
    const artifactRun: Run = {
      id: ARTIFACT_ID,
      task_id: runs[0]?.task_id ?? "",
      agent_id: "shared artifact",
      branch: "", parent_id: null,
      tldr: "Shared starting artifact", message: "",
      score: null, verified: false,
      created_at: runs.length > 0
        ? runs.reduce((e, r) => r.created_at < e ? r.created_at : e, runs[0].created_at)
        : new Date().toISOString(),
    };
    const originPos = posMap.get(ARTIFACT_ID) || { fx: 0, fy: 0 };
    const artifactNode: GraphNode = {
      id: ARTIFACT_ID, run: artifactRun, isArtifact: true,
      inLineage: false, color: "#60a5fa",
      fx: originPos.fx, fy: originPos.fy,
    };
    nodeMap.set(ARTIFACT_ID, artifactNode);

    // Create run nodes
    for (const run of runs) {
      const pos = posMap.get(run.id);
      nodeMap.set(run.id, {
        id: run.id, run, isArtifact: false,
        inLineage: bestLineage.has(run.id),
        color: getAgentColor(run.agent_id),
        fx: pos?.fx, fy: pos?.fy,
      });
    }

    // Build links
    const rootIds = children.get(ARTIFACT_ID) || [];
    for (const rootId of rootIds) {
      links.push({
        source: ARTIFACT_ID, target: rootId,
        inLineage: false, isFromArtifact: true,
        siblingCount: rootIds.length,
        declined: false,
      });
    }
    for (const run of runs) {
      if (!run.parent_id) continue;
      const parentFullId = resolveId(run.parent_id, runIds.values());
      if (parentFullId && runIds.has(parentFullId)) {
        const inLineage = bestChains.some((c) => c.has(parentFullId) && c.has(run.id));
        const siblings = (children.get(parentFullId) || []).length;
        const parentRun = runById.get(parentFullId);
        const declined = run.score !== null && parentRun?.score !== null && parentRun?.score !== undefined && run.score < parentRun.score;
        links.push({
          source: parentFullId, target: run.id,
          inLineage, isFromArtifact: false,
          siblingCount: siblings,
          declined,
        });
      }
    }

    return { nodes: [...nodeMap.values()], links };
  }, [runs, bestLineage, bestChains]);


  // Keep render loop alive for edge pulse animation (only when tab is visible)
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (!interval) interval = setInterval(() => { fgRef.current?.d3ReheatSimulation(); }, 3000);
    };
    const stop = () => { if (interval) { clearInterval(interval); interval = null; } };
    const onVisibility = () => document.hidden ? stop() : start();
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) start();
    return () => { stop(); document.removeEventListener("visibilitychange", onVisibility); };
  }, []);

  // Fit graph: seed on left, rightmost node on right, centered
  const fitGraph = useCallback(() => {
    const fg = fgRef.current;
    if (!fg || graphData.nodes.length === 0) return;

    // Use fx/fy from our node data (already computed, no need to wait for simulation)
    const xs = graphData.nodes.filter((n) => n.fx != null).map((n) => n.fx!);
    const ys = graphData.nodes.filter((n) => n.fy != null).map((n) => n.fy!);
    if (xs.length === 0 || ys.length === 0) return;

    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const graphW = maxX - minX || 1;
    const graphH = maxY - minY || 1;
    const pad = 60;

    const scaleX = (dimensions.width - pad * 2) / graphW;
    const scaleY = (dimensions.height - pad * 2) / graphH;
    const zoom = Math.min(scaleX, scaleY);

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    fg.zoom(zoom, 0);
    fg.centerAt(centerX, centerY, 0);
    setReady(true);
  }, [graphData, dimensions]);

  // Run fit on mount — retry until ref is available
  useEffect(() => {
    let attempts = 0;
    const tryFit = () => {
      if (fgRef.current) {
        fitGraph();
      } else if (attempts < 20) {
        attempts++;
        setTimeout(tryFit, 50);
      }
    };
    tryFit();
  }, [fitGraph]);

  // Resolve CSS vars for canvas rendering
  const cssVars = useMemo(() => {
    if (typeof document === "undefined") return { surface: "#ffffff", bg: "#fafbfc", border: "#e5e7eb", layer3: "#d1d5db", text: "#111827", textTertiary: "#6b7280", accent: "#3f72af", muted: "#94a3b8", artifactBorder: "#cbd5e1" };
    const s = getComputedStyle(document.documentElement);
    const g = (v: string) => s.getPropertyValue(v).trim();
    return {
      surface: g("--color-surface") || "#ffffff",
      bg: g("--color-bg") || "#fafbfc",
      border: g("--color-border") || "#e5e7eb",
      layer3: g("--color-layer-3") || "#d1d5db",
      text: g("--color-text") || "#111827",
      textTertiary: g("--color-text-tertiary") || "#6b7280",
      accent: g("--color-accent") || "#3f72af",
      muted: g("--color-text-secondary") || "#94a3b8",
      artifactBorder: g("--color-border-light") || "#cbd5e1",
    };
  }, []);

  // Custom node rendering on Canvas
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const gn = node as GraphNode;
    const x = node.x as number;
    const y = node.y as number;

    if (gn.isArtifact) {
      // Seed: larger gray square, no border
      const size = 16;
      const half = size / 2;
      ctx.save();
      ctx.fillStyle = cssVars.layer3;
      ctx.beginPath();
      ctx.roundRect(x - half, y - half, size, size, 3);
      ctx.fill();
      ctx.restore();
      return;
    }

    // Regular nodes: small glowing squares
    const size = gn.inLineage ? 7 : 5;
    const half = size / 2;

    ctx.save();
    ctx.fillStyle = gn.inLineage ? gn.color : gn.color + "cc";
    ctx.strokeStyle = gn.inLineage ? gn.color : gn.color + "80";
    ctx.lineWidth = gn.inLineage ? 1.5 : 0.8;

    // Rounded rect
    const rx = 1.5;
    ctx.beginPath();
    ctx.moveTo(x - half + rx, y - half);
    ctx.lineTo(x + half - rx, y - half);
    ctx.quadraticCurveTo(x + half, y - half, x + half, y - half + rx);
    ctx.lineTo(x + half, y + half - rx);
    ctx.quadraticCurveTo(x + half, y + half, x + half - rx, y + half);
    ctx.lineTo(x - half + rx, y + half);
    ctx.quadraticCurveTo(x - half, y + half, x - half, y + half - rx);
    ctx.lineTo(x - half, y - half + rx);
    ctx.quadraticCurveTo(x - half, y - half, x - half + rx, y - half);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  }, [cssVars]);

  // Custom link rendering on Canvas
  const paintLink = useCallback((link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const gl = link as GraphLink;
    const src = link.source;
    const tgt = link.target;
    if (!src || !tgt || src.x == null || tgt.x == null) return;

    const x1 = src.x as number;
    const y1 = src.y as number;
    const x2 = tgt.x as number;
    const y2 = tgt.y as number;

    ctx.save();

    // Edge thickness scales with sibling count (more branches = thicker trunk)
    const baseWidth = Math.min(0.6 + gl.siblingCount * 0.5, 4);

    if (gl.isFromArtifact) {
      ctx.strokeStyle = cssVars.artifactBorder;
      ctx.lineWidth = Math.min(0.5 + gl.siblingCount * 0.3, 3);
      ctx.globalAlpha = 0.6;
      ctx.setLineDash([3, 2]);
    } else if (gl.inLineage) {
      const mx = (x1 + x2) / 2;
      const lineageColor = gl.declined ? "#b9605a" : cssVars.accent;

      // Base stroke — solid, subtle
      ctx.strokeStyle = lineageColor;
      ctx.lineWidth = baseWidth + 0.5;
      ctx.globalAlpha = 0.25;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.bezierCurveTo(mx, y1, mx, y2, x2, y2);
      ctx.stroke();

      // Traveling glow pulse — sample a bright segment along the curve
      const t = ((Date.now() / 1500) % 1); // 0→1 over 1.5s
      const pulseLen = 0.18; // length of bright segment

      // Cubic bezier point helper
      const bx = (t: number) => {
        const mt = 1 - t;
        return mt*mt*mt*x1 + 3*mt*mt*t*mx + 3*mt*t*t*mx + t*t*t*x2;
      };
      const by = (t: number) => {
        const mt = 1 - t;
        return mt*mt*mt*y1 + 3*mt*mt*t*y1 + 3*mt*t*t*y2 + t*t*t*y2;
      };

      // Draw bright segment from t to t+pulseLen
      const steps = 12;
      const tStart = t;
      const tEnd = Math.min(t + pulseLen, 1);
      for (let i = 0; i < steps; i++) {
        const segT = tStart + (tEnd - tStart) * (i / steps);
        const segT2 = tStart + (tEnd - tStart) * ((i + 1) / steps);
        if (segT > 1 || segT2 > 1) break;
        // Fade in at front, fade out at back
        const localT = i / steps;
        const alpha = Math.sin(localT * Math.PI) * 0.7;
        ctx.strokeStyle = lineageColor;
        ctx.lineWidth = baseWidth + 1.5 * Math.sin(localT * Math.PI);
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.moveTo(bx(segT), by(segT));
        ctx.lineTo(bx(segT2), by(segT2));
        ctx.stroke();
      }

      ctx.restore();
      return;
    } else {
      ctx.strokeStyle = gl.declined ? "#c27070" : cssVars.muted;
      ctx.lineWidth = baseWidth;
      ctx.globalAlpha = 0.3 + Math.min(gl.siblingCount * 0.05, 0.2);
    }

    // Smooth horizontal Bezier — control points at midpoint x
    const mx = (x1 + x2) / 2;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.bezierCurveTo(mx, y1, mx, y2, x2, y2);
    ctx.stroke();
    ctx.restore();
  }, [cssVars]);

  const handleNodeHover = useCallback((node: any) => {
    if (node && !(node as GraphNode).isArtifact) {
      setCursorStyle("pointer");
    } else {
      setCursorStyle("grab");
    }
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    const gn = node as GraphNode;
    if (gn.isArtifact) return;
    onRunClick?.(gn.run);
  }, [onRunClick]);

  return (
    <div ref={containerRef} className="h-full w-full relative bg-[var(--color-surface)] rounded-lg overflow-hidden" style={{ cursor: cursorStyle, opacity: ready ? 1 : 0 }}>
      {dimensions.width > 0 && (
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="transparent"
          nodeCanvasObject={paintNode}
          nodeCanvasObjectMode={() => "replace"}
          linkCanvasObject={paintLink}
          linkCanvasObjectMode={() => "replace"}
          nodeVal={(node: any) => (node as GraphNode).isArtifact ? 8 : (node as GraphNode).inLineage ? 5 : 3}
          nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
            const r = 12;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fill();
          }}
          nodeLabel={(node: any) => {
            const gn = node as GraphNode;
            if (gn.isArtifact) return "";
            const scoreHtml = gn.run.score !== null
              ? `<div style="font-family:'IBM Plex Mono',monospace;font-size:18px;font-weight:700;color:var(--color-text)">${gn.run.score.toFixed(3)}</div>`
              : "";
            return `<div style="font-family:'DM Sans',sans-serif;background:var(--color-surface);padding:12px;border-radius:12px;border:1px solid var(--color-border);box-shadow:0 1px 3px rgba(0,0,0,0.06),0 1px 2px rgba(0,0,0,0.04);max-width:280px;width:max-content;line-height:1.5">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <div style="width:10px;height:10px;border-radius:50%;flex-shrink:0;background:${gn.color}"></div>
                <span style="font-size:14px;font-weight:600;color:var(--color-text)">${gn.run.agent_id}</span>
                <span style="font-size:11px;color:var(--color-text-tertiary)">${timeAgo(gn.run.created_at)}</span>
              </div>
              ${scoreHtml}
              <div style="font-size:12px;color:var(--color-text-tertiary);margin-top:2px">${gn.run.tldr}</div>
            </div>`;
          }}
          onNodeClick={handleNodeClick}
          onNodeHover={handleNodeHover}
          cooldownTicks={Infinity}
          warmupTicks={100}
          d3AlphaDecay={0.03}
          d3AlphaMin={0}
          enableNodeDrag={false}
          minZoom={0.05}
          maxZoom={5}
        />
      )}

    </div>
  );
}
