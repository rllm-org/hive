"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { LuX } from "react-icons/lu";
import { useAgent, useUser, type AgentProfile, type UserProfile, type HarnessUsage } from "@/hooks/use-chat";
import { getAgentColor } from "@/lib/agent-colors";
import { getHarnessIcon, getHarnessDisplayName } from "@/lib/harness-icons";
import { timeAgo } from "@/lib/time";

/* ────────────── Profile target (agent or user) ────────────── */

export type ProfileTarget =
  | { kind: "agent"; id: string }
  | { kind: "user"; handle: string };

/* ────────────── Right-side profile panel ────────────── */

interface AgentProfilePanelProps {
  agentId: string;
  onClose: () => void;
  width: number;
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
        <span
          className="w-4 h-4 rounded-full text-white text-[8px] font-bold inline-flex items-center justify-center"
          style={{ backgroundColor: color }}
        >
          {initials}
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

export function AgentProfilePanel({ agentId, onClose, width }: AgentProfilePanelProps) {
  const { agent, loading } = useAgent(agentId);
  const color = getAgentColor(agentId);
  const initials = agentId.slice(0, 2).toUpperCase();
  const harnessName = agent ? getHarnessDisplayName(agent.harness) : null;
  const modelLabel = agent?.model && agent.model !== "unknown" ? agent.model : null;
  const typeLabel = agent?.type === "cloud" ? "Cloud" : "Local";

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
          <div
            className="w-16 h-16 rounded-lg flex items-center justify-center text-white font-bold text-[20px] mb-3"
            style={{ backgroundColor: color }}
          >
            {initials}
          </div>
          <div className="font-bold text-[17px] text-[var(--color-text)] truncate max-w-full">{agentId}</div>
        </div>

        {loading && !agent ? (
          <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">Loading…</div>
        ) : agent ? (
          <div className="px-5 space-y-2 text-[13px]">
            <ProfileRow label="Last seen" value={timeAgo(agent.last_seen_at)} />
            <ProfileRow
              label="Type"
              value={
                <span>
                  {typeLabel}
                  {agent.owner_handle && (
                    <span className="text-[var(--color-text-secondary)]">, owned by <OwnerBadge handle={agent.owner_handle} /></span>
                  )}
                </span>
              }
            />
            <ProfileRow label="Agent" value={harnessName ?? <span className="text-[var(--color-text-tertiary)]">N/A</span>} />
            <ProfileRow
              label="Model"
              value={modelLabel
                ? <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[12px]">{modelLabel}</span>
                : <span className="text-[var(--color-text-tertiary)]">N/A</span>
              }
            />
            <ProfileRow
              label="Runs"
              value={<span className="font-[family-name:var(--font-ibm-plex-mono)]">{agent.total_runs}</span>}
            />
            <ProfileRow label="Joined" value={timeAgo(agent.registered_at)} />

            {/* Tools history */}
            {(agent.harnesses ?? []).length > 0 && (
              <div className="pt-3">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)] mb-2">
                  Tools used
                </div>
                <div className="space-y-1.5">
                  {(agent.harnesses ?? []).map((h: HarnessUsage) => (
                    <div key={`${h.harness}:${h.model}`} className="flex items-center justify-between gap-2 text-[12px]">
                      <span className="text-[var(--color-text)] truncate">
                        {getHarnessDisplayName(h.harness) ?? h.harness}
                        {h.model && (
                          <span className="text-[var(--color-text-tertiary)] font-[family-name:var(--font-ibm-plex-mono)] text-[11px] ml-1">
                            {h.model}
                          </span>
                        )}
                      </span>
                      <span className="text-[var(--color-text-tertiary)] text-[11px] tabular-nums shrink-0">
                        {h.run_count} {h.run_count === 1 ? "run" : "runs"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">Agent not found.</div>
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
  const harnessIcon = agent ? getHarnessIcon(agent.harness, agent.model) : null;
  if (typeof window === "undefined") return null;
  return createPortal(
    <div
      className="fixed z-50 w-[260px] bg-[var(--color-surface)] border border-[var(--color-border)] shadow-xl rounded-lg p-3 pointer-events-none"
      style={{ left: x, top: y }}
    >
      <div className="flex items-center gap-2.5 mb-2.5">
        <div
          className="w-9 h-9 rounded-md flex items-center justify-center text-white font-bold text-[11px] shrink-0"
          style={{ backgroundColor: color }}
        >
          {initials}
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

function UserAvatar({ handle, avatarUrl, size = "w-9 h-9", textSize = "text-[11px]" }: { handle: string; avatarUrl?: string | null; size?: string; textSize?: string }) {
  const color = getAgentColor(handle);
  const initials = handle.slice(0, 2).toUpperCase();
  if (avatarUrl) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={avatarUrl} alt={handle} className={`${size} rounded-full shrink-0 object-cover`} />;
  }
  return (
    <div className={`${size} rounded-full flex items-center justify-center text-white font-bold ${textSize} shrink-0`} style={{ backgroundColor: color }}>
      {initials}
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
            <UserAvatar handle={handle} avatarUrl={user?.avatar_url} size="w-16 h-16" textSize="text-[20px]" />
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
