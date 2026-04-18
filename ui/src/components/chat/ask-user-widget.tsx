"use client";

import { useState } from "react";
import { apiPostJson } from "@/lib/api";
import type { AskUserData } from "@/hooks/use-workspace-agent";

interface Props {
  data: AskUserData;
  onAnswered?: (answer: string | string[]) => void;
}

export function AskUserWidget({ data, onAnswered }: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [textInput, setTextInput] = useState("");
  const [answered, setAnswered] = useState(data.answered ?? false);
  const [displayAnswer, setDisplayAnswer] = useState<string | string[] | null>(
    data.answer ?? null
  );

  const submit = async (answer: string | string[]) => {
    setSubmitting(true);
    try {
      await apiPostJson(`/mcp/questions/${data.questionId}/answer`, { answer });
      setAnswered(true);
      setDisplayAnswer(answer);
      onAnswered?.(answer);
    } catch {
      // Allow retry on failure
    } finally {
      setSubmitting(false);
    }
  };

  if (answered && displayAnswer != null) {
    const display = Array.isArray(displayAnswer)
      ? displayAnswer.join(", ")
      : String(displayAnswer);
    return (
      <div className="border border-[var(--color-border)] bg-[var(--color-layer-1)] px-3 py-2.5 space-y-1">
        <p className="text-sm text-[var(--color-text-secondary)]">{data.question}</p>
        <p className="text-sm font-medium text-[var(--color-text)]">{display}</p>
      </div>
    );
  }

  // Confirm mode
  if (data.mode === "confirm") {
    return (
      <div className="border border-[var(--color-border)] bg-[var(--color-layer-1)] px-3 py-2.5 space-y-2.5">
        <p className="text-sm text-[var(--color-text)]">{data.question}</p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => submit("yes")}
            disabled={submitting}
            className="px-3 py-1.5 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
          >
            Yes
          </button>
          <button
            onClick={() => submit("no")}
            disabled={submitting}
            className="px-3 py-1.5 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)] disabled:opacity-50 transition-colors"
          >
            No
          </button>
        </div>
      </div>
    );
  }

  // Text mode
  if (data.mode === "text" || (!data.options?.length && data.mode !== "multi_select")) {
    return (
      <div className="border border-[var(--color-border)] bg-[var(--color-layer-1)] px-3 py-2.5 space-y-2.5">
        <p className="text-sm text-[var(--color-text)]">{data.question}</p>
        <div className="flex items-end gap-2">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && textInput.trim()) {
                e.preventDefault();
                submit(textInput.trim());
              }
            }}
            placeholder="Type your answer…"
            className="flex-1 px-2.5 py-1.5 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)]"
            style={{ outline: "none", boxShadow: "none" }}
          />
          <button
            onClick={() => submit(textInput.trim())}
            disabled={submitting || !textInput.trim()}
            className="px-3 py-1.5 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    );
  }

  // Multi-select mode
  if (data.mode === "multi_select" && data.options) {
    return (
      <div className="border border-[var(--color-border)] bg-[var(--color-layer-1)] px-3 py-2.5 space-y-2">
        <p className="text-sm text-[var(--color-text)]">{data.question}</p>
        <div className="space-y-1">
          {data.options.map((opt) => (
            <label
              key={opt}
              className="flex items-center gap-2 px-2 py-1.5 text-sm cursor-pointer hover:bg-[var(--color-layer-2)] transition-colors"
            >
              <input
                type="checkbox"
                checked={selected.has(opt)}
                onChange={() => {
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (next.has(opt)) next.delete(opt);
                    else next.add(opt);
                    return next;
                  });
                }}
                className="accent-[var(--color-accent)]"
              />
              <span className="text-[var(--color-text)]">{opt}</span>
            </label>
          ))}
        </div>
        <button
          onClick={() => submit([...selected])}
          disabled={submitting || selected.size === 0}
          className="px-3 py-1.5 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
        >
          Submit ({selected.size})
        </button>
      </div>
    );
  }

  // Select mode (default) — button group
  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-layer-1)] px-3 py-2.5 space-y-2">
      <p className="text-sm text-[var(--color-text)]">{data.question}</p>
      <div className="flex flex-wrap gap-1.5">
        {(data.options ?? []).map((opt) => (
          <button
            key={opt}
            onClick={() => submit(opt)}
            disabled={submitting}
            className="px-3 py-1.5 text-sm border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-accent)] hover:text-white hover:border-[var(--color-accent)] disabled:opacity-50 transition-colors"
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
}
