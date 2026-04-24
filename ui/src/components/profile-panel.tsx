"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth, getGithubOAuthUrl, getAuthHeader, fetchAuthConfig } from "@/lib/auth";
import { ClaimAgentModal } from "@/components/claim-agent-modal";
import { ClaudeConnectModal } from "@/components/claude-connect-modal";
import { Avatar } from "@/components/shared";
import { useRouter } from "next/navigation";
import { LuBot, LuActivity, LuPlus, LuGithub, LuLogOut, LuRefreshCw, LuMonitor, LuLaptop, LuCloud, LuMail, LuKeyRound, LuMoreVertical, LuTrash2 } from "react-icons/lu";
import { LoadingSpinner } from "@/components/loading-spinner";
import { ThemeToggle } from "@/components/theme-toggle";
import { PasswordSection } from "@/components/settings-panel";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

interface AgentInfo {
  id: string;
  registered_at: string;
  last_seen_at: string;
  total_runs: number;
  avatar_seed: string | null;
}

interface ProfileData {
  id: number;
  email: string;
  role: string;
  github_username: string | null;
  avatar_url: string | null;
  avatar_seed: string | null;
  created_at: string;
  has_password: boolean;
  agents: AgentInfo[];
}

interface WorkspaceAgentPreview {
  id: string;
  avatar_seed: string | null;
}

interface Workspace {
  id: number;
  name: string;
  type: "local" | "cloud" | "persistent";
  agent_count?: number;
  agents?: WorkspaceAgentPreview[];
  created_at: string;
}

type ProfileTab = "workspaces" | "agents" | "settings";

function HandleSection() {
  const { user, checkHandleAvailable, updateHandle } = useAuth();
  const [value, setValue] = useState(user?.handle ?? "");
  const [status, setStatus] = useState<"idle" | "checking" | "available" | "taken" | "invalid">("idle");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(0);

  useEffect(() => { setValue(user?.handle ?? ""); }, [user?.handle]);

  useEffect(() => {
    if (!value || value === user?.handle) {
      setStatus("idle");
      setReason("");
      return;
    }
    setStatus("checking");
    const t = setTimeout(async () => {
      try {
        const result = await checkHandleAvailable(value);
        if (result.available) {
          setStatus("available");
          setReason("");
        } else if (result.reason) {
          setStatus("invalid");
          setReason(result.reason);
        } else {
          setStatus("taken");
          setReason("already taken");
        }
      } catch {
        setStatus("idle");
      }
    }, 300);
    return () => clearTimeout(t);
  }, [value, user?.handle, checkHandleAvailable]);

  const handleSave = async () => {
    if (status !== "available") return;
    setSaving(true);
    try {
      await updateHandle(value);
      setSavedAt(Date.now());
      setStatus("idle");
    } catch (err) {
      setReason(err instanceof Error ? err.message : "save failed");
      setStatus("invalid");
    } finally {
      setSaving(false);
    }
  };

  const showSaved = savedAt > 0 && Date.now() - savedAt < 3000;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value.toLowerCase())}
            minLength={2}
            maxLength={20}
            placeholder="alice"
            className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] outline-none"
            style={{ outline: "none", boxShadow: "none" }}
          />
          {status === "checking" && <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-[var(--color-text-tertiary)]">…</span>}
          {status === "available" && <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-emerald-500">✓</span>}
          {(status === "taken" || status === "invalid") && <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-red-500">✗</span>}
        </div>
        <button
          onClick={handleSave}
          disabled={saving || status !== "available"}
          className="px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] disabled:opacity-50 transition-colors"
        >
          {saving ? "..." : "Save"}
        </button>
      </div>
      <div className="text-xs text-[var(--color-text-tertiary)]">Used in your task URLs and on your profile.</div>
      {reason && <p className="text-xs text-red-500">{reason}</p>}
      {!reason && showSaved && <p className="text-xs text-emerald-500">Saved.</p>}
    </div>
  );
}


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
    <div className="space-y-2">
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
        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs font-mono bg-[var(--color-layer-1)] px-3 py-2 text-[var(--color-text-tertiary)]">
            {prefix}{"•".repeat(24)}
          </code>
          <button
            onClick={handleGenerate}
            disabled={regenerating}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border text-red-500 border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40 disabled:opacity-50 transition-colors"
          >
            <LuRefreshCw size={12} />
            {regenerating ? "Generating..." : "Regenerate"}
          </button>
        </div>
      ) : (
        <div>
          <button
            onClick={handleGenerate}
            disabled={regenerating}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border text-[var(--color-accent)] border-[var(--color-border)] hover:bg-[var(--color-layer-1)] disabled:opacity-50 transition-colors"
          >
            <LuRefreshCw size={12} />
            {regenerating ? "Generating..." : "Generate API key"}
          </button>
        </div>
      )}
      <div className="text-xs text-[var(--color-text-tertiary)]">Use this key to authenticate with the Hive CLI. Run <code className="px-1 py-0.5 bg-[var(--color-layer-1)] text-[var(--color-text)]">hive auth login</code></div>

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

function CreateWorkspaceModal({ onClose, onCreated, existingNames }: { onClose: () => void; onCreated: (workspace: Workspace) => void; existingNames: string[] }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [name, setName] = useState(() => {
    let x = 1;
    while (existingNames.includes(`my-workspace-${x}`)) x++;
    return `my-workspace-${x}`;
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handleCreate = async (type: "local" | "cloud") => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/workspaces`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ name: name.trim(), type }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed to create workspace");
      onCreated(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
      setSubmitting(false);
    }
  };

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[420px] flex flex-col animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-base font-semibold text-[var(--color-text)]">Create Workspace</h2>
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
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Workspace Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-workspace"
              className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
              style={{ outline: "none", boxShadow: "none" }}
              autoFocus
            />
          </div>

          <button
            onClick={() => setError("Local workspaces are currently unavailable.")}
            disabled={submitting}
            className="w-full flex items-center gap-4 p-4 border border-[var(--color-border)] text-left cursor-not-allowed opacity-60"
          >
            <LuLaptop size={24} className="text-[var(--color-text-tertiary)] shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-[var(--color-text)]">Local</span>
                <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)]" style={{ borderRadius: 3 }}>
                  Coming soon
                </span>
              </div>
              <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5">
                Run the agent in your local computer.
              </div>
            </div>
          </button>

          <button
            onClick={() => handleCreate("cloud")}
            disabled={submitting || !name.trim()}
            className="w-full flex items-center gap-4 p-4 border border-[var(--color-border)] hover:bg-[var(--color-layer-1)] transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <LuCloud size={24} className="text-[var(--color-text-secondary)] shrink-0" />
            <div>
              <div className="text-sm font-semibold text-[var(--color-text)]">Cloud</div>
              <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5">
                Run the agent in the cloud sandbox, managed by us.
              </div>
            </div>
          </button>

          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
      </div>
    </div>
  );
}

function AgentCard({ agent, onDeleted }: { agent: AgentInfo; onDeleted: () => void }) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setConfirmDelete(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      const res = await fetch(`${API_BASE}/agents/${agent.id}`, {
        method: "DELETE",
        headers: getAuthHeader(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to delete");
      }
      setMenuOpen(false);
      onDeleted();
    } catch {
      setDeleting(false);
    }
  };

  return (
    <div className="relative flex items-center gap-3 p-4 bg-[var(--color-surface)] border border-[var(--color-border)] hover:bg-[var(--color-layer-1)] transition-colors">
      <div
        className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer"
        onClick={() => router.push(`/agents/${agent.id}?from=Account`)}
      >
        <Avatar id={agent.id} seed={agent.avatar_seed} kind="agent" size="md" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-[var(--color-text)] truncate">
            {agent.id}
          </div>
          <div className="text-xs text-[var(--color-text-tertiary)] flex items-center gap-1.5 mt-0.5">
            <LuActivity size={11} />
            {agent.total_runs} runs
          </div>
        </div>
      </div>
      <div ref={menuRef} className="relative shrink-0">
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); setConfirmDelete(false); }}
          className="w-7 h-7 flex items-center justify-center rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
        >
          <LuMoreVertical size={14} />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 z-50 bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 min-w-[140px]" style={{ borderRadius: 6 }}>
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                className="w-full flex items-center gap-2 px-3 py-2 text-[13px] text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors text-left"
              >
                <LuTrash2 size={13} />
                Delete agent
              </button>
            ) : (
              <div className="px-3 py-2">
                <p className="text-[12px] text-red-500 mb-2">Delete {agent.id}?</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setConfirmDelete(false)}
                    disabled={deleting}
                    className="px-2 py-1 text-[12px] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="px-2 py-1 text-[12px] font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 transition-colors rounded"
                  >
                    {deleting ? "..." : "Confirm"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function ProfilePanel() {
  const { user, logout, disconnectGithub, claudeStatus, claudeDisconnect } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<ProfileTab>(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const t = params.get("tab");
      if (t && ["agents", "settings"].includes(t)) return t as ProfileTab;
    }
    return "agents";
  });
  const [showClaim, setShowClaim] = useState(false);
  const [showCreateWorkspace, setShowCreateWorkspace] = useState(false);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [installUrl, setInstallUrl] = useState<string | null>(null);
  const [disconnectError, setDisconnectError] = useState<string | null>(null);
  const [claudeConn, setClaudeConn] = useState<{ connected: boolean; connected_at?: string } | null>(null);
  const [showClaudeConnect, setShowClaudeConnect] = useState(false);

  const fetchClaudeStatus = useCallback(async () => {
    try {
      setClaudeConn(await claudeStatus());
    } catch { /* noop */ }
  }, [claudeStatus]);

  useEffect(() => { fetchClaudeStatus(); }, [fetchClaudeStatus]);

  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, { headers: getAuthHeader() });
      if (res.ok) setProfile(await res.json());
    } catch {}
    setLoading(false);
  }, []);

  const fetchWorkspaces = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/workspaces`, { headers: getAuthHeader() });
      if (res.ok) {
        const data = await res.json();
        setWorkspaces(data.workspaces);
      }
    } catch {}
  }, []);

  useEffect(() => { fetchProfile(); }, [fetchProfile, user?.github_username]);
  useEffect(() => { fetchWorkspaces(); }, [fetchWorkspaces]);
  useEffect(() => {
    fetchAuthConfig().then((c) => { if (c.github_app_install_url) setInstallUrl(c.github_app_install_url); });
  }, []);

  if (!user) return null;

  const tabs: { id: ProfileTab; label: string }[] = [
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
      {showCreateWorkspace && (
        <CreateWorkspaceModal
          onClose={() => setShowCreateWorkspace(false)}
          existingNames={workspaces.map(w => w.name)}
          onCreated={(ws) => {
            setShowCreateWorkspace(false);
            fetchWorkspaces();
            router.push(`/workspaces/${ws.id}`);
          }}
        />
      )}
      {showClaudeConnect && (
        <ClaudeConnectModal
          onClose={() => setShowClaudeConnect(false)}
          onConnected={() => { setShowClaudeConnect(false); fetchClaudeStatus(); }}
        />
      )}
      <div className="h-full py-8 px-8">
        {/* Profile header */}
        <div className="flex items-center gap-4 mb-2">
          {(profile?.avatar_url || user.avatar_url) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile?.avatar_url || user.avatar_url!}
              alt="Profile"
              className="w-16 h-16 rounded-full shrink-0 object-cover"
            />
          ) : (
            <div className="w-16 h-16 rounded-full overflow-hidden shrink-0">
              <Avatar id={user.handle} seed={profile?.avatar_seed} kind="user" size="xl" />
            </div>
          )}
          <div>
            <div className="text-xl font-semibold text-[var(--color-text)]">{user.handle}</div>
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
        {tab === "workspaces" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-medium text-[var(--color-text)]">
                Your Workspaces
              </h3>
              <button
                onClick={() => setShowCreateWorkspace(true)}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
              >
                <LuPlus size={14} />
                Create Workspace
              </button>
            </div>

            {loading ? (
              <LoadingSpinner />
            ) : workspaces.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-[var(--color-border)]">
                <LuMonitor size={32} className="mx-auto mb-3 text-[var(--color-text-tertiary)]" />
                <p className="text-base text-[var(--color-text-tertiary)] mb-2">No workspaces yet</p>
                <p className="text-sm text-[var(--color-text-tertiary)]">Create a workspace to start working with an agent.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {workspaces.map((ws) => {
                  const agentPreviews = ws.agents ?? [];
                  const shown = agentPreviews.slice(0, 4);
                  const extra = (ws.agent_count ?? agentPreviews.length) - shown.length;
                  return (
                    <div
                      key={ws.id}
                      onClick={() => router.push(`/workspaces/${ws.id}`)}
                      className="flex items-center gap-3 p-4 bg-[var(--color-surface)] border border-[var(--color-border)] cursor-pointer hover:bg-[var(--color-layer-1)] transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-semibold">
                          {ws.type}
                        </div>
                        <div className="text-sm font-semibold text-[var(--color-text)] truncate">
                          {ws.name}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {shown.length > 0 ? (
                          <>
                            {shown.map((a) => (
                              <div
                                key={a.id}
                                title={a.id}
                                className="overflow-hidden"
                                style={{ width: 22, height: 22, borderRadius: 4 }}
                              >
                                <Avatar id={a.id} seed={a.avatar_seed} kind="agent" size="sm" />
                              </div>
                            ))}
                            {extra > 0 && (
                              <span className="text-[11px] text-[var(--color-text-tertiary)] ml-1">
                                +{extra}
                              </span>
                            )}
                          </>
                        ) : (
                          <span className="text-[11px] text-[var(--color-text-tertiary)]">No agents</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
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

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {profile?.agents.map((agent) => (
                <AgentCard key={agent.id} agent={agent} onDeleted={fetchProfile} />
              ))}
            </div>
          </div>
        )}

        {tab === "settings" && (
          <div className="space-y-6">
            {/* Profile */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Profile</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-4">
                <div className="text-sm text-[var(--color-text)] mb-2">Handle</div>
                <div className="max-w-sm">
                  <HandleSection />
                </div>
              </div>
            </div>

            {/* Sign-in Methods */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Sign-in Methods</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
                {/* Email */}
                <div className="px-5 py-3 flex items-start gap-3">
                  <LuMail size={16} className="shrink-0 text-[var(--color-text-secondary)] mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-[var(--color-text)]">Email</div>
                    <div className="text-xs text-[var(--color-text-tertiary)] truncate">{user.email}</div>
                  </div>
                </div>

                {/* Password */}
                <div className="px-5 py-3 flex items-start gap-3">
                  <LuKeyRound size={16} className="shrink-0 text-[var(--color-text-secondary)] mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-[var(--color-text)]">Password</div>
                        <div className="text-xs text-[var(--color-text-tertiary)]">
                          {profile?.has_password ? "Configured" : "Not configured"}
                        </div>
                      </div>
                      <PasswordSection
                        hasPassword={profile?.has_password ?? false}
                        onPasswordSet={fetchProfile}
                      />
                    </div>
                  </div>
                </div>

                {/* GitHub */}
                <div className="px-5 py-3 flex items-start gap-3">
                  <LuGithub size={16} className="shrink-0 text-[var(--color-text-secondary)] mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-[var(--color-text)]">GitHub</div>
                        <div className="text-xs text-[var(--color-text-tertiary)] truncate">
                          {profile?.github_username ? `Connected as ${profile.github_username}` : "Not connected"}
                        </div>
                      </div>
                      {profile?.github_username ? (
                        <button
                          onClick={async () => {
                            setDisconnectError(null);
                            const result = await disconnectGithub();
                            if (result.ok) {
                              fetchProfile();
                            } else if (result.reason === "needs_password") {
                              setDisconnectError("Set a password above before disconnecting GitHub.");
                            } else {
                              setDisconnectError(result.message);
                            }
                          }}
                          className="shrink-0 px-3 py-1.5 text-xs font-medium text-red-500 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                        >
                          Disconnect
                        </button>
                      ) : (
                        <button
                          onClick={async () => {
                            if (installUrl) {
                              window.location.href = installUrl;
                            } else {
                              window.location.href = await getGithubOAuthUrl("connect");
                            }
                          }}
                          className="shrink-0 px-3 py-1.5 text-xs font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
                        >
                          Connect
                        </button>
                      )}
                    </div>
                    {disconnectError && (
                      <p className="text-xs text-red-500 mt-2">{disconnectError}</p>
                    )}
                  </div>
                </div>

              </div>
            </div>

            {/* Connected Services */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Connected Services</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)]">
                <div className="px-5 py-3 flex items-start gap-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/claude-icon.png" alt="Claude" width={16} height={16} className="shrink-0 mt-0.5 rounded-full" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-[var(--color-text)]">Claude Account</div>
                        <div className="text-xs text-[var(--color-text-tertiary)] truncate">
                          {claudeConn?.connected ? "Connected" : "Not connected"}
                        </div>
                      </div>
                      {claudeConn?.connected ? (
                        <div className="flex gap-2">
                          <button
                            onClick={() => setShowClaudeConnect(true)}
                            className="shrink-0 px-3 py-1.5 text-xs font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
                          >
                            Reconnect
                          </button>
                          <button
                            onClick={async () => {
                              const result = await claudeDisconnect();
                              if (result.ok) fetchClaudeStatus();
                            }}
                            className="shrink-0 px-3 py-1.5 text-xs font-medium text-red-500 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                          >
                            Disconnect
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setShowClaudeConnect(true)}
                          className="shrink-0 px-3 py-1.5 text-xs font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
                        >
                          Connect
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Developer */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Developer</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-4">
                <h4 className="text-sm text-[var(--color-text)] mb-3">User API Key</h4>
                <div className="max-w-md">
                  <ApiKeySection />
                </div>
              </div>
            </div>

            {/* Preferences */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Preferences</h3>
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

            {/* Account */}
            <div>
              <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Account</h3>
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-4">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-[var(--color-text)]">Log out</div>
                  <button
                    onClick={logout}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-500 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                  >
                    <LuLogOut size={12} />
                    Log out
                  </button>
                </div>
              </div>
            </div>
            <div className="h-12" />
          </div>
        )}
      </div>
    </>
  );
}
