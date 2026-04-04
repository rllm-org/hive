"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth, getGithubOAuthUrl, getAuthHeader, fetchAuthConfig } from "@/lib/auth";
import { ClaimAgentModal } from "@/components/claim-agent-modal";
import { CreateTaskModal } from "@/components/create-task-modal";
import { TaskExplorer } from "@/components/task-explorer";
import { Avatar } from "@/components/shared";
import { Task } from "@/types/api";
import { LuBot, LuActivity, LuPlus, LuGithub, LuLogOut, LuLayoutGrid, LuRefreshCw } from "react-icons/lu";
import { LoadingSpinner } from "@/components/loading-spinner";
import { ThemeToggle } from "@/components/theme-toggle";

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
  github_username: string | null;
  avatar_url: string | null;
  created_at: string;
  agents: AgentInfo[];
}

type ProfileTab = "tasks" | "agents" | "settings";

function ApiKeySection() {
  const [prefix, setPrefix] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/auth/api-key`, { headers: getAuthHeader() })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d) setPrefix(d.api_key_prefix); })
      .catch(() => {});
  }, []);

  const handleCopy = () => {
    if (newKey) {
      navigator.clipboard.writeText(newKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const [showConfirm, setShowConfirm] = useState(false);

  const handleGenerate = () => {
    if (prefix) {
      setShowConfirm(true);
    } else {
      doGenerate();
    }
  };

  const doGenerate = async () => {
    setShowConfirm(false);
    setRegenerating(true);
    try {
      const res = await fetch(`${API_BASE}/auth/api-key/regenerate`, { method: "POST", headers: getAuthHeader() });
      if (res.ok) {
        const data = await res.json();
        setNewKey(data.api_key);
        setPrefix(data.api_key.slice(0, 12));
      }
    } catch {}
    setRegenerating(false);
  };

  return (
    <div className="space-y-3">
      <div className="text-xs text-[var(--color-text-tertiary)]">Use this key to authenticate with the Hive CLI. Run <code className="px-1 py-0.5 bg-[var(--color-layer-1)] text-[var(--color-text)]">hive auth login</code></div>
      {newKey ? (
        <div className="px-4 py-3 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40">
          <p className="text-xs text-amber-800 dark:text-amber-300 mb-2">Copy this key now — it won&apos;t be shown again.</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono bg-white dark:bg-[var(--color-layer-1)] px-3 py-2 text-[var(--color-text)] truncate border border-amber-200 dark:border-amber-700">
              {newKey}
            </code>
            <button onClick={handleCopy} className="px-3 py-2 text-xs font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors">
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>
      ) : prefix ? (
        <code className="block text-xs font-mono bg-[var(--color-layer-1)] px-3 py-2 text-[var(--color-text-tertiary)]">
          {prefix}{"•".repeat(24)}
        </code>
      ) : null}
      <div className="flex justify-end">
      <button
        onClick={handleGenerate}
        disabled={regenerating}
        className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border disabled:opacity-50 transition-colors ${
          prefix
            ? "text-red-500 border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40"
            : "text-[var(--color-accent)] border-[var(--color-border)] hover:bg-[var(--color-layer-1)]"
        }`}
      >
        <LuRefreshCw size={12} />
        {regenerating ? "Generating..." : prefix ? "Regenerate key" : "Generate API key"}
      </button>
      </div>

      {showConfirm && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center backdrop-blur-md bg-black/30" onClick={() => setShowConfirm(false)}>
          <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[380px] animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-[var(--color-border)]">
              <h2 className="text-base font-semibold text-[var(--color-text)]">Regenerate API key?</h2>
            </div>
            <div className="px-6 py-5 space-y-4">
              <p className="text-sm text-[var(--color-text-secondary)]">The current key will stop working immediately. Any CLI sessions using the old key will need to re-authenticate.</p>
              <div className="flex items-center gap-2">
                <button onClick={doGenerate} className="px-4 py-2 text-sm font-medium bg-red-500 text-white hover:bg-red-600 transition-colors">
                  Regenerate
                </button>
                <button onClick={() => setShowConfirm(false)} className="px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ProfilePanel() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<ProfileTab>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const t = params.get("tab");
      if (t && ["tasks", "agents", "settings"].includes(t)) return t as ProfileTab;
    }
    return "tasks";
  });
  const [showClaim, setShowClaim] = useState(false);
  const searchParams = useSearchParams();
  const [showCreateTask, setShowCreateTask] = useState(searchParams.get("create") === "1");
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [myTasks, setMyTasks] = useState<Task[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [installUrl, setInstallUrl] = useState<string | null>(null);

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, { headers: getAuthHeader() });
      if (res.ok) setProfile(await res.json());
    } catch {}
    setLoading(false);
  }, []);

  const fetchMyTasks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/tasks/mine`, { headers: getAuthHeader() });
      if (res.ok) {
        const data = await res.json();
        setMyTasks(data.tasks);
      }
    } catch {}
  }, []);

  useEffect(() => { fetchProfile(); }, [fetchProfile, user?.github_username]);
  useEffect(() => { fetchMyTasks(); }, [fetchMyTasks]);
  useEffect(() => {
    if (searchParams.get("create") === "1") {
      window.history.replaceState({}, "", "/me");
    }
  }, [searchParams]);
  useEffect(() => {
    fetchAuthConfig().then((c) => { if (c.github_app_install_url) setInstallUrl(c.github_app_install_url); });
  }, []);

  if (!user) return null;

  const tabs: { id: ProfileTab; label: string }[] = [
    { id: "tasks", label: "Tasks" },
    { id: "agents", label: "Agents" },
    { id: "settings", label: "Settings" },
  ];

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
          onCreated={() => { setShowCreateTask(false); fetchMyTasks(); }}
        />
      )}
      <div className="h-full py-8 px-8">
        {/* Profile header */}
        <div className="flex items-center gap-4 mb-2">
          {(profile?.avatar_url || user.avatar_url) ? (
            <img
              src={profile?.avatar_url || user.avatar_url!}
              alt="Profile"
              className="w-16 h-16 rounded-full shrink-0 object-cover"
            />
          ) : (
            <div className="w-16 h-16 rounded-full bg-[var(--color-accent)] flex items-center justify-center text-white font-bold text-2xl shrink-0">
              {user.email[0].toUpperCase()}
            </div>
          )}
          <div>
            <div className="text-xl font-semibold text-[var(--color-text)]">{user.email}</div>
            <div className="flex items-center gap-2 mt-1">
              {user.role === "admin" && (
                <span className="inline-flex items-center px-2.5 h-6 text-[11px] font-semibold border border-[var(--color-accent)] text-[var(--color-accent)] bg-[var(--color-accent)]/10 tracking-wide uppercase">
                  Admin
                </span>
              )}
              {profile?.github_username && (
                <span className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-tertiary)]">
                  <LuGithub size={14} />
                  {profile.github_username}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-[var(--color-border)] mt-6 mb-6">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-5 py-3 text-base font-medium transition-colors border-b-2 ${
                tab === t.id
                  ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                  : "border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === "tasks" && (
          <div>
            {loading ? (
              <LoadingSpinner />
            ) : user.role === "admin" ? (
              <div className="text-center py-16 border border-dashed border-[var(--color-border)]">
                <LuLayoutGrid size={32} className="mx-auto mb-3 text-[var(--color-text-tertiary)]" />
                <p className="text-base text-[var(--color-text-tertiary)] mb-2">Admin tasks are managed in Public Tasks</p>
                <p className="text-sm text-[var(--color-text-tertiary)]">Go to the <a href="/tasks" className="text-[var(--color-accent)] hover:underline">Public Tasks</a> page to upload and manage tasks.</p>
              </div>
            ) : !profile?.github_username ? (
              <div className="text-center py-16 border border-dashed border-[var(--color-border)]">
                <LuGithub size={32} className="mx-auto mb-3 text-[var(--color-text-tertiary)]" />
                <p className="text-base text-[var(--color-text-tertiary)] mb-4">Connect GitHub to create tasks from your repos</p>
                <button
                  onClick={async () => {
                    if (installUrl) {
                      window.location.href = installUrl;
                    } else {
                      window.location.href = await getGithubOAuthUrl("connect");
                    }
                  }}
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-[#24292f] text-white hover:bg-[#32383f] dark:bg-white dark:text-black dark:hover:bg-[#e0e0e0] transition-colors"
                >
                  <LuGithub size={16} />
                  Connect GitHub Repositories
                </button>
              </div>
            ) : (
              <>
                <div className="mb-4 px-4 py-3 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40">
                  <p className="text-sm text-amber-800 dark:text-amber-300">Beta: Currently you can add tasks from your GitHub repos, but your agents will be able to join in the future.</p>
                </div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-medium text-[var(--color-text)]">Your Private Tasks</h3>
                  <button
                    onClick={() => setShowCreateTask(true)}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
                  >
                    <LuPlus size={14} />
                    Add task
                  </button>
                </div>
                <TaskExplorer title={null} tasks={myTasks} showFeed={true} linkPrefix="/me" ownerName={profile?.github_username ?? user.email} ownerAvatar={profile?.avatar_url ?? user.avatar_url} />
              </>
            )}
          </div>
        )}

        {tab === "agents" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-medium text-[var(--color-text)]">
                Agents ({profile?.agents.length ?? 0})
              </h3>
              <button
                onClick={() => setShowClaim(true)}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
              >
                <LuPlus size={14} />
                Claim Agent
              </button>
            </div>

            {loading && (
              <div className="text-sm text-[var(--color-text-tertiary)] text-center py-16">Loading...</div>
            )}

            {!loading && (!profile?.agents.length) && (
              <div className="text-center py-16 border border-dashed border-[var(--color-border)]">
                <LuBot size={32} className="mx-auto mb-3 text-[var(--color-text-tertiary)]" />
                <p className="text-base text-[var(--color-text-tertiary)]">No agents claimed yet</p>
              </div>
            )}

            <div className="space-y-2">
              {profile?.agents.map((agent) => (
                <div
                  key={agent.id}
                  className="flex items-center gap-4 p-4 bg-[var(--color-surface)] border border-[var(--color-border)]"
                >
                  <Avatar id={agent.id} size="sm" />
                  <div className="flex-1 min-w-0">
                    <div className="text-base font-medium text-[var(--color-text)] truncate">
                      {agent.id}
                    </div>
                    <div className="text-xs text-[var(--color-text-tertiary)]">
                      <span className="flex items-center gap-1.5">
                        <LuActivity size={12} />
                        {agent.total_runs} runs
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "settings" && (
          <div className="space-y-6">
            {/* Appearance */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Appearance</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm text-[var(--color-text)]">Theme</div>
                    <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5">Choose between light, dark, or system theme</div>
                  </div>
                  <ThemeToggle />
                </div>
              </div>
            </div>

            {/* API Key */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">API Key</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-4">
                <ApiKeySection />
              </div>
            </div>

            {/* General */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">General</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-4 space-y-4">
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
        )}
      </div>
    </>
  );
}
