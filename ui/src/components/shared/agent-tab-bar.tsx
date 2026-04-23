"use client";

import { useState, useEffect, useRef } from "react";
import BoringAvatar from "boring-avatars";

const AVATAR_COLORS = ["#92A1C6", "#146A7C", "#F0AB3D", "#C271B4", "#C20D90"];

export interface AgentTabInfo {
  id: string;
  avatar_seed?: string | null;
}

interface AgentTabBarProps {
  agents: AgentTabInfo[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onClose?: (id: string) => Promise<void>;
}

function AgentAvatar({ seed, id, size = 16 }: { seed?: string | null; id: string; size?: number }) {
  return (
    <div className="overflow-hidden shrink-0" style={{ width: size, height: size, borderRadius: 4 }}>
      <BoringAvatar name={seed || id} variant="beam" size={size} square colors={AVATAR_COLORS} />
    </div>
  );
}

export function AgentTabBar({ agents, activeId, onSelect, onClose }: AgentTabBarProps) {
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  return (
    <>
      <div className="shrink-0 flex items-end gap-0 px-3 pt-2 relative overflow-x-auto" style={{ marginBottom: -1 }}>
        {agents.map((a) => {
          const active = a.id === activeId;
          return (
            <div
              key={a.id}
              onClick={() => onSelect(a.id)}
              className={`group flex items-center gap-1.5 pl-2.5 pr-1.5 py-1.5 text-[12px] font-medium cursor-pointer transition-colors ${
                active
                  ? "bg-[var(--color-layer-1)] text-[var(--color-text)] border border-[var(--color-border)] border-b-transparent z-10"
                  : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)] opacity-60 hover:opacity-100 border border-transparent"
              }`}
              style={{ borderRadius: "6px 6px 0 0" }}
            >
              <AgentAvatar seed={a.avatar_seed} id={a.id} />
              <span className="truncate max-w-[120px]">{a.id}</span>
              {onClose && (
                <button
                  onClick={(e) => { e.stopPropagation(); setPendingDelete(a.id); }}
                  className={`w-4 h-4 ml-0.5 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all ${
                    active ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                  }`}
                  style={{ borderRadius: 3 }}
                  aria-label={`Close ${a.id}`}
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M2 2l6 6M8 2l-6 6" />
                  </svg>
                </button>
              )}
            </div>
          );
        })}
      </div>
      {pendingDelete && onClose && (
        <DeleteAgentModal
          agentId={pendingDelete}
          onClose={() => setPendingDelete(null)}
          onConfirm={async () => {
            const id = pendingDelete;
            setPendingDelete(null);
            await onClose(id);
          }}
        />
      )}
    </>
  );
}

function DeleteAgentModal({
  agentId,
  onClose,
  onConfirm,
}: {
  agentId: string;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const submit = async () => {
    setSubmitting(true);
    try { await onConfirm(); } finally { setSubmitting(false); }
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[420px] flex flex-col animate-fade-in" style={{ borderRadius: 6 }}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-base font-semibold text-[var(--color-text)]">Delete Agent</h2>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>
        <div className="px-6 py-5 space-y-3">
          <p className="text-sm text-[var(--color-text-secondary)]">
            Delete agent <span className="font-semibold text-[var(--color-text)] font-[family-name:var(--font-ibm-plex-mono)]">{agentId}</span>?
          </p>
          <p className="text-xs text-[var(--color-text-tertiary)]">
            This will tear down the agent&apos;s sandbox and remove its chat history. If the agent has public runs, its profile will be kept but unlinked.
          </p>
          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 transition-colors"
            >
              {submitting ? "Deleting…" : "Delete"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
