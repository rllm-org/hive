"use client";

import { useState, useEffect, useRef } from "react";
import { TextShimmer } from "@/components/text-shimmer";

export function ThinkingBlock({ content, active }: { content: string; active: boolean }) {
  const [manualToggle, setManualToggle] = useState<boolean | null>(null);
  const startRef = useRef<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (active && startRef.current === null) {
      startRef.current = Date.now();
    }
    if (!active && startRef.current !== null) {
      setElapsed(Math.round((Date.now() - startRef.current) / 1000));
      startRef.current = null;
    }
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => {
      if (startRef.current) setElapsed(Math.round((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [active]);

  useEffect(() => {
    if (active && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [active, content]);

  const isOpen = manualToggle ?? active;
  const label = active ? "Thinking" : elapsed > 0 ? `Thought for ${elapsed}s` : "Thought";

  return (
    <div className="group/th">
      <button
        type="button"
        onClick={() => setManualToggle(isOpen ? false : true)}
        className="flex items-center gap-1.5 text-sm text-[var(--color-text-tertiary)] cursor-pointer hover:text-[var(--color-text-secondary)]"
      >
        {active ? <TextShimmer className="text-sm [--base-color:var(--color-text-tertiary)] [--base-gradient-color:var(--color-text)]" duration={2}>{label}</TextShimmer> : <span>{label}</span>}
        <svg className={`w-3 h-3 transition-all opacity-0 group-hover/th:opacity-100 ${isOpen ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {isOpen && (
        <div ref={contentRef} className="mt-1 whitespace-pre-wrap text-sm leading-relaxed max-h-60 overflow-y-auto text-[var(--color-text-tertiary)]">
          {content}
        </div>
      )}
    </div>
  );
}
