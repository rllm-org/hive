"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { LuX, LuBot, LuCpu, LuCalendar, LuActivity } from "react-icons/lu";
import { AgentChat } from "@/components/shared/agent-chat";
import { FileExplorer } from "@/components/shared/file-explorer";
import { useWorkspaceFiles } from "@/hooks/use-workspace-files";
import { useWorkspaceAgent, type ChatMessage } from "@/hooks/use-workspace-agent";
import AgentProfilePage from "@/app/agents/[id]/page";
import { useAgent, useUser, type AgentProfile, type UserProfile, type HarnessUsage } from "@/hooks/use-chat";
import { getAgentColor } from "@/lib/agent-colors";
import { getHarnessDisplayName } from "@/lib/harness-icons";
import { timeAgo, isOnline } from "@/lib/time";
import { Avatar } from "@/components/shared";

/** Small green/hollow dot indicating online status (Slack-style). */
function OnlineDot({ online, size = "w-3 h-3" }: { online: boolean; size?: string }) {
  return (
    <span
      className={`block ${size} rounded-full border-2 ${
        online ? "bg-green-500 border-white" : "bg-white border-gray-400"
      }`}
    />
  );
}

/* ────────────── Profile target (agent or user) ────────────── */

export type ProfileTarget =
  | { kind: "agent"; id: string }
  | { kind: "user"; handle: string };

/* ────────────── Right-side profile panel ────────────── */

interface AgentProfilePanelProps {
  agentId: string;
  onClose: () => void;
  width: number;
  workspaceId?: string | number | null;
}

function OwnerBadge({ handle }: { handle: string }) {
  const { user } = useUser(handle);
  const color = getAgentColor(handle);
  const initials = handle.slice(0, 2).toUpperCase();
  return (
    <span className="inline-flex items-center gap-1">
      {user?.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={user.avatar_url} alt={handle} className="w-4 h-4 rounded-full object-cover inline-block" />
      ) : (
        <span className="w-4 h-4 rounded-full overflow-hidden inline-flex">
          <Avatar id={handle} seed={null} kind="user" size="xs" />
        </span>
      )}
      <span>{handle}</span>
    </span>
  );
}

function ProfileRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[var(--color-text-tertiary)]">{label}</span>
      <span className="text-[var(--color-text)]">{value}</span>
    </div>
  );
}

type AgentPanelTab = "profile" | "workspace" | "activity";

const AGENT_PANEL_TABS: { id: AgentPanelTab; label: string }[] = [
  { id: "profile", label: "Profile" },
  { id: "workspace", label: "Workspace" },
  { id: "activity", label: "Activity" },
];

function AgentFilesView({ sessionId }: { sessionId?: string | null }) {
  const { tree, loading, readFile } = useWorkspaceFiles(sessionId ?? null);
  const read = async (path: string) => (await readFile(path)) ?? undefined;
  return <FileExplorer tree={tree} loading={loading} onReadFile={read} />;
}

export function AgentProfilePanel({ agentId, onClose, width, workspaceId }: AgentProfilePanelProps) {
  const { agent } = useAgent(agentId);
  const [tab, setTab] = useState<AgentPanelTab>("profile");
  const needsConnection = tab === "activity" || tab === "workspace";
  const { messages: activityMessages, sendMessage, cancel, isLoading, sessionId } = useWorkspaceAgent(
    workspaceId ?? null, needsConnection ? agentId : null,
  );

  return (
    <aside
      className="hidden md:flex flex-col shrink-0 bg-[var(--color-layer-1)] border-l border-[var(--color-border)]"
      style={{ width }}
    >
      {/* Header — workspace style */}
      <div className="shrink-0 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
        <div className="h-[52px] px-5 flex items-center gap-2">
          <Avatar id={agentId} seed={agent?.avatar_seed} kind="agent" size="sm" />
          <span className="font-bold text-[17px] text-[var(--color-text)] truncate">{agentId}</span>
          {agent && (
            <OnlineDot online={isOnline(agent.last_seen_at)} size="w-2.5 h-2.5" />
          )}
          <button
            onClick={onClose}
            className="ml-auto w-7 h-7 flex items-center justify-center rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
          >
            <LuX size={16} />
          </button>
        </div>
        <div className="flex items-center gap-1 px-5 mt-1">
          {AGENT_PANEL_TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 pb-2 text-[13px] font-medium border-b-2 transition-colors ${
                  active
                    ? "border-[var(--color-accent)] text-[var(--color-text)]"
                    : "border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {tab === "profile" && (
          <AgentProfilePage embeddedAgentId={agentId} />
        )}

        {tab === "activity" && (
          <AgentChat
            agentId={agentId}
            messages={activityMessages}
            onSend={sendMessage}
            onCancel={cancel}
            loading={isLoading}
          />
        )}

        {tab === "workspace" && (
          <AgentFilesView sessionId={sessionId} />
        )}
      </div>
    </aside>
  );
}


/* ────────────── Hover card popover ────────────── */

const HOVER_DELAY_MS = 350;

/** Internal hover-handle hook shared by agent and user links */
function useHoverPos() {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const elRef = useRef<HTMLSpanElement>(null);
  const cancel = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };
  const enter = () => {
    cancel();
    timerRef.current = setTimeout(() => {
      if (elRef.current) {
        const r = elRef.current.getBoundingClientRect();
        setPos({ x: r.left, y: r.bottom + 6 });
      }
    }, HOVER_DELAY_MS);
  };
  const leave = () => {
    cancel();
    setPos(null);
  };
  useEffect(() => () => cancel(), []);
  return { pos, elRef, enter, leave };
}

export function AgentLink({
  agentId,
  onOpenProfile,
  className = "",
  children,
}: {
  agentId: string;
  onOpenProfile: (target: ProfileTarget) => void;
  className?: string;
  children: ReactNode;
}) {
  const { pos, elRef, enter, leave } = useHoverPos();
  return (
    <span
      ref={elRef}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onClick={(e) => {
        e.stopPropagation();
        onOpenProfile({ kind: "agent", id: agentId });
      }}
      className={`cursor-pointer ${className}`}
    >
      {children}
      {pos && <AgentHoverCard agentId={agentId} x={pos.x} y={pos.y} />}
    </span>
  );
}

export function UserLink({
  handle,
  onOpenProfile,
  className = "",
  children,
}: {
  handle: string;
  onOpenProfile: (target: ProfileTarget) => void;
  className?: string;
  children: ReactNode;
}) {
  const { pos, elRef, enter, leave } = useHoverPos();
  return (
    <span
      ref={elRef}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onClick={(e) => {
        e.stopPropagation();
        onOpenProfile({ kind: "user", handle });
      }}
      className={`cursor-pointer ${className}`}
    >
      {children}
      {pos && <UserHoverCard handle={handle} x={pos.x} y={pos.y} />}
    </span>
  );
}

function AgentHoverCard({ agentId, x, y }: { agentId: string; x: number; y: number }) {
  const { agent } = useAgent(agentId);
  const color = getAgentColor(agentId);
  const initials = agentId.slice(0, 2).toUpperCase();
  if (typeof window === "undefined") return null;
  return createPortal(
    <div
      className="fixed z-50 w-[260px] bg-[var(--color-surface)] border border-[var(--color-border)] shadow-xl rounded-lg p-3 pointer-events-none"
      style={{ left: x, top: y }}
    >
      <div className="flex items-center gap-2.5 mb-2.5">
        <div className="relative shrink-0">
          <Avatar id={agentId} seed={agent?.avatar_seed} kind="agent" size="md" />
          {agent && (
            <span className="absolute -bottom-1 -right-1">
              <OnlineDot online={isOnline(agent.last_seen_at)} />
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-bold text-[13px] text-[var(--color-text)] truncate">{agentId}</div>
        </div>
      </div>
      <div className="text-[12px] space-y-1">
        {agent ? (
          <>
            <div className="flex items-baseline justify-between">
              <span className="text-[var(--color-text-tertiary)]">Type</span>
              <span className="text-[var(--color-text)]">
                {agent.type === "cloud" ? "Cloud" : "Local"}
                {agent.type !== "cloud" && agent.owner_handle && <span className="text-[var(--color-text-secondary)]">, owned by <OwnerBadge handle={agent.owner_handle} /></span>}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[var(--color-text-tertiary)]">Agent</span>
              <span className="text-[var(--color-text)]">
                {agent.harness && agent.harness !== "unknown" ? (getHarnessDisplayName(agent.harness) ?? agent.harness) : <span className="text-[var(--color-text-tertiary)]">N/A</span>}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[var(--color-text-tertiary)]">Model</span>
              <span className="text-[var(--color-text)]">
                {agent.model && agent.model !== "unknown" ? <span className="font-[family-name:var(--font-ibm-plex-mono)]">{agent.model}</span> : <span className="text-[var(--color-text-tertiary)]">N/A</span>}
              </span>
            </div>
          </>
        ) : (
          <div className="text-[var(--color-text-tertiary)]">Loading…</div>
        )}
      </div>
    </div>,
    document.body,
  );
}

function UserAvatar({ handle, avatarUrl, size = "w-9 h-9", avatarSize = "md" }: { handle: string; avatarUrl?: string | null; size?: string; textSize?: string; avatarSize?: "xs" | "sm" | "md" | "lg" | "xl" }) {
  if (avatarUrl) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={avatarUrl} alt={handle} className={`${size} rounded-full shrink-0 object-cover`} />;
  }
  return (
    <div className={`${size} rounded-full overflow-hidden shrink-0`}>
      <Avatar id={handle} seed={null} kind="user" size={avatarSize} />
    </div>
  );
}

function UserHoverCard({ handle, x, y }: { handle: string; x: number; y: number }) {
  const { user } = useUser(handle);
  if (typeof window === "undefined") return null;
  return createPortal(
    <div
      className="fixed z-50 w-[260px] bg-[var(--color-surface)] border border-[var(--color-border)] shadow-xl rounded-lg p-3 pointer-events-none"
      style={{ left: x, top: y }}
    >
      <div className="flex items-center gap-2.5 mb-2.5">
        <UserAvatar handle={handle} avatarUrl={user?.avatar_url} />
        <div className="min-w-0 flex-1">
          <div className="font-bold text-[13px] text-[var(--color-text)] truncate">{handle}</div>
        </div>
      </div>
      <div className="text-[12px] space-y-1">
        {user ? (
          <>
            <div className="flex items-baseline justify-between">
              <span className="text-[var(--color-text-tertiary)]">Agents</span>
              <span className="text-[var(--color-text)] font-[family-name:var(--font-ibm-plex-mono)]">{user.agent_count}</span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[var(--color-text-tertiary)]">Joined</span>
              <span className="text-[var(--color-text)]">{timeAgo(user.created_at)}</span>
            </div>
          </>
        ) : (
          <div className="text-[var(--color-text-tertiary)]">Loading…</div>
        )}
      </div>
    </div>,
    document.body,
  );
}

/* ────────────── User profile panel (right side) ────────────── */

interface UserProfilePanelProps {
  handle: string;
  onClose: () => void;
  width: number;
}

export function UserProfilePanel({ handle, onClose, width }: UserProfilePanelProps) {
  const { user, loading } = useUser(handle);
  return (
    <aside
      className="hidden md:flex flex-col shrink-0 bg-[var(--color-layer-1)] border-l border-[var(--color-border)]"
      style={{ width }}
    >
      <div className="shrink-0 h-[60px] px-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center justify-between">
        <div className="text-[15px] font-bold text-[var(--color-text)]">Profile</div>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
          aria-label="Close profile"
        >
          <LuX size={16} />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* Centered avatar + name */}
        <div className="px-5 pt-6 pb-4 flex flex-col items-center">
          <div className="mb-3">
            <UserAvatar handle={handle} avatarUrl={user?.avatar_url} size="w-16 h-16" avatarSize="xl" />
          </div>
          <div className="font-bold text-[17px] text-[var(--color-text)] truncate max-w-full">{handle}</div>
        </div>

        {loading && !user ? (
          <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">Loading…</div>
        ) : user ? (
          <div className="px-5 space-y-2 text-[13px]">
            <ProfileRow
              label="Agents"
              value={<span className="font-[family-name:var(--font-ibm-plex-mono)]">{user.agent_count}</span>}
            />
            <ProfileRow label="Joined" value={timeAgo(user.created_at)} />
          </div>
        ) : (
          <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">User not found.</div>
        )}
      </div>
    </aside>
  );
}
