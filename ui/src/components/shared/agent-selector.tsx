"use client";

import { useState, useRef, useEffect } from "react";
import BoringAvatar from "boring-avatars";

const AVATAR_COLORS = ["#92A1C6", "#146A7C", "#F0AB3D", "#C271B4", "#C20D90"];

export interface AgentOption {
  id: string;
  avatar_seed?: string | null;
}

interface AgentSelectorProps {
  agents: AgentOption[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

function AgentAvatar({ seed, id, size = 18 }: { seed?: string | null; id: string; size?: number }) {
  return (
    <div className="overflow-hidden shrink-0" style={{ width: size, height: size, borderRadius: 4 }}>
      <BoringAvatar name={seed || id} variant="beam" size={size} square colors={AVATAR_COLORS} />
    </div>
  );
}

export function AgentSelector({ agents, activeId, onSelect }: AgentSelectorProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = agents.find((a) => a.id === activeId) ?? agents[0];

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  if (!active) return null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 text-[13px] font-medium text-[var(--color-text)] hover:bg-[var(--color-layer-1)] rounded-md transition-colors"
      >
        <AgentAvatar seed={active.avatar_seed} id={active.id} />
        <span className="truncate max-w-[180px]">{active.id}</span>
        <svg
          className={`w-3 h-3 text-[var(--color-text-tertiary)] transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 bg-[var(--color-surface)] border border-[var(--color-border)] shadow-[var(--shadow-elevated)] py-1 min-w-[200px]" style={{ borderRadius: 6 }}>
          {agents.map((a) => (
            <button
              key={a.id}
              onClick={() => { onSelect(a.id); setOpen(false); }}
              className={`w-full flex items-center gap-2 px-3 py-2 text-[13px] text-left transition-colors ${
                a.id === activeId
                  ? "bg-[var(--color-layer-1)] text-[var(--color-text)] font-medium"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-1)] hover:text-[var(--color-text)]"
              }`}
            >
              <AgentAvatar seed={a.avatar_seed} id={a.id} />
              <span className="truncate">{a.id}</span>
              {a.id === activeId && (
                <svg className="ml-auto w-3.5 h-3.5 text-[var(--color-accent)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
