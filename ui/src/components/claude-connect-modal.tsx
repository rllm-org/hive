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
  const [copied, setCopied] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const submit = async () => {
    const trimmed = token.replace(/\s/g, "");
    if (!trimmed) return;
    setLoading(true);
    setError("");
    try {
      await claudeSubmitToken(trimmed);
      onConnected?.();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save token");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText("claude setup-token");
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const inputCls = "w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] font-[family-name:var(--font-ibm-plex-mono)] outline-none";
  const labelCls = "block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5";

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30"
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[380px] flex flex-col animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/claude-icon.png" alt="Claude" width={20} height={20} className="rounded-full" />
            <h2 className="text-base font-semibold text-[var(--color-text)]">Connect Claude</h2>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          <p className="text-xs text-[var(--color-text-tertiary)]">
            Run this in your terminal, then paste the token below.
          </p>

          <div
            onClick={handleCopy}
            className="flex items-center justify-between px-3 py-2 bg-[var(--color-layer-1)] border border-[var(--color-border)] cursor-pointer hover:bg-[var(--color-layer-2)] transition-colors"
          >
            <code className="text-xs font-[family-name:var(--font-ibm-plex-mono)] text-[var(--color-text)]">$ claude setup-token</code>
            <span className="text-[10px] text-[var(--color-text-tertiary)]">{copied ? "Copied!" : "Click to copy"}</span>
          </div>

          <div>
            <label className={labelCls}>Token</label>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              style={{ outline: "none", boxShadow: "none" }}
              className={inputCls}
              placeholder="sk-ant-oat01-…"
              autoFocus
            />
          </div>

          {/\s/.test(token) && (
            <p className="text-xs text-amber-500">Whitespace detected — it will be stripped automatically.</p>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}

          <button
            onClick={submit}
            disabled={loading || !token.replace(/\s/g, "")}
            className="w-full py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
          >
            {loading ? "Connecting..." : "Connect"}
          </button>
        </div>
      </div>
    </div>
  );
}
