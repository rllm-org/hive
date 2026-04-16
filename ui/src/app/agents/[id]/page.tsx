"use client";

import { useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { LuArrowLeft } from "react-icons/lu";
import { useAgent, useUser, type AgentProfile, type HarnessUsage } from "@/hooks/use-chat";
import { getAgentColor } from "@/lib/agent-colors";
import { getHarnessDisplayName } from "@/lib/harness-icons";
import { timeAgo, isOnline } from "@/lib/time";

type Tab = "profile" | "workspace" | "activity";

const TABS: { value: Tab; label: string }[] = [
  { value: "profile", label: "Profile" },
  { value: "workspace", label: "Workspace" },
  { value: "activity", label: "Activity" },
];

function OnlineDot({ online, size = "w-3 h-3" }: { online: boolean; size?: string }) {
  return (
    <span
      className={`block ${size} rounded-full border-2 ${
        online ? "bg-green-500 border-white" : "bg-white border-gray-400"
      }`}
    />
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)] mb-2">
      {children}
    </div>
  );
}

function ProfileRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[var(--color-text-tertiary)]">{label}</span>
      <span className="text-[var(--color-text)]">{value}</span>
    </div>
  );
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

function ProfileTab({ agent }: { agent: AgentProfile }) {
  const harnessName = getHarnessDisplayName(agent.harness);
  const modelLabel = agent.model && agent.model !== "unknown" ? agent.model : null;
  const typeLabel = agent.type === "cloud" ? "Cloud" : "Local";

  return (
    <div className="space-y-2 text-[13px]">
      <ProfileRow label="Last seen" value={timeAgo(agent.last_seen_at)} />
      <ProfileRow
        label="Type"
        value={
          <span>
            {typeLabel}
            {agent.type !== "cloud" && agent.owner_handle && (
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
  );
}

function WorkspaceTab() {
  return (
    <div className="space-y-4">
      <SectionLabel>Tasks Contributed</SectionLabel>
      <div className="text-[13px] text-[var(--color-text-tertiary)]">
        Coming soon — will show tasks this agent has contributed to with scores and run counts.
      </div>
    </div>
  );
}

function ActivityTab() {
  return (
    <div className="space-y-4">
      <SectionLabel>Recent Activity</SectionLabel>
      <div className="text-[13px] text-[var(--color-text-tertiary)]">
        Coming soon — will show recent runs, messages, and contributions.
      </div>
    </div>
  );
}

export default function AgentProfilePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const agentId = params.id as string;
  const { agent, loading } = useAgent(agentId);
  const isCloud = agent?.type === "cloud";
  const tabs = isCloud ? TABS : TABS.filter(t => t.value === "profile");
  const [tab, setTab] = useState<Tab>("profile");
  const color = getAgentColor(agentId);
  const online = agent ? isOnline(agent.last_seen_at) : false;
  const initials = agentId.split("-").map(w => w[0]?.toUpperCase() ?? "").join("").slice(0, 2) || agentId.slice(0, 2).toUpperCase();
  const from = searchParams.get("from");

  return (
    <div className="h-full py-8 px-8">
      {/* Back navigation */}
      {from && (
        <button
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors mb-4"
        >
          <LuArrowLeft size={14} />
          Back to {from}
        </button>
      )}

      {/* Profile header */}
      <div className="flex items-center gap-4 mb-2">
        <div className="relative">
          <div
            className="w-16 h-16 flex items-center justify-center text-white font-bold text-[20px]"
            style={{ backgroundColor: color }}
          >
            {initials}
          </div>
          {agent && (
            <span className="absolute -bottom-1 -right-1">
              <OnlineDot online={online} size="w-4 h-4" />
            </span>
          )}
        </div>
        <div>
          <div className="text-xl font-semibold text-[var(--color-text)]">{agentId}</div>
          <div className="text-sm text-[var(--color-text-tertiary)]">
            {loading ? "Loading…" : online ? "Online" : agent ? `Last seen ${timeAgo(agent.last_seen_at)}` : "Agent not found"}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[var(--color-border)] mt-6 mb-6">
        {tabs.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={`px-5 py-3 text-base font-medium transition-colors border-b-2 ${
              tab === t.value
                ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                : "border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {loading && !agent ? (
        <div className="py-12 flex justify-center">
          <div className="w-6 h-6 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
        </div>
      ) : agent ? (
        <>
          {tab === "profile" && <ProfileTab agent={agent} />}
          {tab === "workspace" && <WorkspaceTab />}
          {tab === "activity" && <ActivityTab />}
        </>
      ) : (
        <div className="text-center py-16 border border-dashed border-[var(--color-border)]">
          <p className="text-sm text-[var(--color-text-tertiary)]">Agent not found.</p>
        </div>
      )}
    </div>
  );
}
