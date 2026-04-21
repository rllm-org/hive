"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth";

interface ClaudeConnectModalProps {
  onClose: () => void;
  onConnected?: () => void;
}

export function ClaudeConnectModal({ onClose, onConnected }: ClaudeConnectModalProps) {
  const { claudeSubmitToken } = useAuth();
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const submit = async () => {
    const trimmed = token.trim();
    if (!trimmed) return;
    setLoading(true);
    setError("");
    try {
      await claudeSubmitToken(trimmed);
      onConnected?.();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "failed to save token");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-lg rounded-lg bg-[var(--color-surface)] p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-semibold">Connect your Claude account</h2>
        <p className="mb-3 text-sm text-[var(--color-muted)]">
          Hive runs agents on your Claude subscription. Generate a token once and paste it here —
          every workspace you create will use your account.
        </p>

        <ol className="mb-4 list-decimal space-y-2 pl-5 text-sm">
          <li>
            Install the Claude Code CLI if you haven&apos;t already:{" "}
            <a
              href="https://docs.anthropic.com/claude/docs/claude-code"
              target="_blank" rel="noopener noreferrer"
              className="text-[var(--color-accent)] underline"
            >
              setup guide ↗
            </a>
          </li>
          <li>
            Run this in your terminal:
            <pre className="mt-1 overflow-x-auto rounded bg-[var(--color-layer-2)] p-2 text-xs font-mono">claude setup-token</pre>
          </li>
          <li>Approve in your browser; the terminal will print a token starting with <code>sk-ant-oat01-…</code></li>
          <li>Paste the token below:</li>
        </ol>

        <label className="mb-1 block text-sm font-medium">Claude OAuth token</label>
        <input
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          className="mb-3 w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 font-mono text-sm"
          placeholder="sk-ant-oat01-…"
          autoFocus
        />

        {error && <p className="mb-3 text-sm text-red-500">{error}</p>}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded border border-[var(--color-border)] px-3 py-1.5 text-sm hover:bg-[var(--color-hover)]"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={loading || !token.trim()}
            className="rounded bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? "Saving…" : "Connect"}
          </button>
        </div>
      </div>
    </div>
  );
}
