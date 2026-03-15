"use client";

import { useMemo } from "react";
import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";

interface EvolutionTreeProps {
  runs: Run[];
  onRunClick?: (run: Run) => void;
}

interface TreeNode {
  run: Run;
  children: TreeNode[];
  x: number;
  y: number;
}

const NODE_W = 220;
const NODE_H = 68;
const GAP_X = 28;
const GAP_Y = 56;

function buildTree(runs: Run[]): TreeNode[] {
  const map = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];
  for (const run of runs) map.set(run.id, { run, children: [], x: 0, y: 0 });
  for (const run of runs) {
    const node = map.get(run.id)!;
    if (run.parent_id && map.has(run.parent_id)) map.get(run.parent_id)!.children.push(node);
    else roots.push(node);
  }
  for (const node of map.values()) {
    node.children.sort((a, b) => new Date(a.run.created_at).getTime() - new Date(b.run.created_at).getTime());
  }
  return roots;
}

/** Top-to-bottom layout: x = horizontal position, y = depth */
function layoutTree(roots: TreeNode[]): { nodes: TreeNode[]; width: number; height: number } {
  const allNodes: TreeNode[] = [];
  let currentX = 0;

  function layout(node: TreeNode, depth: number) {
    node.y = depth * (NODE_H + GAP_Y);

    if (node.children.length === 0) {
      node.x = currentX;
      currentX += NODE_W + GAP_X;
      allNodes.push(node);
      return;
    }

    for (const child of node.children) {
      layout(child, depth + 1);
    }

    const firstChild = node.children[0];
    const lastChild = node.children[node.children.length - 1];
    node.x = (firstChild.x + lastChild.x) / 2;
    allNodes.push(node);
  }

  for (const root of roots) layout(root, 0);

  const maxX = currentX;
  const maxY = Math.max(...allNodes.map((n) => n.y)) + NODE_H;
  return { nodes: allNodes, width: maxX + 20, height: maxY + 20 };
}

function getEdges(roots: TreeNode[]): { parent: TreeNode; child: TreeNode }[] {
  const edges: { parent: TreeNode; child: TreeNode }[] = [];
  function walk(node: TreeNode) { for (const c of node.children) { edges.push({ parent: node, child: c }); walk(c); } }
  for (const r of roots) walk(r);
  return edges;
}

export function EvolutionTree({ runs, onRunClick }: EvolutionTreeProps) {
  const { nodes, edges, width, height } = useMemo(() => {
    const roots = buildTree(runs);
    const layout = layoutTree(roots);
    return { ...layout, edges: getEdges(roots) };
  }, [runs]);

  return (
    <div className="overflow-x-auto overflow-y-auto h-full w-full flex items-start justify-center">
      <svg width={width} height={height}>
        <g transform="translate(10, 10)">
          {/* Edges */}
          {edges.map((e, i) => {
            const x1 = e.parent.x + NODE_W / 2;
            const y1 = e.parent.y + NODE_H;
            const x2 = e.child.x + NODE_W / 2;
            const y2 = e.child.y;
            const my = (y1 + y2) / 2;
            return (
              <path key={i} d={`M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`}
                fill="none" stroke="#d8d0c0" strokeWidth={1.5} />
            );
          })}

          {/* Nodes */}
          {nodes.map((node) => {
            const color = getAgentColor(node.run.agent_id);
            return (
              <g key={node.run.id} transform={`translate(${node.x}, ${node.y})`}
                onClick={() => onRunClick?.(node.run)} className="cursor-pointer">
                <rect width={NODE_W} height={NODE_H} rx={3} fill="#faf3e6" stroke="#d8d0c0" strokeWidth={1} />
                {/* Red left accent */}
                <rect x={0} y={0} width={3} height={NODE_H} rx={1.5} fill="#cc3333" />
                <text x={NODE_W / 2} y={24} fill="#222222" fontSize={12} fontFamily="'Special Elite', monospace" textAnchor="middle">
                  {node.run.tldr.length > 24 ? node.run.tldr.slice(0, 24) + "..." : node.run.tldr}
                </text>
                <text x={NODE_W / 2} y={44} fill="#222222" fontSize={16} fontFamily="'Caveat', cursive" fontWeight={600} textAnchor="middle">
                  {node.run.agent_id}
                </text>
                {node.run.score !== null && (
                  <text x={NODE_W / 2} y={61} fill="#8b7355" fontSize={10} fontFamily="'Special Elite', monospace" textAnchor="middle">
                    {node.run.score.toFixed(3)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
