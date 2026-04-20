"use client";

import { useState } from "react";

export interface AskUserData {
  question: string;
  options?: string[];
  mode?: "select" | "confirm" | "multi_select" | "text";
}

interface Props {
  questions: AskUserData[];
  onSubmitAll?: (answers: (string | string[])[]) => void;
}

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

function OptionButton({ label, index, isSelected, onClick }: { label: string; index: number; isSelected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
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
        {LETTERS[index] ?? index + 1}
      </span>
      <span className="text-[var(--color-text)]">{label}</span>
    </button>
  );
}

function QuestionView({
  data,
  answer,
  onAnswer,
}: {
  data: AskUserData;
  answer: string | string[] | null;
  onAnswer: (answer: string | string[]) => void;
}) {
  const [multiSelected, setMultiSelected] = useState<Set<string>>(
    () => new Set(Array.isArray(answer) ? answer : [])
  );
  const [textInput, setTextInput] = useState((typeof answer === "string" ? answer : "") ?? "");
  const [otherText, setOtherText] = useState("");
  const [otherActive, setOtherActive] = useState(false);

  // Confirm mode — A) Yes, B) No
  if (data.mode === "confirm") {
    return (
      <div className="space-y-1.5">
        <p className="text-sm text-[var(--color-text)]">{data.question}</p>
        <div className="space-y-0.5">
          <OptionButton label="Yes" index={0} isSelected={answer === "Yes"} onClick={() => onAnswer(answer === "Yes" ? "" : "Yes")} />
          <OptionButton label="No" index={1} isSelected={answer === "No"} onClick={() => onAnswer(answer === "No" ? "" : "No")} />
        </div>
      </div>
    );
  }

  // Text mode — plain text field
  if (data.mode === "text" || !data.options?.length) {
    return (
      <div className="space-y-1.5">
        <p className="text-sm text-[var(--color-text)]">{data.question}</p>
        <input
          type="text"
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && textInput.trim()) { e.preventDefault(); onAnswer(textInput.trim()); } }}
          onBlur={() => { if (textInput.trim()) onAnswer(textInput.trim()); }}
          placeholder="Type your answer…"
          className="w-full px-2.5 py-1.5 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-accent)] focus:bg-[var(--color-accent-50)]"
          style={{ outline: "none", boxShadow: "none", borderRadius: 8 }}
        />
      </div>
    );
  }

  // Multi-select mode
  if (data.mode === "multi_select") {
    const isOther = (opt: string) => /^other/i.test(opt.replace(/[^a-zA-Z]/g, ""));
    const regularOpts = (data.options ?? []).filter((o) => !isOther(o));
    const hasOtherOpt = (data.options ?? []).some(isOther);
    const otherI = regularOpts.length;
    return (
      <div className="space-y-1.5">
        <p className="text-sm text-[var(--color-text)]">{data.question}</p>
        <div className="space-y-0.5">
          {regularOpts.map((opt, i) => (
            <OptionButton
              key={opt}
              label={opt}
              index={i}
              isSelected={multiSelected.has(opt)}
              onClick={() => {
                const next = new Set(multiSelected);
                if (next.has(opt)) next.delete(opt); else next.add(opt);
                setMultiSelected(next);
                const allAnswers = [...next];
                if (otherText.trim()) allAnswers.push(otherText.trim());
                setTimeout(() => onAnswer(allAnswers), 0);
              }}
            />
          ))}
          {hasOtherOpt && (
            <div
              className={`flex items-center gap-2.5 px-2.5 py-1.5 text-sm transition-colors ${
                otherActive
                  ? "bg-[var(--color-accent-50)] border border-[var(--color-accent)]"
                  : "border border-transparent"
              }`}
              style={{ borderRadius: 8 }}
            >
              <span className={`inline-flex items-center justify-center w-5 h-5 text-xs font-medium shrink-0 ${
                otherActive
                  ? "bg-[var(--color-accent)] text-white"
                  : "bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)]"
              }`} style={{ borderRadius: 6 }}>
                {LETTERS[otherI] ?? otherI + 1}
              </span>
              <input
                type="text"
                value={otherText}
                onChange={(e) => {
                  setOtherText(e.target.value);
                  setOtherActive(!!e.target.value);
                  const allAnswers = [...multiSelected];
                  if (e.target.value.trim()) allAnswers.push(e.target.value.trim());
                  setTimeout(() => onAnswer(allAnswers), 0);
                }}
                onFocus={() => setOtherActive(true)}
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

  // Select mode (default)
  const isOtherOpt = (opt: string) => /^other/i.test(opt.replace(/[^a-zA-Z]/g, ""));
  const regularOptions = (data.options ?? []).filter((o) => !isOtherOpt(o));
  const hasOther = (data.options ?? []).some(isOtherOpt);
  const otherIdx = regularOptions.length;

  return (
    <div className="space-y-1.5">
      <p className="text-sm text-[var(--color-text)]">{data.question}</p>
      <div className="space-y-0.5">
        {regularOptions.map((opt, i) => (
          <OptionButton
            key={opt}
            label={opt}
            index={i}
            isSelected={answer === opt}
            onClick={() => { setOtherActive(false); onAnswer(answer === opt ? "" : opt); }}
          />
        ))}
        {hasOther && (
          <div
            onClick={() => setOtherActive(true)}
            className={`flex items-center gap-2.5 px-2.5 py-1.5 text-sm cursor-text transition-colors ${
              otherActive
                ? "bg-[var(--color-accent-50)] border border-[var(--color-accent)]"
                : "border border-transparent"
            }`}
            style={{ borderRadius: 8 }}
          >
            <span className={`inline-flex items-center justify-center w-5 h-5 text-xs font-medium shrink-0 ${
              otherActive
                ? "bg-[var(--color-accent)] text-white"
                : "bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)]"
            }`} style={{ borderRadius: 6 }}>
              {LETTERS[otherIdx] ?? otherIdx + 1}
            </span>
            <input
              type="text"
              value={otherText}
              onChange={(e) => { setOtherText(e.target.value); setOtherActive(true); }}
              onFocus={() => setOtherActive(true)}
              onKeyDown={(e) => { if (e.key === "Enter" && otherText.trim()) { e.preventDefault(); onAnswer(otherText.trim()); } }}
              onBlur={() => { if (otherText.trim()) onAnswer(otherText.trim()); }}
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

export function AskUserWidget({ questions, onSubmitAll }: Props) {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<(string | string[] | null)[]>(() => questions.map(() => null));
  const total = questions.length;
  const current = questions[currentIdx];
  const allAnswered = answers.every((a) => a !== null && (typeof a === "string" ? a.length > 0 : a.length > 0));
  const isLast = currentIdx === total - 1;

  if (!current) return null;

  const handleAnswer = (answer: string | string[]) => {
    const isEmpty = answer === "" || (Array.isArray(answer) && answer.length === 0);
    setAnswers((prev) => {
      const next = [...prev];
      next[currentIdx] = isEmpty ? null : answer;
      return next;
    });
    // Auto-advance for select/confirm only when selecting (not deselecting)
    if (!isEmpty && (current.mode === "select" || current.mode === "confirm" || !current.mode) && !isLast) {
      setTimeout(() => setCurrentIdx((i) => Math.min(total - 1, i + 1)), 150);
    }
  };

  const handleSubmit = () => {
    const filled = answers.filter((a): a is string | string[] => a !== null);
    if (filled.length === total) {
      onSubmitAll?.(filled);
    }
  };

  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 space-y-3" style={{ borderRadius: 10 }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-[var(--color-text-tertiary)]">Questions</span>
        {total > 1 && (
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
        )}
      </div>

      {/* Current question */}
      <QuestionView
        key={currentIdx}
        data={current}
        answer={answers[currentIdx]}
        onAnswer={handleAnswer}
      />

      {/* Footer — skip / next / submit */}
      <div className="flex items-center justify-end gap-2 pt-1">
        {!isLast && (
          <button
            onClick={() => setCurrentIdx((i) => Math.min(total - 1, i + 1))}
            className="px-3 py-1 text-sm font-medium bg-[var(--color-layer-3)] text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)] transition-colors"
            style={{ borderRadius: 6 }}
          >
            Skip
          </button>
        )}
        {!isLast && (current.mode === "multi_select" || current.mode === "text") && answers[currentIdx] !== null && (
          <button
            onClick={() => setCurrentIdx((i) => Math.min(total - 1, i + 1))}
            className="px-3 py-1 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors"
            style={{ borderRadius: 6 }}
          >
            Next
          </button>
        )}
        {(isLast || total === 1) && (
          <button
            onClick={handleSubmit}
            disabled={!allAnswered}
            className="px-3 py-1 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 transition-colors"
            style={{ borderRadius: 6 }}
          >
            Submit
          </button>
        )}
      </div>

    </div>
  );
}
