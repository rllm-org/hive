"use client";

import { useEffect, useRef } from "react";
import type { Turn } from "@/hooks/use-agent-session";
import { ToolCallCard } from "./tool-call-card";

interface Props {
  turns: Turn[];
}

export function TurnStream({ turns }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns.length, turns[turns.length - 1]?.text.length]);

  if (turns.length === 0) {
    return (
      <div className="p-4 text-xs text-[var(--color-text-secondary)]">
        No messages yet — say something to get started.
      </div>
    );
  }
  return (
    <div className="p-3 space-y-3">
      {turns.map((t) => (
        <TurnView key={t.key} turn={t} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] px-3 py-2 bg-[var(--color-layer-2)] border border-[var(--color-border)] text-sm whitespace-pre-wrap">
          {turn.text}
        </div>
      </div>
    );
  }
  if (turn.role === "error") {
    return (
      <div className="px-3 py-2 text-sm text-red-500 border border-red-500/40 bg-red-500/5 whitespace-pre-wrap">
        {turn.text}
      </div>
    );
  }
  // assistant
  return (
    <div className="space-y-2">
      {turn.reasoning && (
        <details className="text-xs text-[var(--color-text-secondary)]">
          <summary className="cursor-pointer select-none">Reasoning</summary>
          <div className="mt-1 whitespace-pre-wrap pl-2 border-l border-[var(--color-border)]">
            {turn.reasoning}
          </div>
        </details>
      )}
      {turn.toolCalls.length > 0 && (
        <div className="space-y-1">
          {turn.toolCalls.map((tc) => <ToolCallCard key={tc.id} call={tc} />)}
        </div>
      )}
      {(turn.text || turn.streaming) && (
        <div className="text-sm whitespace-pre-wrap">
          {turn.text}
          {turn.streaming && <span className="inline-block w-2 h-4 ml-0.5 bg-[var(--color-text)] animate-pulse" />}
        </div>
      )}
      {turn.stopReason && turn.stopReason !== "end_turn" && (
        <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">
          stop: {turn.stopReason}
        </div>
      )}
    </div>
  );
}
