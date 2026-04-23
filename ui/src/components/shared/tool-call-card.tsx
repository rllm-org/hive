"use client";

import { useState } from "react";
import { TextShimmer } from "@/components/text-shimmer";
import type { MessagePart } from "@/hooks/use-workspace-agent";

type ToolPart = Extract<MessagePart, { type: "tool" }>;

export function ToolCallCard({ part, active }: { part: ToolPart; active?: boolean }) {
  const [open, setOpen] = useState(false);
  const hasDetails = part.input != null || part.output != null;

  const formatValue = (v: unknown): string => {
    if (v == null) return "";
    if (typeof v === "string") return v;
    try { return JSON.stringify(v, null, 2); } catch { return String(v); }
  };

  return (
    <div className="not-prose border border-[var(--color-border)] bg-[var(--color-surface)] text-xs" style={{ borderRadius: 8 }}>
      <button
        type="button"
        onClick={() => hasDetails && setOpen(!open)}
        className={`group/tc w-full flex items-center gap-2 px-3 py-1.5 text-left ${hasDetails ? "cursor-pointer hover:bg-[var(--color-layer-1)]" : "cursor-default"}`}
        style={{ borderRadius: open ? "8px 8px 0 0" : 8 }}
      >
        <svg className="w-3.5 h-3.5 shrink-0 text-[var(--color-text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
          {part.name === "Bash" ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          )}
        </svg>
        {(part.status === "pending" || active) ? (
          <TextShimmer className="text-xs [--base-color:var(--color-text-tertiary)] [--base-gradient-color:var(--color-text)]" duration={1.5}>{part.title || part.name || "Running…"}</TextShimmer>
        ) : (
          <span className="truncate text-[var(--color-text-secondary)]">{part.title || part.name}</span>
        )}
        {part.status === "error" && <span className="text-red-500 shrink-0">failed</span>}
        {hasDetails && (
          <svg className={`ml-auto w-3 h-3 shrink-0 text-[var(--color-text-tertiary)] transition-all ${open ? "rotate-180 opacity-100" : "opacity-0 group-hover/tc:opacity-100"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>
      {open && (
        <div className="border-t border-[var(--color-border)] px-3 py-2 space-y-2">
          {part.input != null && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)] mb-0.5">input</div>
              <pre className="whitespace-pre-wrap break-all font-[family-name:var(--font-ibm-plex-mono)] text-[11px] leading-snug max-h-40 overflow-y-auto text-[var(--color-text)]">
                {formatValue(part.input)}
              </pre>
            </div>
          )}
          {part.output != null && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)] mb-0.5">output</div>
              <pre className="whitespace-pre-wrap break-all font-[family-name:var(--font-ibm-plex-mono)] text-[11px] leading-snug max-h-40 overflow-y-auto text-[var(--color-text)]">
                {formatValue(part.output)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
