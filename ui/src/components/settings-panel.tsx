"use client";

import { useAuth } from "@/lib/auth";
import { LuLogOut } from "react-icons/lu";
import { ThemeToggle } from "@/components/theme-toggle";

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
