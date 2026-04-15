"use client";

import { KeyboardEvent, useState } from "react";

interface Props {
  busy: boolean;
  disabled?: boolean;
  onSend: (text: string, interrupt: boolean) => void | Promise<void>;
}

export function Composer({ busy, disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  const submit = async (interrupt: boolean) => {
    const text = value.trim();
    if (!text) return;
    setValue("");
    await onSend(text, interrupt);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(false);
    } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && busy) {
      e.preventDefault();
      submit(true);
    }
  };

  return (
    <div className="border-t border-[var(--color-border)] p-2 flex items-end gap-2">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKey}
        disabled={disabled}
        rows={2}
        placeholder={busy ? "Agent is thinking — ⌘⏎ to interrupt, ⏎ to queue." : "Message the agent… (⏎ to send, ⇧⏎ for newline)"}
        className="flex-1 resize-none bg-transparent text-sm px-2 py-1 border border-[var(--color-border)] focus:outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
      />
      <button
        type="button"
        disabled={disabled || !value.trim()}
        onClick={() => submit(busy)}
        className="px-3 py-1.5 text-sm bg-[var(--color-accent)] text-white disabled:opacity-50"
      >
        {busy ? "Interrupt" : "Send"}
      </button>
    </div>
  );
}
