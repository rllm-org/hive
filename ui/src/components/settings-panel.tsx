"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { getAuthHeader } from "@/lib/auth";
import { LuLogOut } from "react-icons/lu";
import { ThemeToggle } from "@/components/theme-toggle";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

export function SettingsPanel() {
  const { user, logout } = useAuth();
  const searchParams = useSearchParams();
  const showPasswordPrompt = searchParams.get("set_password") === "1";

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

        {/* Set Password (for GitHub-only accounts) */}
        {showPasswordPrompt && <SetPasswordCard />}

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

function SetPasswordCard() {
  const { disconnectGithub } = useAuth();
  const [pw, setPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [passwordSet, setPasswordSet] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [disconnected, setDisconnected] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const submitPassword = async () => {
    if (pw.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (pw !== confirmPw) { setError("Passwords do not match."); return; }
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/auth/set-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ password: pw }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => null);
        throw new Error(d?.detail ?? "Failed to set password");
      }
      setPasswordSet(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  const doDisconnect = async () => {
    setDisconnecting(true);
    setError(null);
    try {
      await disconnectGithub();
      setDisconnected(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg !== "__redirect__") setError(msg || "Disconnect failed");
    } finally {
      setDisconnecting(false);
    }
  };

  const inputCls = "w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] outline-none";

  return (
    <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 overflow-hidden">
      <div className="px-5 py-4 border-b border-amber-200 dark:border-amber-800">
        <h3 className="text-base font-semibold text-[var(--color-text)]">
          {disconnected ? "GitHub disconnected" : passwordSet ? "Disconnect GitHub" : "Set a password"}
        </h3>
        <p className="text-xs text-[var(--color-text-secondary)] mt-1">
          {disconnected
            ? "You can now reconnect GitHub to get a fresh token."
            : passwordSet
              ? "Password saved. You can now disconnect GitHub."
              : "Your account was created via GitHub. Set a password first so you can disconnect and reconnect."}
        </p>
      </div>
      <div className="px-5 py-4 space-y-3">
        {disconnected ? (
          <p className="text-sm text-green-600 dark:text-green-400">
            Done — go to your profile to reconnect GitHub.
          </p>
        ) : passwordSet ? (
          <button
            disabled={disconnecting}
            onClick={doDisconnect}
            className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 transition-colors"
          >
            {disconnecting ? "Disconnecting…" : "Disconnect GitHub"}
          </button>
        ) : (
          <>
            <input type="password" placeholder="New password (min 8 chars)" value={pw} onChange={(e) => setPw(e.target.value)} className={inputCls} />
            <input type="password" placeholder="Confirm password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} className={inputCls} />
            <button disabled={submitting} onClick={submitPassword} className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] disabled:opacity-50">
              {submitting ? "Setting…" : "Set password"}
            </button>
          </>
        )}
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>
    </div>
  );
}
