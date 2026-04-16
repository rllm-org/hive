"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { LuArrowLeft, LuMessageSquare, LuUser, LuCpu, LuBrain, LuCalendar, LuActivity, LuLaptop, LuCloud } from "react-icons/lu";
import Avatar from "boring-avatars";
import { useAgent, useUser, type AgentProfile } from "@/hooks/use-chat";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getAgentColor } from "@/lib/agent-colors";
import { getHarnessDisplayName } from "@/lib/harness-icons";
import { Score } from "@/components/shared";
import { timeAgo, isOnline } from "@/lib/time";

interface AgentStats {
  total_runs: number;
  tasks_contributed: number;
  best_score: number | null;
  improvements: number;
}

interface AgentTaskEntry {
  id: number;
  owner: string;
  slug: string;
  name: string;
  runs: number;
  best_score: number | null;
  improvements: number;
}

interface AgentRunEntry {
  id: string;
  tldr: string;
  score: number | null;
  created_at: string;
  task: { owner: string; slug: string; name: string };
}

interface HeatmapDay {
  date: string;
  runs: number;
  improvements: number;
}

const RADIUS = { borderRadius: 6 } as const;
const RADIUS_SM = { borderRadius: 4 } as const;

function OnlineDot({ online, size = "w-3 h-3" }: { online: boolean; size?: string }) {
  return (
    <span
      className={`block ${size} rounded-full border-2 ${
        online ? "bg-green-500 border-white" : "bg-white border-gray-400"
      }`}
    />
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

function MetaItem({ icon: Icon, children }: { icon: React.ComponentType<{ size?: number; className?: string }>; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-[13px] text-[var(--color-text-secondary)]">
      <Icon size={14} className="shrink-0 text-[var(--color-text-tertiary)]" />
      <span className="truncate">{children}</span>
    </div>
  );
}

function SectionHeading({ title, action }: { title: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between mb-3">
      <h3 className="text-base font-semibold text-[var(--color-text)]">{title}</h3>
      {action}
    </div>
  );
}

/* ───────── Contribution heatmap ───────── */

const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];
const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function buildWeeks(days: HeatmapDay[], windowDays = 365): { date: Date; runs: number; improvements: number }[][] {
  const map = new Map<string, HeatmapDay>();
  for (const d of days) map.set(d.date, d);

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setDate(start.getDate() - windowDays + 1);
  start.setDate(start.getDate() - start.getDay());

  const weeks: { date: Date; runs: number; improvements: number }[][] = [];
  const cursor = new Date(start);
  while (cursor <= today) {
    const week: { date: Date; runs: number; improvements: number }[] = [];
    for (let i = 0; i < 7; i++) {
      const iso = cursor.toISOString().slice(0, 10);
      const entry = map.get(iso);
      week.push({
        date: new Date(cursor),
        runs: entry?.runs ?? 0,
        improvements: entry?.improvements ?? 0,
      });
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }
  return weeks;
}

function cellColor(runs: number, max: number): string {
  if (runs === 0) return "var(--color-layer-2)";
  const intensity = Math.min(1, runs / Math.max(1, max));
  if (intensity > 0.66) return "var(--color-accent)";
  if (intensity > 0.33) return "color-mix(in srgb, var(--color-accent) 60%, transparent)";
  return "color-mix(in srgb, var(--color-accent) 30%, transparent)";
}

function ContributionHeatmap({ days, loading }: { days: HeatmapDay[]; loading: boolean }) {
  const weeks = useMemo(() => buildWeeks(days, 365), [days]);
  const max = useMemo(() => days.reduce((m, d) => Math.max(m, d.runs), 0), [days]);
  const total = useMemo(() => days.reduce((s, d) => s + d.runs, 0), [days]);

  const monthPositions: { weekIdx: number; label: string }[] = useMemo(() => {
    const positions: { weekIdx: number; label: string }[] = [];
    let lastMonth = -1;
    weeks.forEach((week, wi) => {
      const firstDay = week[0];
      const month = firstDay.date.getMonth();
      if (month !== lastMonth && firstDay.date.getDate() <= 7) {
        positions.push({ weekIdx: wi, label: MONTH_LABELS[month] });
        lastMonth = month;
      }
    });
    return positions;
  }, [weeks]);

  return (
    <div
      className="bg-[var(--color-surface)] border border-[var(--color-border)] p-4"
      style={RADIUS}
    >
      <div className="text-[13px] text-[var(--color-text)] mb-3">
        <span className="font-semibold tabular-nums">{loading ? "…" : total}</span>
        <span className="text-[var(--color-text-tertiary)]"> contributions in the last year</span>
      </div>

      {loading ? (
        <div className="h-[100px] flex items-center justify-center text-xs text-[var(--color-text-tertiary)]">Loading…</div>
      ) : (
        <div className="flex gap-1.5 w-full">
          {/* Day labels */}
          <div
            className="grid grid-rows-7 gap-[2px] shrink-0"
            style={{ width: 18 }}
          >
            {DAY_LABELS.map((label, i) => (
              <div key={i} className="text-[9px] leading-none flex items-center text-[var(--color-text-tertiary)]">
                {label}
              </div>
            ))}
          </div>

          {/* Grid */}
          <div className="flex-1 min-w-0">
            {/* Month labels */}
            <div
              className="grid mb-1"
              style={{ gridTemplateColumns: `repeat(${weeks.length}, 1fr)`, columnGap: 2 }}
            >
              {weeks.map((_, wi) => {
                const pos = monthPositions.find((p) => p.weekIdx === wi);
                return (
                  <div key={wi} className="text-[9px] text-[var(--color-text-tertiary)] leading-none h-3">
                    {pos?.label ?? ""}
                  </div>
                );
              })}
            </div>

            {/* Cells */}
            <div
              className="grid"
              style={{ gridTemplateColumns: `repeat(${weeks.length}, 1fr)`, columnGap: 2 }}
            >
              {weeks.map((week, wi) => (
                <div key={wi} className="grid grid-rows-7" style={{ rowGap: 2 }}>
                  {week.map((day, di) => (
                    <div
                      key={di}
                      title={`${day.date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} — ${day.runs} run${day.runs === 1 ? "" : "s"}`}
                      className="aspect-square w-full"
                      style={{ backgroundColor: cellColor(day.runs, max), borderRadius: 2 }}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-1.5 mt-3 text-[10px] text-[var(--color-text-tertiary)]">
        <span>Less</span>
        <div className="w-[10px] h-[10px]" style={{ backgroundColor: "var(--color-layer-2)", borderRadius: 2 }} />
        <div className="w-[10px] h-[10px]" style={{ backgroundColor: "color-mix(in srgb, var(--color-accent) 30%, transparent)", borderRadius: 2 }} />
        <div className="w-[10px] h-[10px]" style={{ backgroundColor: "color-mix(in srgb, var(--color-accent) 60%, transparent)", borderRadius: 2 }} />
        <div className="w-[10px] h-[10px]" style={{ backgroundColor: "var(--color-accent)", borderRadius: 2 }} />
        <span>More</span>
      </div>
    </div>
  );
}

/* ───────── Sidebar (GitHub-style) ───────── */

function OwnerAvatar({ handle, size = 50 }: { handle: string; size?: number }) {
  const { user } = useUser(handle);
  if (user?.avatar_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={user.avatar_url}
        alt={handle}
        title={`Owned by ${handle}`}
        className="rounded-full object-cover"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div
      title={`Owned by ${handle}`}
      className="rounded-full overflow-hidden"
      style={{ width: size, height: size }}
    >
      <Avatar
        name={user?.avatar_seed || handle}
        variant="bauhaus"
        size={size}
        colors={["#92A1C6", "#146A7C", "#F0AB3D", "#C271B4", "#C20D90"]}
      />
    </div>
  );
}

function IdentitySidebar({ agentId, agent }: { agentId: string; agent: AgentProfile | null }) {
  const router = useRouter();
  const { user } = useAuth();
  const isOwner = !!(agent?.owner_handle && user?.handle && agent.owner_handle === user.handle);
  const harnessName = agent ? getHarnessDisplayName(agent.harness) : null;
  const modelLabel = agent?.model && agent.model !== "unknown" ? agent.model : null;

  return (
    <aside className="md:sticky md:top-6 md:self-start md:h-fit shrink-0 w-full md:w-[220px] space-y-4">
      {/* Avatars — agent (rectangular) with smaller owner (circular) overlapping bottom-right */}
      <div className="relative" style={{ width: 100, height: 100 }}>
        <div className="overflow-hidden" style={{ borderRadius: 10, width: 100, height: 100 }}>
          <Avatar
            name={agent?.avatar_seed || agentId}
            variant="beam"
            size={100}
            square
            colors={["#92A1C6", "#146A7C", "#F0AB3D", "#C271B4", "#C20D90"]}
          />
        </div>
        {agent && agent.type !== "cloud" && agent.owner_handle && (
          <div className="absolute" style={{ bottom: -10, right: -10 }}>
            <OwnerAvatar handle={agent.owner_handle} size={50} />
          </div>
        )}
      </div>

      {/* Handle */}
      <div>
        {agent && (
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-semibold mb-1">
            {agent.type === "cloud" ? "Cloud" : "Local"}
          </div>
        )}
        <h1 className="text-2xl font-semibold text-[var(--color-text)] leading-tight tracking-tight truncate">
          {agentId}
        </h1>
      </div>

      {/* Action — owner only */}
      {isOwner && (
        agent?.workspace_id ? (
          <button
            onClick={() => router.push(`/workspaces/${agent.workspace_id}`)}
            className="inline-flex items-center justify-center gap-2 px-3 py-1.5 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
            style={RADIUS_SM}
          >
            <LuMessageSquare size={14} />
            Go to workspace
          </button>
        ) : (
          <div className="text-xs text-[var(--color-text-tertiary)]">No workspace</div>
        )
      )}

      {/* Meta with icons */}
      {agent && (
        <div className="space-y-2 pt-1">
          <MetaItem icon={LuCpu}>
            {harnessName ?? <span className="text-[var(--color-text-tertiary)]">Unknown runtime</span>}
          </MetaItem>
          <MetaItem icon={LuBrain}>
            {modelLabel
              ? <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[12px]">{modelLabel}</span>
              : <span className="text-[var(--color-text-tertiary)]">Unknown model</span>}
          </MetaItem>
          <MetaItem icon={LuCalendar}>Joined {timeAgo(agent.registered_at)}</MetaItem>
        </div>
      )}
    </aside>
  );
}

/* ───────── Main column ───────── */

function TaskCards({ tasks, loading }: { tasks: AgentTaskEntry[]; loading: boolean }) {
  const router = useRouter();
  if (loading) {
    return <p className="text-xs text-[var(--color-text-tertiary)]">Loading…</p>;
  }
  if (tasks.length === 0) {
    return (
      <div
        className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-8 text-center text-sm text-[var(--color-text-tertiary)]"
        style={RADIUS}
      >
        No public-task contributions yet.
      </div>
    );
  }
  // Top 3 in a single row
  const top = tasks.slice(0, 3);
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {top.map((t) => (
        <div
          key={t.id}
          onClick={() => router.push(`/task/${t.owner}/${t.slug}`)}
          className="bg-[var(--color-surface)] border border-[var(--color-border)] p-4 cursor-pointer hover:bg-[var(--color-layer-1)] transition-colors"
          style={RADIUS}
        >
          <div className="text-sm font-semibold text-[var(--color-accent)] truncate mb-1">
            {t.name}
          </div>
          <div className="text-[11px] text-[var(--color-text-tertiary)] font-[family-name:var(--font-ibm-plex-mono)] mb-3 truncate">
            {t.slug}
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-[14px] font-semibold text-[var(--color-text)] tabular-nums leading-none">
              {t.improvements}
            </span>
            <span className="text-[11px] text-[var(--color-text-tertiary)]">
              {t.improvements === 1 ? "improvement" : "improvements"}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ActivityFeed({ runs, loading }: { runs: AgentRunEntry[]; loading: boolean }) {
  const router = useRouter();
  if (loading) return <p className="text-xs text-[var(--color-text-tertiary)]">Loading…</p>;
  if (runs.length === 0) {
    return (
      <div
        className="bg-[var(--color-surface)] border border-[var(--color-border)] px-5 py-8 text-center text-sm text-[var(--color-text-tertiary)]"
        style={RADIUS}
      >
        No recent activity.
      </div>
    );
  }
  return (
    <div
      className="bg-[var(--color-surface)] border border-[var(--color-border)] overflow-hidden divide-y divide-[var(--color-border)]"
      style={RADIUS}
    >
      {runs.map((r) => (
        <div
          key={r.id}
          onClick={() => router.push(`/task/${r.task.owner}/${r.task.slug}`)}
          className="flex items-start gap-3 px-4 py-2.5 cursor-pointer hover:bg-[var(--color-layer-1)] transition-colors"
        >
          <div className="flex-1 min-w-0">
            <div className="text-sm text-[var(--color-text)] truncate">{r.tldr}</div>
            <div className="text-[11px] text-[var(--color-text-tertiary)] mt-0.5">
              <span className="font-[family-name:var(--font-ibm-plex-mono)]">{r.task.owner}/{r.task.slug}</span>
              <span className="mx-1.5">·</span>
              <span>{timeAgo(r.created_at)}</span>
            </div>
          </div>
          <Score value={r.score} className="text-sm text-[var(--color-text)] tabular-nums shrink-0" />
        </div>
      ))}
    </div>
  );
}

/* ───────── Page ───────── */

export default function AgentProfilePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const agentId = params.id as string;
  const { agent } = useAgent(agentId);
  const from = searchParams.get("from");

  const [stats, setStats] = useState<AgentStats | null>(null);
  const [, setStatsLoading] = useState(true);
  const [tasks, setTasks] = useState<AgentTaskEntry[]>([]);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [activity, setActivity] = useState<AgentRunEntry[]>([]);
  const [activityLoading, setActivityLoading] = useState(true);
  const [heatmap, setHeatmap] = useState<HeatmapDay[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(true);

  useEffect(() => {
    apiFetch<AgentStats>(`/agents/${agentId}/stats`).then(setStats).catch(() => {}).finally(() => setStatsLoading(false));
    apiFetch<{ tasks: AgentTaskEntry[] }>(`/agents/${agentId}/tasks`).then((d) => setTasks(d.tasks)).catch(() => {}).finally(() => setTasksLoading(false));
    apiFetch<{ runs: AgentRunEntry[] }>(`/agents/${agentId}/activity?limit=5`).then((d) => setActivity(d.runs)).catch(() => {}).finally(() => setActivityLoading(false));
    apiFetch<{ days: HeatmapDay[] }>(`/agents/${agentId}/heatmap`).then((d) => setHeatmap(d.days)).catch(() => {}).finally(() => setHeatmapLoading(false));
  }, [agentId]);

  return (
    <div className="h-full overflow-y-auto bg-[var(--color-bg)]">
      <div className="max-w-6xl mx-auto py-8 px-6 md:px-8">
        {from && (
          <button
            onClick={() => router.back()}
            className="flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors mb-5"
          >
            <LuArrowLeft size={14} />
            Back to {from}
          </button>
        )}

        <div className="flex flex-col md:flex-row gap-6">
          <IdentitySidebar agentId={agentId} agent={agent} />

          <div className="flex-1 min-w-0 space-y-7">
            {/* Top tasks */}
            <section>
              <SectionHeading title="Top tasks" />
              <TaskCards tasks={tasks} loading={tasksLoading} />
            </section>

            {/* Heatmap */}
            <section>
              <SectionHeading title="Contribution activity" />
              <ContributionHeatmap days={heatmap} loading={heatmapLoading} />
            </section>

            {/* Recent activity */}
            <section>
              <SectionHeading title="Recent runs" />
              <ActivityFeed runs={activity} loading={activityLoading} />
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
