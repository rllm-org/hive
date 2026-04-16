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
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (pw.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (pw !== confirm) { setError("Passwords do not match."); return; }
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
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] outline-none";

  return (
    <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800 overflow-hidden">
      <div className="px-5 py-4 border-b border-amber-200 dark:border-amber-800">
        <h3 className="text-base font-semibold text-[var(--color-text)]">Set a password</h3>
        <p className="text-xs text-[var(--color-text-secondary)] mt-1">
          Your account was created via GitHub. Set a password so you can disconnect and reconnect GitHub.
        </p>
      </div>
      <div className="px-5 py-4 space-y-3">
        {done ? (
          <p className="text-sm text-green-600 dark:text-green-400">
            Password set. You can now disconnect GitHub from your profile.
          </p>
        ) : (
          <>
            <input type="password" placeholder="New password (min 8 chars)" value={pw} onChange={(e) => setPw(e.target.value)} className={inputCls} />
            <input type="password" placeholder="Confirm password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputCls} />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <button disabled={submitting} onClick={submit} className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] disabled:opacity-50">
              {submitting ? "Setting…" : "Set password"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
