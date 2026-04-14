"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { LuX } from "react-icons/lu";
import { useAgent, useUser, type AgentProfile, type UserProfile } from "@/hooks/use-chat";
import { getAgentColor } from "@/lib/agent-colors";
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

export function AgentProfilePanel({ agentId, onClose, width }: AgentProfilePanelProps) {
  const { agent, loading } = useAgent(agentId);
  const color = getAgentColor(agentId);
  const initials = agentId.slice(0, 2).toUpperCase();
  return (
    <aside
      className="hidden md:flex flex-col shrink-0 bg-[var(--color-layer-1)] border-l border-[var(--color-border)]"
      style={{ width }}
    >
      <div className="shrink-0 h-[60px] px-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center justify-between">
        <div className="text-[15px] font-bold text-[var(--color-text)]">Agent profile</div>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
          aria-label="Close profile"
        >
          <LuX size={16} />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-5">
        {/* Avatar + name */}
        <div className="flex items-center gap-3 mb-5">
          <div
            className="w-16 h-16 rounded-md flex items-center justify-center text-white font-bold text-[20px]"
            style={{ backgroundColor: color }}
          >
            {initials}
          </div>
          <div className="min-w-0">
            <div className="font-bold text-[18px] text-[var(--color-text)] truncate">{agentId}</div>
            <div className="text-[12px] text-[var(--color-text-secondary)]">Agent</div>
          </div>
        </div>
        {loading && !agent ? (
          <div className="text-[13px] text-[var(--color-text-secondary)]">Loading…</div>
        ) : agent ? (
          <ProfileFields agent={agent} />
        ) : (
          <div className="text-[13px] text-[var(--color-text-secondary)]">Agent not found.</div>
        )}
      </div>
    </aside>
  );
}

function ProfileFields({ agent }: { agent: AgentProfile }) {
  return (
    <dl className="space-y-4 text-[13px]">
      <Field label="Owner">
        {agent.owner_handle ? (
          <span className="text-[var(--color-text)]">@{agent.owner_handle}</span>
        ) : (
          <span className="text-[var(--color-text-tertiary)]">Unclaimed</span>
        )}
      </Field>
      <Field label="Joined">
        <span className="text-[var(--color-text)]">{timeAgo(agent.registered_at)}</span>
      </Field>
      <Field label="Last seen">
        <span className="text-[var(--color-text)]">{timeAgo(agent.last_seen_at)}</span>
      </Field>
      <Field label="Total runs">
        <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[var(--color-text)]">
          {agent.total_runs}
        </span>
      </Field>
    </dl>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)] mb-1">
        {label}
      </dt>
      <dd>{children}</dd>
    </div>
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
      <div className="flex items-center gap-3 mb-2">
        <div
          className="w-10 h-10 rounded-md flex items-center justify-center text-white font-bold text-[12px] shrink-0"
          style={{ backgroundColor: color }}
        >
          {initials}
        </div>
        <div className="min-w-0">
          <div className="font-bold text-[14px] text-[var(--color-text)] truncate">{agentId}</div>
          {agent?.owner_handle ? (
            <div className="text-[11px] text-[var(--color-text-secondary)] truncate">@{agent.owner_handle}</div>
          ) : (
            <div className="text-[11px] text-[var(--color-text-tertiary)]">Unclaimed</div>
          )}
        </div>
      </div>
      <div className="space-y-1 text-[12px] text-[var(--color-text-secondary)]">
        {agent ? (
          <>
            <div>
              Joined <span className="text-[var(--color-text)]">{timeAgo(agent.registered_at)}</span>
            </div>
            <div>
              <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[var(--color-text)]">
                {agent.total_runs}
              </span>{" "}
              total runs
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

function UserHoverCard({ handle, x, y }: { handle: string; x: number; y: number }) {
  const { user } = useUser(handle);
  const color = getAgentColor(handle);
  const initials = handle.slice(0, 2).toUpperCase();
  if (typeof window === "undefined") return null;
  return createPortal(
    <div
      className="fixed z-50 w-[260px] bg-[var(--color-surface)] border border-[var(--color-border)] shadow-xl rounded-lg p-3 pointer-events-none"
      style={{ left: x, top: y }}
    >
      <div className="flex items-center gap-3 mb-2">
        {user?.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={user.avatar_url} alt={handle} className="w-10 h-10 rounded-full shrink-0 object-cover" />
        ) : (
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-[12px] shrink-0"
            style={{ backgroundColor: color }}
          >
            {initials}
          </div>
        )}
        <div className="min-w-0">
          <div className="font-bold text-[14px] text-[var(--color-text)] truncate">@{handle}</div>
          <div className="text-[11px] text-[var(--color-text-secondary)]">User</div>
        </div>
      </div>
      <div className="space-y-1 text-[12px] text-[var(--color-text-secondary)]">
        {user ? (
          <>
            <div>
              Joined <span className="text-[var(--color-text)]">{timeAgo(user.created_at)}</span>
            </div>
            <div>
              <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[var(--color-text)]">
                {user.agent_count}
              </span>{" "}
              {user.agent_count === 1 ? "agent" : "agents"}
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
  const color = getAgentColor(handle);
  const initials = handle.slice(0, 2).toUpperCase();
  return (
    <aside
      className="hidden md:flex flex-col shrink-0 bg-[var(--color-layer-1)] border-l border-[var(--color-border)]"
      style={{ width }}
    >
      <div className="shrink-0 h-[60px] px-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center justify-between">
        <div className="text-[15px] font-bold text-[var(--color-text)]">User profile</div>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
          aria-label="Close profile"
        >
          <LuX size={16} />
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-5">
        <div className="flex items-center gap-3 mb-5">
          {user?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.avatar_url} alt={handle} className="w-16 h-16 rounded-full shrink-0 object-cover" />
          ) : (
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center text-white font-bold text-[20px]"
              style={{ backgroundColor: color }}
            >
              {initials}
            </div>
          )}
          <div className="min-w-0">
            <div className="font-bold text-[18px] text-[var(--color-text)] truncate">@{handle}</div>
            <div className="text-[12px] text-[var(--color-text-secondary)]">User</div>
          </div>
        </div>
        {loading && !user ? (
          <div className="text-[13px] text-[var(--color-text-secondary)]">Loading…</div>
        ) : user ? (
          <UserFields user={user} />
        ) : (
          <div className="text-[13px] text-[var(--color-text-secondary)]">User not found.</div>
        )}
      </div>
    </aside>
  );
}

function UserFields({ user }: { user: UserProfile }) {
  return (
    <dl className="space-y-4 text-[13px]">
      <Field label="Joined">
        <span className="text-[var(--color-text)]">{timeAgo(user.created_at)}</span>
      </Field>
      <Field label="Agents">
        <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[var(--color-text)]">
          {user.agent_count}
        </span>
      </Field>
    </dl>
  );
}
