"use client";

import { Run } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";

interface RunDetailProps {
  run: Run;
  onClose: () => void;
}

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function RunDetail({ run, onClose }: RunDetailProps) {
  const color = getAgentColor(run.agent_id);

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm" style={{ zIndex: 9999 }} onClick={onClose}>
      <div className="bg-[var(--bg-card)] border border-[#d8d0c0] border-l-[3px] border-l-[var(--accent-red)] max-w-lg w-full mx-4 pt-5 animate-fade-in"
        style={{ transform: "rotate(-0.5deg)", boxShadow: "2px 3px 12px rgba(0,0,0,0.25)" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="p-6">
          <div className="flex items-start justify-between mb-5">
            <div>
              <div className="flex items-center gap-2.5 mb-1">
                <span className="agent-name text-[24px]">{run.agent_id}</span>
              </div>
              <div className="text-[11px] text-[var(--text-dim)] font-[family-name:var(--font-typewriter)]">{run.id}</div>
            </div>
            <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-[#ebe8e0] text-[var(--text-dim)] hover:text-[var(--text-dark)] transition-colors">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3l8 8M11 3l-8 8"/></svg>
            </button>
          </div>
          <div className="text-5xl text-[var(--text-dark)] mb-6 font-[family-name:var(--font-typewriter)] font-bold tracking-tighter">
            {run.score?.toFixed(3) ?? "—"}
          </div>
          <div className="space-y-4 text-sm">
            <div>
              <div className="font-[family-name:var(--font-stamp)] text-[9px] tracking-[0.2em] text-[var(--accent-dark-red)] uppercase mb-1">TLDR</div>
              <div className="font-[family-name:var(--font-typewriter)] text-[var(--text-dark)] leading-[1.8]">{run.tldr}</div>
            </div>
            <div>
              <div className="font-[family-name:var(--font-stamp)] text-[9px] tracking-[0.2em] text-[var(--accent-dark-red)] uppercase mb-1">Message</div>
              <div className="font-[family-name:var(--font-typewriter)] text-[var(--text-dim)] leading-[1.8] whitespace-pre-wrap">{run.message}</div>
            </div>
            <div className="flex gap-8 pt-3 border-t border-dashed border-[#d8d0c0]">
              {[
                { l: "Branch", v: run.branch },
                { l: "Parent", v: run.parent_id?.slice(0, 7) ?? "root" },
                { l: "When", v: relativeTime(run.created_at) },
              ].map(({ l, v }) => (
                <div key={l}>
                  <div className="font-[family-name:var(--font-stamp)] text-[9px] tracking-[0.2em] text-[var(--accent-dark-red)] uppercase mb-0.5">{l}</div>
                  <div className="text-[var(--text-dark)] font-[family-name:var(--font-typewriter)] text-[12px]">{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
