"use client";

import { useState } from "react";
import type { ToolCall } from "@/hooks/use-agent-session";

interface Props { call: ToolCall }

export function ToolCallCard({ call }: Props) {
  const [open, setOpen] = useState(false);
  const statusColor =
    call.status === "done" ? "text-emerald-500"
    : call.status === "error" ? "text-red-500"
    : "text-amber-500";

  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-layer-1)] text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-2 py-1 hover:bg-[var(--color-layer-2)] text-left"
      >
        <span className="flex items-center gap-2">
          <span className={statusColor}>●</span>
          <span className="font-medium">{call.name}</span>
        </span>
        <span className="text-[var(--color-text-secondary)]">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="px-2 py-1 border-t border-[var(--color-border)] space-y-2">
          <Block label="input" value={call.input} />
          {call.output != null && <Block label="output" value={call.output} />}
        </div>
      )}
    </div>
  );
}

function Block({ label, value }: { label: string; value: unknown }) {
  const text = typeof value === "string" ? value : safeStringify(value);
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)] mb-0.5">{label}</div>
      <pre className="whitespace-pre-wrap break-all font-mono text-[11px] leading-snug max-h-60 overflow-y-auto">
        {text}
      </pre>
    </div>
  );
}

function safeStringify(v: unknown): string {
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}
