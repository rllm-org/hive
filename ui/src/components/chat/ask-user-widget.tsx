"use client";

import { useState } from "react";

export interface AskUserData {
  question: string;
  options?: string[];
  mode?: "select" | "confirm" | "multi_select" | "text";
  answered?: boolean;
  answer?: string | string[];
}

interface Props {
  questions: AskUserData[];
  onAnswered?: (questionIdx: number, answer: string | string[]) => void;
  onSendMessage?: (text: string) => void;
}

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

function SingleQuestion({
  data,
  onAnswered,
  onSendMessage,
}: {
  data: AskUserData;
  onAnswered?: (answer: string | string[]) => void;
  onSendMessage?: (text: string) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [multiSelected, setMultiSelected] = useState<Set<string>>(new Set());
  const [textInput, setTextInput] = useState("");
  const [otherText, setOtherText] = useState("");
  const [answered, setAnswered] = useState(data.answered ?? false);
  const [displayAnswer, setDisplayAnswer] = useState<string | string[] | null>(
    data.answer ?? null
  );

  const submit = (answer: string | string[]) => {
    const text = Array.isArray(answer) ? answer.join(", ") : String(answer);
    onSendMessage?.(text);
    setAnswered(true);
    setDisplayAnswer(answer);
    onAnswered?.(answer);
  };

  // Answered state
  if (answered && displayAnswer != null) {
    const display = Array.isArray(displayAnswer)
      ? displayAnswer.join(", ")
      : String(displayAnswer);
    return (
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-[var(--color-text)]">{data.question}</p>
        <div className="flex items-center gap-2 px-3 py-2 bg-[var(--color-accent-50)] border border-[var(--color-accent)] text-sm text-[var(--color-text)]" style={{ borderRadius: 8 }}>
          {display}
        </div>
      </div>
    );
  }

  // Confirm mode
  if (data.mode === "confirm") {
    return (
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-[var(--color-text)]">{data.question}</p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => submit("yes")}
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
            style={{ borderRadius: 6 }}
          >
            Yes
          </button>
          <button
            onClick={() => submit("no")}
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)] disabled:opacity-50 transition-colors"
            style={{ borderRadius: 6 }}
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
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-[var(--color-text)]">{data.question}</p>
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
            className="flex-1 px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)]"
            style={{ outline: "none", boxShadow: "none", borderRadius: 6 }}
          />
          <button
            onClick={() => submit(textInput.trim())}
            disabled={submitting || !textInput.trim()}
            className="px-4 py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
            style={{ borderRadius: 6 }}
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
      <div className="space-y-1.5">
        <p className="text-sm font-medium text-[var(--color-text)]">{data.question}</p>
        <div className="space-y-0.5">
          {data.options.map((opt, i) => {
            const isSelected = multiSelected.has(opt);
            return (
              <button
                key={opt}
                onClick={() => {
                  setMultiSelected((prev) => {
                    const next = new Set(prev);
                    if (next.has(opt)) next.delete(opt);
                    else next.add(opt);
                    return next;
                  });
                }}
                disabled={submitting}
                className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 text-sm text-left transition-colors ${
                  isSelected
                    ? "bg-[var(--color-accent-50)] border border-[var(--color-accent)]"
                    : "hover:bg-[var(--color-layer-1)] border border-transparent"
                }`}
                style={{ borderRadius: 8 }}
              >
                <span className={`inline-flex items-center justify-center w-5 h-5 text-xs font-medium shrink-0 ${
                  isSelected
                    ? "bg-[var(--color-accent)] text-white"
                    : "bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)]"
                }`} style={{ borderRadius: 6 }}>
                  {LETTERS[i] ?? i + 1}
                </span>
                <span className="text-[var(--color-text)]">{opt}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // Select mode (default) — lettered list like Cursor
  const isOtherOpt = (opt: string) => /^other/i.test(opt.replace(/[^a-zA-Z]/g, ""));
  const regularOptions = (data.options ?? []).filter((o) => !isOtherOpt(o));
  const hasOther = (data.options ?? []).some(isOtherOpt);
  const otherIdx = regularOptions.length;

  const handleSubmit = () => {
    if (selected === "__other__" && otherText.trim()) {
      submit(otherText.trim());
    } else if (selected && selected !== "__other__") {
      submit(selected);
    }
  };

  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium text-[var(--color-text)]">{data.question}</p>
      <div className="space-y-0.5">
        {regularOptions.map((opt, i) => {
          const isSelected = selected === opt;
          return (
            <button
              key={opt}
              onClick={() => submit(opt)}
              disabled={submitting}
              className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 text-sm text-left transition-colors ${
                isSelected
                  ? "bg-[var(--color-accent-50)] border border-[var(--color-accent)]"
                  : "hover:bg-[var(--color-layer-1)] border border-transparent"
              }`}
              style={{ borderRadius: 8 }}
            >
              <span className={`inline-flex items-center justify-center w-5 h-5 text-xs font-medium shrink-0 ${
                isSelected
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)]"
              }`} style={{ borderRadius: 6 }}>
                {LETTERS[i] ?? i + 1}
              </span>
              <span className="text-[var(--color-text)]">{opt}</span>
            </button>
          );
        })}
        {hasOther && (
          <div
            onClick={() => setSelected("__other__")}
            className={`flex items-center gap-2.5 px-2.5 py-1.5 text-sm cursor-text transition-colors ${
              selected === "__other__"
                ? "bg-[var(--color-accent-50)] border border-[var(--color-accent)]"
                : "border border-transparent"
            }`}
            style={{ borderRadius: 8 }}
          >
            <span className={`inline-flex items-center justify-center w-5 h-5 text-xs font-medium shrink-0 ${
              selected === "__other__"
                ? "bg-[var(--color-accent)] text-white"
                : "bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)]"
            }`} style={{ borderRadius: 6 }}>
              {LETTERS[otherIdx] ?? otherIdx + 1}
            </span>
            <input
              type="text"
              value={otherText}
              onChange={(e) => { setOtherText(e.target.value); setSelected("__other__"); }}
              onFocus={() => setSelected("__other__")}
              onKeyDown={(e) => { if (e.key === "Enter" && otherText.trim()) { e.preventDefault(); submit(otherText.trim()); } }}
              placeholder="Other..."
              className="flex-1 bg-transparent text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
              style={{ outline: "none", border: "none", padding: 0 }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function AskUserWidget({ questions, onAnswered, onSendMessage }: Props) {
  const [currentIdx, setCurrentIdx] = useState(0);
  const total = questions.length;
  const current = questions[currentIdx];

  if (!current) return null;

  // Single question — no pagination
  if (total === 1) {
    return (
      <div className="border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 space-y-2" style={{ borderRadius: 10 }}>
        <span className="text-xs font-medium text-[var(--color-text-tertiary)]">Questions</span>
        <SingleQuestion
          data={current}
          onAnswered={(answer) => onAnswered?.(0, answer)}
          onSendMessage={onSendMessage}
        />
      </div>
    );
  }

  // Multiple questions — paginated like Cursor
  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 space-y-4" style={{ borderRadius: 10 }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider">Questions</span>
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
          <button
            onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
            disabled={currentIdx === 0}
            className="w-5 h-5 flex items-center justify-center hover:text-[var(--color-text)] disabled:opacity-30 transition-colors"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M6 2L3 5l3 3" />
            </svg>
          </button>
          <span>{currentIdx + 1} of {total}</span>
          <button
            onClick={() => setCurrentIdx((i) => Math.min(total - 1, i + 1))}
            disabled={currentIdx === total - 1}
            className="w-5 h-5 flex items-center justify-center hover:text-[var(--color-text)] disabled:opacity-30 transition-colors"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 2l3 3-3 3" />
            </svg>
          </button>
        </div>
      </div>

      <SingleQuestion
        key={currentIdx}
        data={current}
        onSendMessage={onSendMessage}
        onAnswered={(answer) => {
          onAnswered?.(currentIdx, answer);
          if (currentIdx < total - 1) setCurrentIdx(currentIdx + 1);
        }}
      />

      <div className="flex items-center justify-end gap-3 pt-1">
        <button
          onClick={() => {
            if (currentIdx < total - 1) setCurrentIdx(currentIdx + 1);
          }}
          className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
        >
          Skip
        </button>
        <button
          onClick={() => {
            // Submit the selected answer for current question
            // The SingleQuestion handles its own submission
          }}
          className="px-4 py-1.5 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors flex items-center gap-1.5"
          style={{ borderRadius: 6 }}
        >
          Next
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M2 10L10 2M10 2H4M10 2v6" />
          </svg>
        </button>
      </div>
    </div>
  );
}
