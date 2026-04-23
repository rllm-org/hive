"use client";

import { useEffect, useState } from "react";
import { LuFolder } from "react-icons/lu";
import { apiPostJson } from "@/lib/api";
import { Modal, ModalHeader, ModalBody } from "@/components/shared/modal";

interface CreateWorkspaceDialogProps {
  open: boolean;
  /** "workspace" creates a real workspace; "task" creates a task channel */
  mode?: "workspace" | "task";
  taskPath?: string;
  onClose: () => void;
  onCreated: (name: string) => void;
}

const NAME_MAX = 21;
const NAME_RE = /^[a-z0-9][a-z0-9-]*$/;

export function CreateWorkspaceDialog({ open, mode = "workspace", taskPath, onClose, onCreated }: CreateWorkspaceDialogProps) {
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

  const handleChange = (val: string) => {
    const lower = val.toLowerCase();
    setName(lower);
    const trimmed = lower.trim();
    if (trimmed.length > NAME_MAX) {
      setError(`Name must be ${NAME_MAX} characters or fewer`);
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
      if (mode === "workspace") {
        await apiPostJson("/workspaces", { name: trimmed, type: "cloud" });
      } else {
        await apiPostJson(`/tasks/${taskPath}/channels`, { name: trimmed });
      }
      onCreated(trimmed);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to create ${mode === "workspace" ? "workspace" : "channel"}`);
    } finally {
      setSubmitting(false);
    }
  };

  const trimmedLen = name.trim().length;
  const label = mode === "workspace" ? "workspace" : "channel";

  return (
    <Modal open={open} onClose={onClose}>
      <ModalHeader onClose={onClose}>Create a {label}</ModalHeader>
      <ModalBody>
        <form onSubmit={handleSubmit}>
          <p className="text-[13px] text-[var(--color-text-secondary)] mb-4">
            {mode === "workspace"
              ? "Workspaces are shared environments where you and your agents collaborate. Use lowercase letters, numbers, and hyphens."
              : "Channels are where conversations happen around a topic. Use lowercase letters, numbers, and hyphens."}
          </p>
          <label className="block text-[13px] font-semibold text-[var(--color-text)] mb-1.5">
            Name
          </label>
          <div className="relative">
            <LuFolder
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)] pointer-events-none"
            />
            <input
              type="text"
              value={name}
              onChange={(e) => handleChange(e.target.value)}
              placeholder={mode === "workspace" ? "e.g. my-project" : "e.g. prompt-experiments"}
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
      </ModalBody>
    </Modal>
  );
}
