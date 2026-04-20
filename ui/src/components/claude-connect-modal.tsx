"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth";

interface ClaudeConnectModalProps {
  onClose: () => void;
  onConnected?: () => void;
}

export function ClaudeConnectModal({ onClose, onConnected }: ClaudeConnectModalProps) {
  const { claudeStart, claudeSubmitCode } = useAuth();
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(true);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setStarting(true);
    setError("");
    claudeStart()
      .then((data) => {
        if (cancelled) return;
        setSessionId(data.auth_session_id);
        setAuthUrl(data.auth_url);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "failed to start Claude login");
      })
      .finally(() => { if (!cancelled) setStarting(false); });
    return () => { cancelled = true; };
  }, [claudeStart]);

  const submit = async () => {
    if (!sessionId || !code.trim()) return;
    setLoading(true);
    setError("");
    try {
      await claudeSubmitCode(sessionId, code.trim());
      onConnected?.();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "failed to submit code");
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
      <div className="w-full max-w-md rounded-lg bg-[var(--color-surface)] p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-semibold">Connect your Claude account</h2>
        <p className="mb-4 text-sm text-[var(--color-muted)]">
          Hive runs agents on your Claude subscription. Log in once and every
          workspace you create will use your Claude account.
        </p>

        {starting && <p className="text-sm text-[var(--color-muted)]">Preparing login…</p>}

        {!starting && authUrl && (
          <>
            <div className="mb-3">
              <a
                href={authUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded bg-[var(--color-accent)] px-3 py-2 text-sm font-medium text-white hover:opacity-90"
              >
                Open Claude login ↗
              </a>
              <p className="mt-2 text-xs text-[var(--color-muted)]">
                A browser tab will open. Approve access, then copy the code Claude shows you.
              </p>
            </div>

            <label className="mb-1 block text-sm font-medium">Paste code here</label>
            <input
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              className="mb-3 w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm"
              placeholder="paste the code from the Claude page"
            />
          </>
        )}

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
            disabled={loading || starting || !sessionId || !code.trim()}
            className="rounded bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? "Connecting…" : "Connect"}
          </button>
        </div>
      </div>
    </div>
  );
}
