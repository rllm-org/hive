"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth";
import { AuthModal } from "@/components/auth-modal";
import { ClaimAgentModal } from "@/components/claim-agent-modal";
import { CreateTaskModal } from "@/components/create-task-modal";
import { Avatar } from "@/components/shared";
import { getAuthHeader } from "@/lib/auth";
import { LuBot, LuActivity, LuPlus } from "react-icons/lu";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

interface AgentInfo {
  id: string;
  registered_at: string;
  last_seen_at: string;
  total_runs: number;
}

interface ProfileData {
  id: number;
  email: string;
  role: string;
  created_at: string;
  agents: AgentInfo[];
}

function AccountPanel({ onClose }: { onClose: () => void }) {
  const { user, logout } = useAuth();
  const [showClaim, setShowClaim] = useState(false);
  const [showCreateTask, setShowCreateTask] = useState(false);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const overlayRef = useRef<HTMLDivElement>(null);

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, { headers: getAuthHeader() });
      if (res.ok) setProfile(await res.json());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  return (
    <>
    {showClaim && (
      <ClaimAgentModal
        onClose={() => setShowClaim(false)}
        onClaimed={() => { setShowClaim(false); fetchProfile(); }}
      />
    )}
    {showCreateTask && (
      <CreateTaskModal
        onClose={() => setShowCreateTask(false)}
        onCreated={() => setShowCreateTask(false)}
      />
    )}
    {!showClaim && !showCreateTask && (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[9999] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[440px] flex flex-col animate-fade-in">
        {/* Top bar */}
        <div className="flex items-center justify-between px-5 pt-4 pb-0">
          <button
            onClick={() => { logout(); onClose(); }}
            className="px-2.5 py-1.5 text-xs font-medium text-red-500 hover:bg-red-500/10 transition-colors"
          >
            Log out
          </button>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>

        {/* Profile header */}
        <div className="flex flex-col items-center px-8 pt-2 pb-6">
          <div className="w-16 h-16 rounded-full bg-[var(--color-accent)] flex items-center justify-center text-white font-bold text-2xl mb-3">
            {user?.email[0].toUpperCase()}
          </div>
          <div className="text-base font-semibold text-[var(--color-text)]">{user?.email}</div>
          {user?.role === "admin" && (
            <div className="flex items-center gap-2 mt-1.5">
              <span className="inline-flex items-center px-2.5 h-6 text-[11px] font-semibold border border-[var(--color-accent)] text-[var(--color-accent)] bg-[var(--color-accent)]/10 tracking-wide uppercase">
                Admin
              </span>
              <button
                onClick={() => setShowCreateTask(true)}
                className="inline-flex items-center gap-1 px-2.5 h-6 text-[11px] font-semibold bg-[var(--color-accent)] text-white hover:opacity-90 transition-opacity"
              >
                <LuPlus size={10} />
                Create task
              </button>
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-[var(--color-border)] mx-6" />

        {/* Agents section */}
        <div className="overflow-y-auto px-8 py-6" style={{ maxHeight: 320 }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide">
              My Agents ({profile?.agents.length ?? 0})
            </h3>
            <button
              onClick={() => setShowClaim(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
            >
              <LuPlus size={12} />
              Claim Agent
            </button>
          </div>

          {loading && (
            <div className="text-xs text-[var(--color-text-tertiary)] text-center py-8">Loading...</div>
          )}

          {!loading && (!profile?.agents.length) && (
            <div className="text-center py-8 border border-dashed border-[var(--color-border)]">
              <LuBot size={24} className="mx-auto mb-3 text-[var(--color-text-tertiary)]" />
              <p className="text-sm text-[var(--color-text-tertiary)]">No agents claimed yet</p>
            </div>
          )}

          <div className="space-y-2">
            {profile?.agents.map((agent) => (
              <div
                key={agent.id}
                className="flex items-center gap-3 p-3 bg-[var(--color-layer-1)] border border-[var(--color-border)]"
              >
                <Avatar id={agent.id} size="sm" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-[var(--color-text)] truncate">
                    {agent.id}
                  </div>
                  <div className="text-[11px] text-[var(--color-text-tertiary)]">
                    <span className="flex items-center gap-1">
                      <LuActivity size={10} />
                      {agent.total_runs} runs
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

        </div>
      </div>
    </div>
    )}
    </>
  );
}

export function UserMenu() {
  const { user } = useAuth();
  const [showPanel, setShowPanel] = useState(false);

  if (!user) return null;

  return (
    <div className="fixed bottom-4 left-4 z-[9998]">
      <button
        data-user-menu
        onClick={() => setShowPanel(true)}
        className="w-9 h-9 rounded-full bg-[var(--color-accent)] text-white text-sm font-semibold flex items-center justify-center hover:opacity-90 transition-opacity shadow-lg"
      >
        {user.email[0].toUpperCase()}
      </button>
      {showPanel && <AccountPanel onClose={() => setShowPanel(false)} />}
    </div>
  );
}
