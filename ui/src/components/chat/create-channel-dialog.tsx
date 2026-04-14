"use client";

import { useEffect, useState } from "react";
import { LuHash, LuX } from "react-icons/lu";
import { apiPostJson } from "@/lib/api";

interface CreateChannelDialogProps {
  open: boolean;
  taskPath: string;
  onClose: () => void;
  onCreated: (name: string) => void;
}

const NAME_MAX = 21;
const NAME_RE = /^[a-z0-9][a-z0-9-]*$/;

export function CreateChannelDialog({ open, taskPath, onClose, onCreated }: CreateChannelDialogProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setName("");
      setError("");
      setSubmitting(false);
    }
  }, [open]);

  // Esc to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const handleChange = (val: string) => {
    const lower = val.toLowerCase();
    setName(lower);
    const trimmed = lower.trim();
    if (trimmed.length > NAME_MAX) {
      setError(`Channel name must be ${NAME_MAX} characters or fewer`);
    } else if (trimmed.length > 0 && !NAME_RE.test(trimmed)) {
      setError("Lowercase letters, numbers, and hyphens only — must start with a letter or number");
    } else if (error) {
      setError("");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim().toLowerCase();
    if (!trimmed) return;
    if (trimmed.length > NAME_MAX || !NAME_RE.test(trimmed)) return;
    setSubmitting(true);
    setError("");
    try {
      await apiPostJson(`/tasks/${taskPath}/channels`, { name: trimmed });
      onCreated(trimmed);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create channel");
    } finally {
      setSubmitting(false);
    }
  };

  const trimmedLen = name.trim().length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div
        className="relative z-10 w-[480px] rounded-2xl bg-[var(--color-surface)] shadow-2xl border border-[var(--color-border)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-[16px] font-bold text-[var(--color-text)]">Create a channel</h2>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
            aria-label="Close"
          >
            <LuX size={16} />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="px-5 py-4">
          <p className="text-[13px] text-[var(--color-text-secondary)] mb-4">
            Channels are where conversations happen around a topic. Use lowercase letters, numbers, and hyphens.
          </p>
          <label className="block text-[13px] font-semibold text-[var(--color-text)] mb-1.5">
            Name
          </label>
          <div className="relative">
            <LuHash
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] pointer-events-none"
            />
            <input
              type="text"
              value={name}
              onChange={(e) => handleChange(e.target.value)}
              placeholder="e.g. prompt-experiments"
              autoFocus
              maxLength={NAME_MAX + 5}
              className="w-full pl-8 pr-12 py-2 text-[14px] rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-accent)] transition-colors"
              style={{ outline: "none", boxShadow: "none" }}
            />
            <span
              className={`absolute right-3 top-1/2 -translate-y-1/2 text-[11px] tabular-nums ${
                trimmedLen > NAME_MAX ? "text-red-500" : "text-[var(--color-text-tertiary)]"
              }`}
            >
              {trimmedLen}/{NAME_MAX}
            </span>
          </div>
          {error && (
            <p className="mt-2 text-[12px] text-red-500">{error}</p>
          )}

          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-[13px] font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !trimmedLen || trimmedLen > NAME_MAX || !NAME_RE.test(name.trim()) || !!error}
              className="px-4 py-2 text-[13px] font-semibold rounded-md bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? "Creating…" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
