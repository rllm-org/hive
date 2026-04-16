"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getAuthHeader } from "@/lib/auth";
import { LuLogOut } from "react-icons/lu";
import { ThemeToggle } from "@/components/theme-toggle";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

export function SettingsPanel() {
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <div className="h-full py-8 px-8">
      <h2 className="text-4xl font-normal leading-tight tracking-tight text-[var(--color-text)] mb-8">Settings</h2>

      <div className="space-y-6">
        {/* Appearance */}
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="text-base font-semibold text-[var(--color-text)]">Appearance</h3>
          </div>
          <div className="px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-[var(--color-text)]">Theme</div>
                <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5">Choose between light, dark, or system theme</div>
              </div>
              <ThemeToggle />
            </div>
          </div>
        </div>

        {/* Account */}
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] overflow-hidden">
          <div className="px-5 py-4 border-b border-[var(--color-border)]">
            <h3 className="text-base font-semibold text-[var(--color-text)]">General</h3>
          </div>
          <div className="px-5 py-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-sm text-[var(--color-text)]">Email</div>
              <div className="text-sm text-[var(--color-text-tertiary)]">{user.email}</div>
            </div>
            <div className="border-t border-[var(--color-border)]" />
            <div className="flex items-center justify-between">
              <div className="text-sm text-[var(--color-text)]">Log out</div>
              <button
                onClick={logout}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-500 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
              >
                <LuLogOut size={14} />
                Log out
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface PasswordSectionProps {
  hasPassword: boolean;
  onPasswordSet?: () => void;
}

export function PasswordSection({ hasPassword, onPasswordSet }: PasswordSectionProps) {
  const [open, setOpen] = useState(false);
  const [savedAt, setSavedAt] = useState(0);

  const showSaved = savedAt > 0 && Date.now() - savedAt < 3000;
  const buttonLabel = hasPassword ? "Change password" : "Set password";

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setOpen(true)}
        className="shrink-0 px-3 py-1.5 text-xs font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
      >
        {buttonLabel}
      </button>
      {showSaved && <span className="text-xs text-emerald-500">Saved</span>}
      {open && (
        <PasswordModal
          hasPassword={hasPassword}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setSavedAt(Date.now());
            onPasswordSet?.();
            setOpen(false);
          }}
        />
      )}
    </div>
  );
}

function PasswordModal({ hasPassword, onClose, onSaved }: { hasPassword: boolean; onClose: () => void; onSaved: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [currentPw, setCurrentPw] = useState("");
  const [pw, setPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const submit = async () => {
    if (hasPassword && !currentPw) { setError("Enter your current password."); return; }
    if (pw.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (pw !== confirmPw) { setError("Passwords do not match."); return; }
    setError(null);
    setSubmitting(true);
    try {
      const body: Record<string, string> = { password: pw };
      if (hasPassword) body.current_password = currentPw;
      const res = await fetch(`${API_BASE}/auth/set-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => null);
        throw new Error(d?.detail ?? "Failed to save password");
      }
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]";

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[420px] flex flex-col animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-base font-semibold text-[var(--color-text)]">
            {hasPassword ? "Change Password" : "Set Password"}
          </h2>
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
        <div className="px-6 py-5 space-y-3">
          {hasPassword && (
            <div>
              <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Current password</label>
              <input
                type="password"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                className={inputCls}
                style={{ outline: "none", boxShadow: "none" }}
                autoComplete="current-password"
                autoFocus
              />
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">New password</label>
            <input
              type="password"
              placeholder="At least 8 characters"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              className={inputCls}
              style={{ outline: "none", boxShadow: "none" }}
              autoComplete="new-password"
              autoFocus={!hasPassword}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Confirm new password</label>
            <input
              type="password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              className={inputCls}
              style={{ outline: "none", boxShadow: "none" }}
              autoComplete="new-password"
            />
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
            >
              {submitting ? "Saving…" : hasPassword ? "Change password" : "Set password"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
