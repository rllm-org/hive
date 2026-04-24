"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode, type ComponentType } from "react";
import { LuHash, LuX, LuMessageSquare, LuChevronRight, LuInfo, LuActivity, LuTerminal, LuPencil, LuPlus, LuBot, LuFolder, LuMonitor, LuTrophy, LuFileText, LuSettings, LuUsers, LuBox, LuChartNoAxesCombined } from "react-icons/lu";
import { useRouter, usePathname } from "next/navigation";
import { useAgent, useChannels, useWorkspaceChannels, useWorkspaceMessages, useWorkspaceAgentsList, useWorkspaceThread, useMessages, useThread, useTaskAgents, type Channel, type Message, type ThreadParticipant, type AgentSummary } from "@/hooks/use-chat";
import { getAgentColor } from "@/lib/agent-colors";
import { Avatar } from "@/components/shared";
import BoringAvatar from "boring-avatars";
import { AgentChat } from "@/components/shared/agent-chat";
import { AgentTabBar } from "@/components/shared/agent-tab-bar";
import { FileExplorer } from "@/components/shared/file-explorer";
import { AgentSelector } from "@/components/shared/agent-selector";
import { useWorkspaceAgents, type ChatMessage } from "@/hooks/use-workspace-agent";
import type { FsTreeNode } from "@/hooks/use-workspace-files";
import { isOnline } from "@/lib/time";
import { RenderMessage } from "@/components/chat/render-message";
import { ResizeHandle, useResizableWidth } from "@/components/shared/resize-handle";
import { AgentLink, AgentProfilePanel, UserLink, UserProfilePanel, type ProfileTarget } from "@/components/chat/agent-profile";
import { MessageInput, EditMessageInline } from "@/components/chat/message-input";
import { CreateWorkspaceDialog } from "@/components/chat/create-workspace-dialog";
import { Modal, ModalHeader, ModalBody } from "@/components/shared/modal";
import { useAuth } from "@/lib/auth";
import useSWR from "swr";
import { apiFetch, apiPatch, apiPostJson, apiDelete } from "@/lib/api";
import { SDK_BASE } from "@/lib/sdk";

interface ChatPanelProps {
  taskPath: string;
  sidebarHeader?: ReactNode;
  aboutContent?: ReactNode;
  runsContent?: ReactNode;
  sandboxContent?: ReactNode;
  /** When true, skip the outer chrome (padding, rounded corners, spacer) — used when the parent already provides the blue background. */
  embedded?: boolean;
  /** When provided, replaces the entire content area (right of sidebar) with this node. Sidebar still renders. */
  contentOverride?: ReactNode;
  /** URL-driven workspace selection — overrides localStorage */
  activeWorkspace?: string;
  /** Team slug for URL navigation (e.g. user handle) */
  team?: string;
  /** "workspace" shows tabs (Agents/Messages/Files/etc), "task" shows messages directly */
  mode?: "workspace" | "task";
  /** Workspace ID for agent creation (workspace mode only) */
  workspaceId?: number;
}

const HIVE_SIDEBAR_BG = "#2a5583"; // darker blue sidebar
const TASK_SIDEBAR_BG = "#3a3f47"; // gray sidebar for task views
const AgentMapContext = createContext<Map<string, { type: string; avatar_seed: string | null }>>(new Map());
const GROUP_GAP_MS = 5 * 60 * 1000;

/* ────────────── System views (not channels — hardcoded sidebar surfaces) ────────────── */

type SystemView = "about" | "runs" | "sandbox";

interface SystemViewDef {
  id: SystemView;
  label: string;
  Icon: ComponentType<{ size?: number; className?: string }>;
}

const SYSTEM_VIEWS: SystemViewDef[] = [
  { id: "sandbox", label: "Sandbox", Icon: LuTerminal },
];

const TASK_SYSTEM_VIEWS: SystemViewDef[] = [
  { id: "about", label: "About", Icon: LuInfo },
  { id: "runs", label: "Runs", Icon: LuActivity },
  { id: "sandbox", label: "Sandbox", Icon: LuTerminal },
];

type Selection =
  | { kind: "system"; view: SystemView }
  | { kind: "channel"; name: string };

function selectionKey(taskPath: string): string {
  return `hive:chat:selection:${taskPath}`;
}

function loadSelection(taskPath: string): Selection | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(selectionKey(taskPath));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.kind === "system" && ["about", "runs", "sandbox"].includes(parsed.view)) {
      return parsed as Selection;
    }
    if (parsed?.kind === "channel" && typeof parsed.name === "string") {
      return parsed as Selection;
    }
  } catch {}
  return null;
}

function saveSelection(taskPath: string, sel: Selection): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(selectionKey(taskPath), JSON.stringify(sel));
  }
}

export function ChatPanel({ taskPath, sidebarHeader, aboutContent, runsContent, sandboxContent, embedded, contentOverride, activeWorkspace, team, mode = "workspace", workspaceId: workspaceIdProp }: ChatPanelProps) {
  // In workspace mode, fetch real workspaces; in task mode, fetch task channels
  const taskChannelsHook = useChannels(mode === "task" ? taskPath : "");
  const workspaceChannelsHook = useWorkspaceChannels();
  const isWorkspaceMode = mode === "workspace";
  const { channels, loading: channelsLoading, refetch: refetchChannels } = isWorkspaceMode
    ? workspaceChannelsHook
    : taskChannelsHook;
  // Resolve workspaceId from the active workspace name
  const workspaceId = workspaceIdProp ?? (isWorkspaceMode
    ? workspaceChannelsHook.workspaces.find((w) => w.name === activeWorkspace)?.id
    : undefined);
  const { agents: taskAgents } = useTaskAgents(mode === "task" ? taskPath : "");
  const { agents: wsAgents, refetch: refetchWsAgents } = useWorkspaceAgentsList(isWorkspaceMode ? (workspaceId ?? null) : null);
  const displayAgents = isWorkspaceMode ? wsAgents : taskAgents;
  const { user } = useAuth();
  const router = useRouter();
  const [createChannelOpen, setCreateChannelOpen] = useState(false);
  const [agentCreatedId, setAgentCreatedId] = useState<string | null>(null);
  const showSandbox = sandboxContent != null;
  const visibleSystemViews = useMemo(
    () => {
      const base = mode === "task" ? TASK_SYSTEM_VIEWS : SYSTEM_VIEWS;
      return base.filter((v) => v.id !== "sandbox" || showSandbox);
    },
    [showSandbox, mode],
  );

  const [selection, setSelection] = useState<Selection>(() => {
    if (activeWorkspace) return { kind: "channel", name: activeWorkspace };
    const saved = loadSelection(taskPath);
    if (saved) return saved;
    if (mode === "task") return { kind: "system", view: "about" };
    return { kind: "channel", name: "general" };
  });
  const [activeThreadTs, setActiveThreadTs] = useState<string | null>(null);
  const [activeProfile, setActiveProfile] = useState<ProfileTarget | null>(null);

  // Sync selection when activeWorkspace prop changes (URL navigation)
  useEffect(() => {
    if (activeWorkspace) {
      setSelection({ kind: "channel", name: activeWorkspace });
      setActiveThreadTs(null);
    }
  }, [activeWorkspace]);

  // If saved selection is no longer valid (channel deleted, sandbox revoked), fall back
  const effectiveSelection: Selection = useMemo(() => {
    if (selection.kind === "system") {
      if (selection.view === "sandbox" && !showSandbox) {
        return channels.length > 0 ? { kind: "channel", name: channels[0].name } : { kind: "channel", name: "general" };
      }
      return selection;
    }
    if (channels.some((c) => c.name === selection.name)) {
      return selection;
    }
    return channels.length > 0 ? { kind: "channel", name: channels[0].name } : { kind: "channel", name: "general" };
  }, [selection, channels, showSandbox]);

  // When on /{team} without a workspace slug, redirect to /{team}/{first-workspace}
  useEffect(() => {
    if (team && !activeWorkspace && !channelsLoading && channels.length > 0) {
      const target = effectiveSelection.kind === "channel" ? effectiveSelection.name : channels[0].name;
      router.replace(`/${team}/${target}`);
    }
  }, [team, activeWorkspace, channelsLoading, channels, effectiveSelection, router]);

  const handleSelectSystem = useCallback(
    (view: SystemView) => {
      const next: Selection = { kind: "system", view };
      setSelection(next);
      setActiveThreadTs(null);
      setActiveProfile(null);
      saveSelection(taskPath, next);
    },
    [taskPath],
  );
  const handleSelectChannel = useCallback(
    (name: string) => {
      const next: Selection = { kind: "channel", name };
      setSelection(next);
      setActiveThreadTs(null);
      saveSelection(taskPath, next);
      if (team) {
        router.push(`/${team}/${name}`);
      }
    },
    [taskPath, team, router],
  );

  const sidebarResize = useResizableWidth({
    initial: 240,
    min: 180,
    max: 420,
    edge: "right",
    storageKey: "hive:chat:sidebarWidth",
  });
  const threadResize = useResizableWidth({
    initial: 420,
    min: 320,
    max: 720,
    edge: "left",
    storageKey: "hive:chat:threadWidth",
  });
  const profileResize = useResizableWidth({
    initial: 400,
    min: 300,
    max: 1200,
    edge: "left",
    storageKey: "hive:chat:profileWidth",
  });

  const handleOpenThread = useCallback((ts: string) => {
    setActiveThreadTs(ts);
    setActiveProfile(null);
  }, []);
  const handleOpenProfile = useCallback((target: ProfileTarget) => {
    setActiveProfile(target);
    setActiveThreadTs(null);
  }, []);

  const agentMap = useMemo(() => new Map(displayAgents.map((a) => [a.id, { type: a.type, avatar_seed: a.avatar_seed }])), [displayAgents]);

  return (
    <AgentMapContext.Provider value={agentMap}>
    <div className={`flex-1 min-h-0 flex flex-col overflow-hidden ${embedded ? "" : "pt-1 bg-[var(--color-surface)]"}`}>
      {/* Inner blue chrome — top + left only; right and bottom continue to the page edge */}
      <div
        className={`flex-1 min-h-0 flex flex-col overflow-hidden ${embedded ? "" : "rounded-tl-2xl"}`}
        style={{ backgroundColor: mode === "task" ? TASK_SIDEBAR_BG : HIVE_SIDEBAR_BG }}
      >
        {/* Thin horizontal top bar — same hive blue, visually one piece with the sidebar */}
        {!embedded && <div className="shrink-0 h-[10px] w-full" />}

        {/* Sidebar + content */}
        <div className="flex-1 min-h-0 flex">
          <ChannelSidebar
            header={sidebarHeader}
            systemViews={visibleSystemViews}
            channels={channels}
            agents={displayAgents}
            selection={contentOverride ? { kind: "channel", name: "" } : effectiveSelection}
            loading={channelsLoading}
            onSelectSystem={handleSelectSystem}
            onSelectChannel={handleSelectChannel}
            onCreateChannel={user ? () => setCreateChannelOpen(true) : undefined}
            onOpenProfile={handleOpenProfile}
            width={sidebarResize.width}
            mode={mode}
            workspaceId={workspaceId}
            onAgentCreated={(agentId) => { refetchWsAgents(); if (agentId) setAgentCreatedId(agentId); }}
          />
          <ResizeHandle
            isDragging={sidebarResize.isDragging}
            onMouseDown={sidebarResize.onMouseDown}
            variant="dark"
          />
          {contentOverride ? (
            <div className="flex-1 min-w-0 overflow-hidden rounded-tl-xl">
              {contentOverride}
            </div>
          ) : (
          <>
          {isWorkspaceMode && channels.length === 0 ? (
            <div className="flex-1 min-w-0 flex flex-col items-center justify-center bg-[var(--color-surface)] rounded-tl-xl">
              <LuFolder size={32} className="text-[var(--color-text-tertiary)] mb-3" />
              <p className="text-sm font-medium text-[var(--color-text-secondary)]">No workspaces yet</p>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">Create one from the sidebar to get started.</p>
            </div>
          ) : (
          <ChannelMain
            taskPath={taskPath}
            selection={effectiveSelection}
            onOpenThread={handleOpenThread}
            onOpenProfile={handleOpenProfile}
            activeThreadTs={activeThreadTs}
            aboutContent={aboutContent}
            runsContent={runsContent}
            sandboxContent={sandboxContent}
            embedded={embedded}
            agents={displayAgents}
            mode={mode}
            workspaceId={workspaceId}
            autoSelectAgentId={agentCreatedId}
            onAgentAutoSelected={() => setAgentCreatedId(null)}
          />
          )}
          {activeThreadTs && effectiveSelection.kind === "channel" && (
            <>
              <ResizeHandle
                isDragging={threadResize.isDragging}
                onMouseDown={threadResize.onMouseDown}
              />
              <ThreadPanel
                taskPath={taskPath}
                channelName={effectiveSelection.name}
                ts={activeThreadTs}
                onClose={() => setActiveThreadTs(null)}
                onOpenProfile={handleOpenProfile}
                width={threadResize.width}
                workspaceId={workspaceId}
              />
            </>
          )}
          {activeProfile && effectiveSelection.kind === "channel" && (
            <>
              <ResizeHandle
                isDragging={profileResize.isDragging}
                onMouseDown={profileResize.onMouseDown}
              />
              {activeProfile.kind === "agent" ? (
                <AgentProfilePanel
                  agentId={activeProfile.id}
                  onClose={() => setActiveProfile(null)}
                  width={profileResize.width}
                  workspaceId={workspaceId}
                />
              ) : (
                <UserProfilePanel
                  handle={activeProfile.handle}
                  onClose={() => setActiveProfile(null)}
                  width={profileResize.width}
                />
              )}
            </>
          )}
          </>
          )}
      </div>
      </div>
      <CreateWorkspaceDialog
        open={createChannelOpen}
        mode={isWorkspaceMode ? "workspace" : "task"}
        taskPath={taskPath}
        onClose={() => setCreateChannelOpen(false)}
        onCreated={(name) => {
          refetchChannels();
          handleSelectChannel(name);
        }}
      />
    </div>
    </AgentMapContext.Provider>
  );
}

/* ──────────────────────────────────────────────── Sidebar ──────────────────────────────────────────────── */

type SidebarMode = "workspace" | "task";

function ChannelSidebar({
  header,
  systemViews,
  channels,
  agents,
  selection,
  loading,
  onSelectSystem,
  onSelectChannel,
  onCreateChannel,
  onOpenProfile,
  width,
  mode: rawMode,
  workspaceId,
  onAgentCreated,
}: {
  header?: ReactNode;
  systemViews: SystemViewDef[];
  channels: Channel[];
  agents: AgentSummary[];
  selection: Selection;
  loading: boolean;
  onSelectSystem: (view: SystemView) => void;
  onSelectChannel: (name: string) => void;
  onCreateChannel?: () => void;
  onOpenProfile: (target: ProfileTarget) => void;
  width: number;
  mode?: SidebarMode;
  workspaceId?: number;
  onAgentCreated?: (agentId?: string) => void;
}) {
  const mode: SidebarMode = rawMode ?? "workspace";
  // Sort agents: online first, then by last_seen_at desc
  const sortedAgents = useMemo(() => {
    return [...agents].sort((a, b) => {
      const aOnline = isOnline(a.last_seen_at);
      const bOnline = isOnline(b.last_seen_at);
      if (aOnline !== bOnline) return aOnline ? -1 : 1;
      const aTime = a.last_seen_at ? new Date(a.last_seen_at).getTime() : 0;
      const bTime = b.last_seen_at ? new Date(b.last_seen_at).getTime() : 0;
      return bTime - aTime;
    });
  }, [agents]);
  const { user: authUser } = useAuth();
  const sidebarRouter = useRouter();
  const sidebarPathname = usePathname();

  // Task mode: simpler sidebar with system views + channels (no Workspaces/Members sections)
  if (mode === "task") {
    return (
      <aside
        className="hidden md:flex flex-col shrink-0"
        style={{ width, backgroundColor: TASK_SIDEBAR_BG }}
      >
        {header && <div className="shrink-0">{header}</div>}
        <div className="flex-1 overflow-y-auto pt-2 pb-3">
          {/* System views (About, Runs, Sandbox) — same indentation as channels */}
          <div className="space-y-0.5">
            {systemViews.map((v) => (
              <SidebarSystemItem
                key={v.id}
                label={v.label}
                Icon={v.Icon}
                isActive={selection.kind === "system" && selection.view === v.id}
                onClick={() => onSelectSystem(v.id)}
                indent="pl-[26px]"
              />
            ))}
          </div>
          {/* Divider */}
          <div className="mx-4 my-3 h-px bg-white/15" />
          {/* Channels section header (task mode) */}
          <div className="group/header flex w-[calc(100%-16px)] items-center gap-2.5 h-[30px] mx-2 pl-2 pr-2 text-[15px] text-white/75">
            <LuHash size={14} className="shrink-0 opacity-80" />
            <span className="truncate flex-1">Channels</span>
            {onCreateChannel && (
              <button
                onClick={onCreateChannel}
                aria-label="Create channel"
                title="Create channel"
                className="opacity-0 group-hover/header:opacity-100 w-5 h-5 flex items-center justify-center rounded text-white/70 hover:bg-white/10 hover:text-white transition-all"
              >
                <LuPlus size={14} />
              </button>
            )}
          </div>
          {/* Channel items */}
          <div className="space-y-0.5">
            {loading && channels.length === 0 ? (
              <div className="px-6 py-2 text-[13px] text-white/50">Loading…</div>
            ) : channels.length === 0 ? (
              <div className="px-6 py-2 text-[13px] text-white/50">No channels.</div>
            ) : (
              channels.map((c) => (
                <SidebarChannelItem
                  key={c.id}
                  name={c.name}
                  isActive={selection.kind === "channel" && selection.name === c.name}
                  onClick={() => onSelectChannel(c.name)}
                  icon={LuHash}
                />
              ))
            )}
          </div>
        </div>
      </aside>
    );
  }

  // Workspace mode: full sidebar with Workspaces + Members
  return (
    <aside
      className="hidden md:flex flex-col shrink-0"
      style={{ width, backgroundColor: HIVE_SIDEBAR_BG }}
    >
      {/* User handle */}
      <div className="shrink-0 h-[48px] px-5 pt-2 flex items-center">
        <span className="text-[20px] font-bold text-white truncate">{authUser?.handle ?? "Hive"}</span>
      </div>
      {header && <div className="shrink-0">{header}</div>}
      <div className="flex-1 overflow-y-auto pt-2 pb-3">
        {/* System views */}
        <div className="space-y-0.5">
          {systemViews.map((v) => (
            <SidebarSystemItem
              key={v.id}
              label={v.label}
              Icon={v.Icon}
              isActive={selection.kind === "system" && selection.view === v.id}
              onClick={() => onSelectSystem(v.id)}
            />
          ))}
        </div>
        {/* Workspaces section header */}
        <div className="group/header flex w-[calc(100%-16px)] items-center gap-2.5 h-[30px] mx-2 pl-2 pr-2 text-[15px] text-white/75">
          <LuMonitor size={14} className="shrink-0 opacity-80" />
          <span className="truncate flex-1">Workspaces</span>
          {onCreateChannel && (
            <button
              onClick={onCreateChannel}
              aria-label="Create workspace"
              title="Create workspace"
              className="opacity-0 group-hover/header:opacity-100 w-5 h-5 flex items-center justify-center rounded text-white/70 hover:bg-white/10 hover:text-white transition-all"
            >
              <LuPlus size={14} />
            </button>
          )}
        </div>
        {/* Chat channel items */}
        <div className="space-y-0.5">
          {loading && channels.length === 0 ? (
            <div className="px-6 py-2 text-[13px] text-white/50">Loading…</div>
          ) : channels.length === 0 ? (
            <div className="px-6 py-2 text-[13px] text-white/50">No workspaces.</div>
          ) : (
            channels.map((c) => (
              <SidebarChannelItem
                key={c.id}
                name={c.name}
                isActive={selection.kind === "channel" && selection.name === c.name}
                onClick={() => onSelectChannel(c.name)}
              />
            ))
          )}
        </div>
        {/* Divider */}
        <div className="mx-4 my-4 h-px bg-white/15" />
        {/* Members section — users with their agents nested underneath */}
        <MembersSectionHeader workspaceId={workspaceId} onAgentCreated={onAgentCreated} />
        <UserAgentsGroup user={authUser} agents={sortedAgents} onOpenProfile={onOpenProfile} sidebarRouter={sidebarRouter} />
      </div>
    </aside>
  );
}

const _ADJ = ["swift","bold","calm","bright","keen","warm","cool","sharp","gentle","witty","brave","vivid","kind","agile","lucid"];
const _NOUN = ["phoenix","falcon","atlas","comet","cipher","horizon","pulse","spark","prism","orbit","nova","ember","drift","quill","sage"];
function _randomHandle() {
  const a = _ADJ[Math.floor(Math.random() * _ADJ.length)];
  const n = _NOUN[Math.floor(Math.random() * _NOUN.length)];
  return `${a}-${n}`;
}

function MembersSectionHeader({ workspaceId, onAgentCreated }: { workspaceId?: number; onAgentCreated?: (agentId?: string) => void }) {
  const [showModal, setShowModal] = useState(false);
  const [tab, setTab] = useState<"user" | "agent">("agent");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [agentName, setAgentName] = useState("");
  const [agentRole, setAgentRole] = useState("");
  const [agentDesc, setAgentDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const resetForm = () => {
    setAgentName(_randomHandle());
    setAgentRole("");
    setAgentDesc("");
    setCreateError("");
    setShowCreateForm(false);
  };

  const handleCreate = async () => {
    if (!workspaceId || !agentName.trim()) return;
    setCreating(true);
    setCreateError("");
    const name = agentName.trim().toLowerCase();
    try {
      const result = await apiPostJson<{ id: string }>(`/workspaces/${workspaceId}/agents`, {
        name,
        role: agentRole.trim() || undefined,
        description: agentDesc.trim() || undefined,
      });
      resetForm();
      setShowModal(false);
      onAgentCreated?.(result.id);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create agent");
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <div className="group/members flex w-[calc(100%-16px)] items-center gap-2.5 h-[30px] mx-2 pl-2 pr-2 text-[15px] text-white/75">
        <LuUsers size={14} className="shrink-0 opacity-80" />
        <span className="truncate flex-1">Members</span>
        <button
          onClick={() => { setShowModal(true); setTab("agent"); resetForm(); }}
          className="w-5 h-5 flex items-center justify-center rounded text-white/70 hover:bg-white/10 hover:text-white transition-all opacity-0 group-hover/members:opacity-100"
        >
          <LuPlus size={14} />
        </button>
      </div>
      <Modal open={showModal} onClose={() => setShowModal(false)} zIndex={10000}>
        <ModalHeader onClose={() => setShowModal(false)}>Add Members</ModalHeader>

        {/* Tabs */}
        <div className="flex border-b border-[var(--color-border)]">
          <button
            onClick={() => setTab("agent")}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              tab === "agent"
                ? "border-[var(--color-accent)] text-[var(--color-text)]"
                : "border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
            }`}
          >
            <LuBot size={14} />
            Invite Agent
          </button>
          <button
            onClick={() => setTab("user")}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              tab === "user"
                ? "border-[var(--color-accent)] text-[var(--color-text)]"
                : "border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
            }`}
          >
            <LuUsers size={14} />
            Invite User
          </button>
        </div>

        <ModalBody>
          {tab === "user" && (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <LuUsers size={32} className="text-[var(--color-text-tertiary)] mb-3" />
              <p className="text-sm font-medium text-[var(--color-text-secondary)]">Coming soon</p>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">User invites will be supported in a future update.</p>
            </div>
          )}
          {tab === "agent" && !showCreateForm && (
            <div className="space-y-3">
              <div className="w-full flex items-center gap-3 p-3 border border-[var(--color-border)] opacity-40 cursor-not-allowed text-left">
                <LuBot size={20} className="text-[var(--color-text-secondary)] shrink-0" />
                <div>
                  <div className="text-sm font-medium text-[var(--color-text)]">Add existing agent</div>
                  <div className="text-xs text-[var(--color-text-tertiary)]">Coming soon</div>
                </div>
              </div>
              <button
                onClick={() => { setAgentName(_randomHandle()); setShowCreateForm(true); }}
                className="w-full flex items-center gap-3 p-3 border border-[var(--color-border)] hover:bg-[var(--color-layer-1)] transition-colors text-left"
              >
                <LuPlus size={20} className="text-[var(--color-text-secondary)] shrink-0" />
                <div>
                  <div className="text-sm font-medium text-[var(--color-text)]">Create new agent</div>
                </div>
              </button>
            </div>
          )}
          {tab === "agent" && showCreateForm && (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Agent Handle</label>
                <input
                  type="text"
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                  placeholder="e.g. claude-orchestrator"
                  className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
                  style={{ outline: "none", boxShadow: "none" }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Agent Role</label>
                <input
                  type="text"
                  value={agentRole}
                  onChange={(e) => setAgentRole(e.target.value)}
                  placeholder="e.g. Orchestrator, Reviewer, Coder"
                  className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
                  style={{ outline: "none", boxShadow: "none" }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Agent Description</label>
                <textarea
                  rows={3}
                  value={agentDesc}
                  onChange={(e) => setAgentDesc(e.target.value)}
                  placeholder="What does this agent do?"
                  className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] resize-none"
                  style={{ outline: "none", boxShadow: "none" }}
                />
              </div>
              {createError && <p className="text-xs text-red-500">{createError}</p>}
              <button
                onClick={handleCreate}
                disabled={creating || !agentName.trim() || !workspaceId}
                className="w-full py-2 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
              >
                {creating ? "Creating..." : "Create Agent"}
              </button>
            </div>
          )}
        </ModalBody>
      </Modal>
    </>
  );
}

function UserAgentsGroup({ user, agents, onOpenProfile, sidebarRouter }: { user: { handle?: string | null; avatar_url?: string | null } | null; agents: AgentSummary[]; onOpenProfile: (target: ProfileTarget) => void; sidebarRouter: ReturnType<typeof useRouter> }) {
  const [expanded, setExpanded] = useState(true);
  const handle = user?.handle ?? "user";
  return (
    <div className="space-y-0.5">
      <div className={`${SIDEBAR_ITEM_BASE} pl-5 text-white group/user`}>
        <button
          onClick={() => onOpenProfile({ kind: "user", handle })}
          className="flex items-center gap-2.5 flex-1 min-w-0"
        >
          <Avatar id={handle} seed={null} imageUrl={user?.avatar_url} kind="user" size="xs" />
          <span className="truncate">{handle}</span>
        </button>
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-5 h-5 flex items-center justify-center rounded opacity-0 group-hover/user:opacity-100 text-white/60 hover:text-white hover:bg-white/10 transition-all"
        >
          <LuChevronRight size={12} className={`transition-transform ${expanded ? "rotate-90" : ""}`} />
        </button>
      </div>
      {expanded && agents.map((a) => (
        <button
          key={a.id}
          onClick={() => onOpenProfile({ kind: "agent", id: a.id })}
          className={`${SIDEBAR_ITEM_BASE} pl-9 text-[13px] text-white/75 hover:bg-white/10 hover:text-white`}
        >
          <Avatar id={a.id} seed={a.avatar_seed} kind="agent" size="xs" />
          <span className={`truncate ${isOnline(a.last_seen_at) ? "text-white" : ""}`}>{a.id}</span>
        </button>
      ))}
    </div>
  );
}

const SIDEBAR_ITEM_BASE =
  "flex w-[calc(100%-16px)] items-center gap-2.5 h-[30px] mx-2 pr-2 text-[15px] text-left rounded-[6px] transition-colors";

function SidebarSystemItem({
  label,
  Icon,
  isActive,
  onClick,
  indent = "pl-4",
}: {
  label: string;
  Icon: ComponentType<{ size?: number; className?: string }>;
  isActive: boolean;
  onClick: () => void;
  indent?: string;
}) {
  if (isActive) {
    return (
      <button
        onClick={onClick}
        className={`${SIDEBAR_ITEM_BASE} ${indent} bg-white text-[#1D1C1D] font-bold`}
      >
        <Icon size={14} className="shrink-0 opacity-80" />
        <span className="truncate">{label}</span>
      </button>
    );
  }
  return (
    <button
      onClick={onClick}
      className={`${SIDEBAR_ITEM_BASE} ${indent} text-white/75 hover:bg-white/10 hover:text-white`}
    >
      <Icon size={14} className="shrink-0 opacity-80" />
      <span className="truncate">{label}</span>
    </button>
  );
}

function SidebarChannelItem({
  name,
  isActive,
  onClick,
  icon: IconOverride,
}: {
  name: string;
  isActive: boolean;
  onClick: () => void;
  icon?: ComponentType<{ size?: number; className?: string }>;
}) {
  const Icon = IconOverride ?? LuFolder;
  if (isActive) {
    return (
      <button
        onClick={onClick}
        className={`${SIDEBAR_ITEM_BASE} pl-5 bg-white text-[#1D1C1D] font-bold`}
      >
        <Icon size={14} className="shrink-0 opacity-80" />
        <span className="truncate">{name}</span>
      </button>
    );
  }
  return (
    <button
      onClick={onClick}
      className={`${SIDEBAR_ITEM_BASE} pl-5 text-white/75 hover:bg-white/10 hover:text-white`}
    >
      <Icon size={14} className="shrink-0 opacity-80" />
      <span className="truncate">{name}</span>
    </button>
  );
}

const AGENT_SIDEBAR_LIMIT = 10;

function AgentsSidebarSection({ agents, onOpenProfile }: { agents: AgentSummary[]; onOpenProfile: (target: ProfileTarget) => void }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? agents : agents.slice(0, AGENT_SIDEBAR_LIMIT);
  const hasMore = agents.length > AGENT_SIDEBAR_LIMIT;

  return (
    <>
      <div className="flex w-[calc(100%-16px)] items-center gap-2.5 h-[30px] mx-2 pl-2 pr-2 text-[15px] text-white/75">
        <LuBot size={14} className="shrink-0 opacity-80" />
        <span className="truncate flex-1">Agents</span>
      </div>
      <div className="space-y-0.5">
        {visible.map((a) => (
          <SidebarAgentItem
            key={a.id}
            agent={a}
            onClick={() => onOpenProfile({ kind: "agent", id: a.id })}
          />
        ))}
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className={`${SIDEBAR_ITEM_BASE} pl-5 text-white/50 hover:bg-white/10 hover:text-white/75`}
          >
            <span className="truncate">
              {expanded ? "Show less" : `Show ${agents.length - AGENT_SIDEBAR_LIMIT} more`}
            </span>
          </button>
        )}
      </div>
    </>
  );
}

function SidebarAgentItem({ agent, onClick }: { agent: AgentSummary; onClick: () => void }) {
  const online = isOnline(agent.last_seen_at);
  return (
    <button
      onClick={onClick}
      className={`${SIDEBAR_ITEM_BASE} pl-5 text-[13px] text-white/75 hover:bg-white/10 hover:text-white`}
      title={[agent.role, agent.description].filter(Boolean).join(" — ") || agent.id}
    >
      <div className="relative shrink-0">
        <Avatar id={agent.id} seed={agent.avatar_seed} kind="agent" size="xs" />
        <span className="absolute -bottom-0.5 -right-0.5">
          <span className={`block w-2.5 h-2.5 rounded-full border-[1.5px] ${
            online ? "bg-green-500 border-[#2a5583]" : "bg-[#3b6ea5] border-white/40"
          }`} />
        </span>
      </div>
      <div className="flex flex-col min-w-0 flex-1">
        <span className={`truncate text-[13px] leading-tight ${online ? "text-white" : ""}`}>{agent.id}</span>
        {agent.role && (
          <span className="truncate text-[10px] leading-tight text-white/40">{agent.role}</span>
        )}
      </div>
    </button>
  );
}

/* ──────────────────────────────────────────────── Main timeline ──────────────────────────────────────────────── */

function ChannelMain({
  taskPath,
  selection,
  activeThreadTs,
  onOpenThread,
  onOpenProfile,
  aboutContent,
  runsContent,
  sandboxContent,
  embedded,
  agents,
  mode = "workspace",
  workspaceId,
  autoSelectAgentId,
  onAgentAutoSelected,
}: {
  taskPath: string;
  selection: Selection;
  activeThreadTs: string | null;
  onOpenThread: (ts: string) => void;
  onOpenProfile: (target: ProfileTarget) => void;
  aboutContent?: ReactNode;
  runsContent?: ReactNode;
  sandboxContent?: ReactNode;
  embedded?: boolean;
  agents?: AgentSummary[];
  mode?: "workspace" | "task";
  workspaceId?: number;
  autoSelectAgentId?: string | null;
  onAgentAutoSelected?: () => void;
}) {
  const rounding = "rounded-tl-xl";
  if (selection.kind === "system") {
    let content: ReactNode;
    if (selection.view === "about") content = aboutContent ?? <SystemViewEmpty view="about" />;
    else if (selection.view === "runs") content = runsContent ?? <SystemViewEmpty view="runs" />;
    else content = sandboxContent ?? <SystemViewEmpty view="sandbox" />;
    return (
      <div className={`flex-1 min-w-0 flex flex-col bg-[var(--color-surface)] overflow-hidden ${rounding}`}>
        {content}
      </div>
    );
  }
  return (
    <ChatChannelView
      taskPath={taskPath}
      channelName={selection.name}
      activeThreadTs={activeThreadTs}
      onOpenThread={onOpenThread}
      onOpenProfile={onOpenProfile}
      embedded={embedded}
      agents={agents}
      mode={mode}
      workspaceId={workspaceId}
      autoSelectAgentId={autoSelectAgentId}
      onAgentAutoSelected={onAgentAutoSelected}
    />
  );
}

function SystemViewEmpty({ view }: { view: SystemView }) {
  return (
    <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-secondary)]">
      No {view} content available.
    </div>
  );
}

type WorkspaceTab = "agents" | "messages" | "files" | "tasks" | "artifacts" | "settings";

const WORKSPACE_TABS: { id: WorkspaceTab; label: string; Icon: ComponentType<{ size?: number; className?: string }> }[] = [
  { id: "agents", label: "Agents", Icon: LuBot },
  { id: "messages", label: "Messages", Icon: LuMessageSquare },
  { id: "artifacts", label: "Artifacts", Icon: LuBox },
  { id: "files", label: "Files", Icon: LuFileText },
  { id: "tasks", label: "Tasks", Icon: LuChartNoAxesCombined },
  { id: "settings", label: "Settings", Icon: LuSettings },
];

function ChatChannelView({
  taskPath,
  channelName,
  activeThreadTs,
  onOpenThread,
  onOpenProfile,
  embedded,
  agents,
  mode = "workspace",
  workspaceId,
  autoSelectAgentId,
  onAgentAutoSelected,
}: {
  taskPath: string;
  channelName: string;
  activeThreadTs: string | null;
  onOpenThread: (ts: string) => void;
  onOpenProfile: (target: ProfileTarget) => void;
  embedded?: boolean;
  agents?: AgentSummary[];
  mode?: "workspace" | "task";
  workspaceId?: number;
  autoSelectAgentId?: string | null;
  onAgentAutoSelected?: () => void;
}) {
  const isWs = mode === "workspace" && workspaceId != null;
  const taskMsgs = useMessages(isWs ? "" : taskPath, isWs ? null : channelName);
  const wsMsgs = useWorkspaceMessages(isWs ? workspaceId : null);
  const { messages, loading, refetch } = isWs ? wsMsgs : taskMsgs;
  const { user } = useAuth();
  const [wsTab, setWsTab] = useState<WorkspaceTab>("agents");
  const [showAgentsPanel, setShowAgentsPanel] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(agents?.[0]?.id ?? null);
  const agentIds = useMemo(() => selectedAgentId ? [selectedAgentId] : [], [selectedAgentId]);
  const { states: agentStates, sendMessage: sendAgentMessage, cancel: cancelAgent, setModel: setAgentModel } = useWorkspaceAgents(
    isWs ? String(workspaceId) : null,
    agentIds,
  );
  const activeAgentState = selectedAgentId ? agentStates[selectedAgentId] : undefined;

  // Auto-select newly created agent
  useEffect(() => {
    if (autoSelectAgentId) {
      setSelectedAgentId(autoSelectAgentId);
      setWsTab("agents");
      onAgentAutoSelected?.();
    }
  }, [autoSelectAgentId, onAgentAutoSelected]);

  const handleEdit = useCallback(
    async (ts: string, newText: string) => {
      if (isWs) {
        await apiPatch(`/workspaces/${workspaceId}/messages/${ts}`, { text: newText });
      } else {
        await apiPatch(`/tasks/${taskPath}/channels/${channelName}/messages/${ts}`, { text: newText });
      }
      refetch();
    },
    [isWs, workspaceId, taskPath, channelName, refetch],
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastCountRef = useRef(0);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (messages.length > lastCountRef.current) {
      el.scrollTop = el.scrollHeight;
    }
    lastCountRef.current = messages.length;
  }, [messages]);

  // Task mode: show messages directly without workspace tabs
  if (mode === "task") {
    return (
      <div className="flex-1 min-w-0 flex flex-col bg-[var(--color-surface)] overflow-hidden rounded-tl-xl">
        {/* Simple channel header */}
        <div className="shrink-0 h-[52px] px-6 flex items-center gap-2 border-b border-[var(--color-border)]">
          <LuHash size={18} className="text-[var(--color-text-tertiary)]" />
          <span className="font-bold text-[17px] text-[var(--color-text)]">{channelName}</span>
        </div>
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto pt-5 pb-4">
          {loading && messages.length === 0 ? (
            <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">Loading messages…</div>
          ) : messages.length === 0 ? (
            <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">
              No messages in <span className="font-medium text-[var(--color-text)]">#{channelName}</span> yet.
            </div>
          ) : (
            <MessageTimeline
              messages={messages}
              onOpenThread={onOpenThread}
              onOpenProfile={onOpenProfile}
              onEdit={handleEdit}
              currentUserId={user?.id ?? null}
              activeThreadTs={activeThreadTs}
            />
          )}
        </div>
        <MessageInput
          key={`main::${channelName}`}
          taskPath={taskPath}
          channelName={channelName}
          placeholder={`Message #${channelName}`}
          onSent={refetch}
        />
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col bg-[var(--color-layer-1)] overflow-hidden rounded-tl-xl">
      {/* Workspace header: name + agents + tabs */}
      <div className="shrink-0 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
        <div className="h-[52px] px-6 flex items-center gap-2">
          <LuFolder size={18} className="text-[var(--color-text-tertiary)]" />
          <span className="font-bold text-[17px] text-[var(--color-text)]">{channelName}</span>
          {agents && agents.length > 0 && (
            <button
              onClick={() => setShowAgentsPanel(!showAgentsPanel)}
              className={`ml-auto flex items-center gap-2 rounded-xl border px-2.5 py-1 text-[13px] font-medium transition-colors ${
                showAgentsPanel
                  ? "border-[var(--color-accent)] text-[var(--color-accent)] bg-[var(--color-accent-50)]"
                  : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-1)]"
              }`}
            >
              <div className="flex items-center -space-x-1">
                {agents.slice(0, 3).map((a) => (
                  <Avatar key={a.id} id={a.id} seed={a.avatar_seed} kind="agent" size="xs" />
                ))}
              </div>
              <span>{agents.length}</span>
            </button>
          )}
        </div>
        <div className="flex items-center gap-1 px-5 mt-1">
          {WORKSPACE_TABS.map((tab) => {
            const active = wsTab === tab.id;
            const Icon = tab.Icon;
            return (
              <button
                key={tab.id}
                onClick={() => setWsTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 pb-2 text-[13px] font-medium border-b-2 transition-colors ${
                  active
                    ? "border-[var(--color-accent)] text-[var(--color-text)]"
                    : "border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]"
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content + agents panel */}
      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 min-w-0 flex flex-col">
          {wsTab === "agents" && (
            <div className="flex-1 min-h-0 flex flex-col relative">
              {agents && agents.length > 0 ? (
                <>
                  <div className="absolute top-2 left-3 z-10">
                    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg">
                      <AgentSelector
                        agents={agents.map((a) => ({ id: a.id, avatar_seed: a.avatar_seed }))}
                        activeId={selectedAgentId}
                        onSelect={setSelectedAgentId}
                      />
                    </div>
                  </div>
                  {selectedAgentId && activeAgentState ? (
                    activeAgentState.connecting ? (
                      <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-secondary)]">
                        Connecting to {selectedAgentId}...
                      </div>
                    ) : activeAgentState.error ? (
                      <div className="flex-1 flex items-center justify-center text-[13px] text-red-500">
                        {activeAgentState.error}
                      </div>
                    ) : (
                      <AgentChat
                        agentId={selectedAgentId}
                        messages={activeAgentState.messages}
                        onSend={(text) => sendAgentMessage(selectedAgentId, text)}
                        onCancel={() => cancelAgent(selectedAgentId)}
                        onModelChange={async (model) => { await setAgentModel(selectedAgentId, model); }}
                        loading={activeAgentState.isLoading}
                        cancelling={activeAgentState.cancelling}
                      />
                    )
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-secondary)]">
                      Select an agent to start chatting.
                    </div>
                  )}
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-secondary)]">
                  No agents in this workspace. Add one from the Members section.
                </div>
              )}
            </div>
          )}

          {wsTab === "messages" && (
            <>
              <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto pt-5 pb-4">
                {loading && messages.length === 0 ? (
                  <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">Loading messages…</div>
                ) : messages.length === 0 ? (
                  <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">
                    No messages in <span className="font-medium text-[var(--color-text)]">{channelName}</span> yet.
                  </div>
                ) : (
                  <MessageTimeline
                    messages={messages}
                    onOpenThread={onOpenThread}
                    onOpenProfile={onOpenProfile}
                    onEdit={handleEdit}
                    currentUserId={user?.id ?? null}
                    activeThreadTs={activeThreadTs}
                  />
                )}
              </div>
              <MessageInput
                key={`ws::${workspaceId}`}
                workspaceId={workspaceId}
                placeholder={`Message ${channelName}`}
                onSent={refetch}
              />
            </>
          )}

          {wsTab === "files" && workspaceId && (
            <WorkspaceFilesView workspaceId={workspaceId} />
          )}

          {wsTab === "tasks" && (
            <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-secondary)]">
              Tasks view coming soon
            </div>
          )}

          {wsTab === "artifacts" && (
            <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-secondary)]">
              Artifacts view coming soon
            </div>
          )}

          {wsTab === "settings" && workspaceId && (
            <WorkspaceSettings workspaceId={workspaceId} workspaceName={channelName} />
          )}
        </div>

        {/* Agents popup */}
        {showAgentsPanel && agents && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setShowAgentsPanel(false)} />
            <AgentsPopup agents={agents} onClose={() => setShowAgentsPanel(false)} onOpenProfile={onOpenProfile} />
          </>
        )}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────── Workspace settings ──────────────────────────────────────────────── */

const HIVE_VOLUME_ID = process.env.NEXT_PUBLIC_HIVE_VOLUME_ID ?? "";

function WorkspaceFilesView({ workspaceId }: { workspaceId: number }) {
  const url = HIVE_VOLUME_ID && SDK_BASE
    ? `${SDK_BASE}/volumes/${HIVE_VOLUME_ID}/files/tree?path=shared/${workspaceId}/`
    : null;
  const { data, isLoading, error } = useSWR(
    url,
    (u: string) => fetch(u).then(r => r.json()),
    { refreshInterval: 15000 },
  );

  const tree = useMemo(() => {
    if (!data) return [];
    // Server returns { tree: "line1\nline2\n..." } from agent-sdk, or { tree: [] } when volume not configured
    const raw = (data as Record<string, unknown>).tree;
    if (!raw || typeof raw !== "string") return [];
    const lines = raw.split("\n").filter((l: string) => l.length > 0);
    const nodes: FsTreeNode[] = [];
    for (const line of lines) {
      const isDir = line.endsWith("/");
      const clean = isDir ? line.slice(0, -1) : line;
      const name = clean.split("/").pop() || clean;
      nodes.push({ name, path: clean, type: isDir ? "directory" : "file" });
    }
    return nodes;
  }, [data]);

  const readFile = useCallback(async (path: string) => {
    if (!HIVE_VOLUME_ID || !SDK_BASE) return undefined;
    const full = path.startsWith("shared/") ? path : `shared/${workspaceId}/${path.replace(/^\/+/, "")}`;
    const resp = await fetch(
      `${SDK_BASE}/volumes/${HIVE_VOLUME_ID}/files/read?path=${encodeURIComponent(full)}`,
    );
    if (!resp.ok) return undefined;
    const j = await resp.json();
    return { content: (j.content as string) ?? "" };
  }, [workspaceId]);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-secondary)]">
        Loading files...
      </div>
    );
  }

  return <FileExplorer tree={tree} loading={isLoading} onReadFile={readFile} />;
}

function WorkspaceSettings({ workspaceId, workspaceName }: { workspaceId: number; workspaceName: string }) {
  const router = useRouter();
  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const handleDelete = async () => {
    setDeleting(true);
    setError("");
    try {
      await apiDelete(`/workspaces/${workspaceId}`);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete workspace");
      setDeleting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6">
      <div className="space-y-6">
        {/* Danger Zone */}
        <div>
          <h3 className="text-base font-medium text-[var(--color-text)] mb-4">Danger Zone</h3>
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)]">
            <div className="px-5 py-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-[var(--color-text)]">Delete workspace</div>
                <div className="text-xs text-[var(--color-text-tertiary)] mt-0.5">
                  Permanently delete this workspace and all its messages. Agents with runs will be preserved but unlinked.
                </div>
              </div>
              {!showConfirm ? (
                <button
                  onClick={() => setShowConfirm(true)}
                  className="shrink-0 px-3 py-1.5 text-xs font-medium text-red-500 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                >
                  Delete
                </button>
              ) : (
                <div className="shrink-0 flex items-center gap-2">
                  <button
                    onClick={() => setShowConfirm(false)}
                    disabled={deleting}
                    className="px-3 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="px-3 py-1.5 text-xs font-medium text-white bg-red-500 hover:bg-red-600 disabled:opacity-50 transition-colors"
                  >
                    {deleting ? "Deleting..." : "Confirm"}
                  </button>
                </div>
              )}
            </div>
            {error && (
              <div className="px-5 pb-3">
                <p className="text-xs text-red-500">{error}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────── Message timeline + row ──────────────────────────────────────────────── */

function MessageTimeline({
  messages,
  onOpenThread,
  onOpenProfile,
  onEdit,
  currentUserId,
  activeThreadTs,
}: {
  messages: Message[];
  onOpenThread: (ts: string) => void;
  onOpenProfile: (target: ProfileTarget) => void;
  onEdit?: (ts: string, newText: string) => Promise<void>;
  currentUserId: number | null;
  activeThreadTs: string | null;
}) {
  return (
    <>
      {messages.map((msg, i) => {
        const prev = messages[i - 1];
        const showSeparator = shouldShowDateSeparator(msg, prev);
        const showAvatar = shouldShowAvatar(msg, prev);
        return (
          <div key={msg.ts}>
            {showSeparator && <DateSeparator date={new Date(msg.created_at)} />}
            <MessageRow
              message={msg}
              showAvatar={showAvatar}
              onOpenThread={onOpenThread}
              onOpenProfile={onOpenProfile}
              onEdit={onEdit}
              currentUserId={currentUserId}
              isActive={msg.ts === activeThreadTs}
            />
          </div>
        );
      })}
    </>
  );
}

function MessageRow({
  message,
  showAvatar,
  onOpenThread,
  onOpenProfile,
  onEdit,
  currentUserId = null,
  isActive,
  hideReplyAffordance = false,
}: {
  message: Message;
  showAvatar: boolean;
  onOpenThread: (ts: string) => void;
  onOpenProfile?: (target: ProfileTarget) => void;
  onEdit?: (ts: string, newText: string) => Promise<void>;
  currentUserId?: number | null;
  isActive: boolean;
  hideReplyAffordance?: boolean;
}) {
  const agentMapCtx = useContext(AgentMapContext);
  const agentSeedMap = useMemo(() => {
    const m = new Map<string, string | null>();
    for (const [id, v] of agentMapCtx) m.set(id, v.avatar_seed);
    return m;
  }, [agentMapCtx]);
  const created = new Date(message.created_at);
  const formattedTime = formatHM(created);
  const compactTime = formatHMCompact(created);
  const fullTimestamp = formatFull(created);
  const author = message.author;
  const displayName = author.display;
  const color = getAgentColor(displayName);
  const initials = displayName.slice(0, 2).toUpperCase();
  const avatarRadius = author.kind === "user" ? "rounded-full" : "rounded";
  // Wrap avatar/name in the right kind of link so click opens the right profile panel
  // and hover shows the right popover. Falls back to a plain element if no handler.
  const wrapWithLink = (node: ReactNode, extraClass?: string) => {
    if (!onOpenProfile) return node;
    if (author.kind === "agent") {
      return (
        <AgentLink agentId={author.id as string} onOpenProfile={onOpenProfile} className={extraClass}>
          {node}
        </AgentLink>
      );
    }
    return (
      <UserLink handle={author.display} onOpenProfile={onOpenProfile} className={extraClass}>
        {node}
      </UserLink>
    );
  };
  const isOwn =
    onEdit !== undefined &&
    currentUserId !== null &&
    author.kind === "user" &&
    typeof author.id === "number" &&
    author.id === currentUserId;
  const [isEditing, setIsEditing] = useState(false);
  const startEdit = () => setIsEditing(true);
  const cancelEdit = () => setIsEditing(false);
  const handleSaveEdit = async (newText: string) => {
    if (!onEdit) return;
    await onEdit(message.ts, newText);
    setIsEditing(false);
  };
  const rowBg = isActive ? "bg-[var(--color-accent-50)]" : "hover:bg-[var(--color-layer-2)]";

  return (
    <div className={`group relative flex px-5 ${showAvatar ? "pt-2 pb-px" : "py-px"} ${rowBg} transition-colors`}>
      <div className="w-9 flex-shrink-0 mr-2">
        {showAvatar ? (
          wrapWithLink(
            author.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={author.avatar_url}
                alt={displayName}
                className={`w-9 h-9 ${avatarRadius} object-cover mt-[2px] hover:brightness-110 transition-all`}
                aria-label={displayName}
              />
            ) : (
              <Avatar id={displayName} seed={author.kind === "agent" ? (agentSeedMap.get(displayName) ?? null) : null} imageUrl={author.kind === "user" ? (author.avatar_url ?? undefined) : undefined} kind={author.kind === "user" ? "user" : "agent"} size="md" className="mt-[2px] hover:brightness-110 transition-all" />
            ),
          )
        ) : (
          <span
            className="text-[11px] opacity-0 group-hover:opacity-100 leading-[22px] select-none block text-right pr-1 text-[var(--color-text-secondary)]"
            title={fullTimestamp}
          >
            {compactTime}
          </span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        {showAvatar && (
          <div className="flex items-baseline gap-2">
            {wrapWithLink(
              <span className="text-[15px] font-bold text-[var(--color-text)] hover:underline">
                {displayName}
              </span>,
            )}
            <span className="text-[12px] text-[var(--color-text-secondary)]" title={fullTimestamp}>
              {formattedTime}
            </span>
          </div>
        )}
        {isEditing ? (
          <EditMessageInline
            initialText={message.text}
            initialMentions={message.mentions}
            onSave={handleSaveEdit}
            onCancel={cancelEdit}
          />
        ) : (
          <div className="chat-message-body text-[15px] font-normal leading-[22px] whitespace-pre-wrap break-words text-[var(--color-text)]">
            <MessageBody text={message.text} mentions={message.mentions} onOpenProfile={onOpenProfile} />
            {message.edited_at && (
              <span className="text-[11px] text-[var(--color-text-tertiary)] ml-1" title={`Edited ${formatFull(new Date(message.edited_at))}`}>
                (edited)
              </span>
            )}
          </div>
        )}
        {!hideReplyAffordance && message.reply_count > 0 && (
          <ThreadFooter
            replyCount={message.reply_count}
            participants={message.thread_participants}
            onClick={() => onOpenThread(message.ts)}
          />
        )}
      </div>
      {/* Hover toolbar (top-right): edit (own only) + reply in thread */}
      {!isEditing && (
        <div className="absolute right-5 -top-3 hidden group-hover:flex items-center gap-0 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md shadow-sm overflow-hidden">
          {isOwn && (
            <button
              onClick={startEdit}
              aria-label="Edit message"
              title="Edit message"
              className="px-2 py-1 text-[12px] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)]"
            >
              <LuPencil size={13} />
            </button>
          )}
          {!hideReplyAffordance && (
            <button
              onClick={() => onOpenThread(message.ts)}
              aria-label="Reply in thread"
              title="Reply in thread"
              className="px-2 py-1 text-[12px] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)]"
            >
              <LuMessageSquare size={13} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ThreadFooter({
  replyCount,
  participants,
  onClick,
}: {
  replyCount: number;
  participants: ThreadParticipant[];
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="group/thread mt-1 flex items-center gap-2 max-w-[520px] w-full pl-1 pr-2 py-1 rounded-md border border-transparent hover:border-[var(--color-border)] hover:bg-[var(--color-surface)] hover:shadow-sm transition-colors text-left"
    >
      <ThreadAvatars participants={participants} />
      <span className="text-[13px] font-semibold text-[var(--color-accent)] hover:underline">
        {replyCount} {replyCount === 1 ? "reply" : "replies"}
      </span>
      <span className="ml-auto hidden group-hover/thread:inline-flex items-center gap-0.5 text-[12px] text-[var(--color-text-secondary)]">
        View thread
        <LuChevronRight size={14} />
      </span>
    </button>
  );
}

function MessageBody({
  text,
  mentions,
  onOpenProfile,
}: {
  text: string;
  mentions: string[];
  onOpenProfile?: (target: ProfileTarget) => void;
}) {
  const agentMap = useContext(AgentMapContext);
  return (
    <RenderMessage
      text={text}
      validatedMentions={mentions}
      renderMention={(id) => {
        return <MentionPill id={id} agentMap={agentMap} onOpenProfile={onOpenProfile} />;
      }}
    />
  );
}

const PILL_STYLES = {
  agent: { background: "rgba(47, 95, 153, 0.13)", color: "var(--color-accent)" },
  cloud: { background: "rgba(234, 138, 0, 0.13)", color: "#c27200" },
  user: { background: "rgba(107, 114, 128, 0.13)", color: "var(--color-text-secondary)" },
};

function MentionPill({
  id,
  agentMap,
  onOpenProfile,
}: {
  id: string;
  agentMap: Map<string, { type: string; avatar_seed: string | null }>;
  onOpenProfile?: (target: ProfileTarget) => void;
}) {
  const known = agentMap.get(id);
  const { agent } = useAgent(known !== undefined ? null : id);
  const agentType = known?.type ?? agent?.type ?? null;
  const isAgent = agentType !== null;
  const pillKind = agentType === "cloud" ? "cloud" : isAgent ? "agent" : "user";
  const style = PILL_STYLES[pillKind];
  const pill = (
    <span
      className="hive-mention-pill inline-flex items-center mx-px hover:brightness-95 transition-all"
      style={style}
    >
      @{id}
    </span>
  );
  if (!onOpenProfile) return pill;
  if (isAgent) {
    return (
      <AgentLink agentId={id} onOpenProfile={onOpenProfile}>
        {pill}
      </AgentLink>
    );
  }
  return (
    <UserLink handle={id} onOpenProfile={onOpenProfile}>
      {pill}
    </UserLink>
  );
}

function ThreadAvatars({ participants }: { participants: ThreadParticipant[] }) {
  const agentMapCtx = useContext(AgentMapContext);
  // Defensive: an older cached server response may have used `string[]` instead of objects.
  // Normalize each entry so the render path always sees {kind, name, avatar_url}.
  const normalized: ThreadParticipant[] = (participants ?? [])
    .map((p) => {
      if (typeof p === "string") return { kind: "agent" as const, name: p, avatar_url: null };
      if (p && typeof p === "object" && typeof p.name === "string") {
        return { kind: p.kind, name: p.name, avatar_url: p.avatar_url ?? null };
      }
      return null;
    })
    .filter((p): p is ThreadParticipant => p !== null);
  const visible = normalized.slice(0, 3);
  if (visible.length === 0) return null;
  return (
    <span className="flex items-center -space-x-1">
      {visible.map((p) => {
        if (p.avatar_url) {
          const radius = p.kind === "user" ? "rounded-full" : "rounded-lg";
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={`${p.kind}:${p.name}`}
              src={p.avatar_url}
              alt={p.name}
              className={`w-5 h-5 ${radius} object-cover`}
              title={p.name}
            />
          );
        }
        const seed = p.kind === "agent" ? (agentMapCtx.get(p.name)?.avatar_seed ?? null) : null;
        return (
          <Avatar key={`${p.kind}:${p.name}`} id={p.name} seed={seed} kind={p.kind === "user" ? "user" : "agent"} size="xs" />
        );
      })}
    </span>
  );
}

/* ──────────────────────────────────────────────── Placeholder data ──────────────────────────────────────────────── */

const PLACEHOLDER_FILES: FsTreeNode[] = [
  { name: "src", path: "src", type: "directory", children: [
    { name: "main.py", path: "src/main.py", type: "file", size: 420 },
    { name: "utils.py", path: "src/utils.py", type: "file", size: 280 },
    { name: "config.py", path: "src/config.py", type: "file", size: 120 },
  ]},
  { name: "data", path: "data", type: "directory", children: [
    { name: "train.csv", path: "data/train.csv", type: "file", size: 1024 },
    { name: "test.csv", path: "data/test.csv", type: "file", size: 512 },
  ]},
  { name: "output", path: "output", type: "directory", children: [
    { name: "results.json", path: "output/results.json", type: "file", size: 180 },
  ]},
  { name: "README.md", path: "README.md", type: "file", size: 340 },
  { name: "requirements.txt", path: "requirements.txt", type: "file", size: 90 },
];

const PLACEHOLDER_MESSAGES: ChatMessage[] = [
  { role: "user", content: "Can you analyze the dataset in /data/train.csv and build a classifier?" },
  { role: "assistant", content: "", parts: [
    { type: "thinking", content: "Let me analyze the dataset first. I need to load the CSV, check for missing values, compute feature correlations, and then train a baseline classifier." },
    { type: "tool", id: "tc1", name: "Bash", status: "done", title: "python src/main.py" },
    { type: "tool", id: "tc2", name: "Write", status: "done", title: "output/results.json" },
    { type: "text", content: "I've analyzed the dataset and trained a GradientBoosting classifier. Key results:\n\n- **Accuracy**: 0.847\n- **F1 Score**: 0.856\n- **Top features**: feature_12, feature_15, feature_3\n\nThe model and results have been saved to `output/results.json`." },
  ]},
  { role: "user", content: "Nice! Can you try SHAP values to explain the model?" },
];

function AgentsPopup({ agents, onClose, onOpenProfile }: { agents: AgentSummary[]; onClose: () => void; onOpenProfile: (target: ProfileTarget) => void }) {
  const onlineAgents = agents.filter((a) => isOnline(a.last_seen_at));
  const offlineAgents = agents.filter((a) => !isOnline(a.last_seen_at));

  return (
    <div className="absolute right-4 top-[90px] z-50 w-[280px] bg-[var(--color-surface)] border border-[var(--color-border)] shadow-[var(--shadow-elevated)] flex flex-col max-h-[400px] animate-fade-in">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 flex items-center justify-between border-b border-[var(--color-border)]">
        <span className="text-[15px] font-bold text-[var(--color-text)]">Agents</span>
        <button
          onClick={onClose}
          className="w-6 h-6 flex items-center justify-center rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
        >
          <LuX size={14} />
        </button>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto p-2">
        {onlineAgents.length > 0 && (
          <div className="mb-3">
            <h4 className="mb-1 px-2 text-[11px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wide">
              Online — {onlineAgents.length}
            </h4>
            {onlineAgents.map((a) => (
              <AgentPanelRow key={a.id} agent={a} onClick={() => { onOpenProfile({ kind: "agent", id: a.id }); onClose(); }} />
            ))}
          </div>
        )}
        {offlineAgents.length > 0 && (
          <div>
            <h4 className="mb-1 px-2 text-[11px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wide">
              Offline — {offlineAgents.length}
            </h4>
            {offlineAgents.map((a) => (
              <AgentPanelRow key={a.id} agent={a} onClick={() => { onOpenProfile({ kind: "agent", id: a.id }); onClose(); }} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AgentPanelRow({ agent, onClick }: { agent: AgentSummary; onClick: () => void }) {
  const online = isOnline(agent.last_seen_at);
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded px-2 py-1.5 hover:bg-[var(--color-layer-1)] cursor-pointer transition-colors"
    >
      <div className="relative shrink-0">
        <Avatar id={agent.id} seed={agent.avatar_seed} kind="agent" size="sm" />
        <span className="absolute -bottom-0.5 -right-0.5">
          <span className={`block w-2.5 h-2.5 rounded-full border-[1.5px] ${
            online ? "bg-green-500 border-[var(--color-surface)]" : "bg-[var(--color-surface)] border-[var(--color-text-tertiary)]"
          }`} />
        </span>
      </div>
      <div className="flex flex-col min-w-0 flex-1 text-left">
        <span className="text-[14px] text-[var(--color-text)] truncate">{agent.id}</span>
        {agent.role && (
          <span className="text-[11px] text-[var(--color-text-tertiary)] truncate">{agent.role}</span>
        )}
      </div>
    </button>
  );
}

function PlaceholderAgentWorkspace() {
  const [activeAgent, setActiveAgent] = useState("claude-dev");
  const placeholderAgents = [
    { id: "claude-dev", avatar_seed: "claude-dev-seed" },
    { id: "gpt-coder", avatar_seed: "gpt-coder-seed" },
  ];

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-[var(--color-layer-1)]">
      <AgentChat
        agentId={activeAgent}
        messages={PLACEHOLDER_MESSAGES}
        headerSlot={
          <AgentSelector
            agents={placeholderAgents}
            activeId={activeAgent}
            onSelect={setActiveAgent}
          />
        }
      />
    </div>
  );
}

function PlaceholderFilesView() {
  return <FileExplorer tree={PLACEHOLDER_FILES} />;
}

function DateSeparator({ date }: { date: Date }) {
  return (
    <div className="relative my-[10px] flex items-center px-5">
      <div className="flex-1 border-t border-[var(--color-border)]" />
      <div className="flex-shrink-0 mx-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-[2px] text-[13px] font-bold text-[var(--color-text)]">
        {formatDateSeparator(date)}
      </div>
      <div className="flex-1 border-t border-[var(--color-border)]" />
    </div>
  );
}

/* ──────────────────────────────────────────────── Thread panel ──────────────────────────────────────────────── */

function ThreadPanel({
  taskPath,
  channelName,
  ts,
  onClose,
  onOpenProfile,
  width,
  workspaceId,
}: {
  taskPath: string;
  channelName: string;
  ts: string;
  onClose: () => void;
  onOpenProfile: (target: ProfileTarget) => void;
  width: number;
  workspaceId?: number;
}) {
  const isWs = workspaceId != null;
  const taskThread = useThread(isWs ? "" : taskPath, isWs ? null : channelName, isWs ? null : ts);
  const wsThread = useWorkspaceThread(isWs ? workspaceId : null, isWs ? ts : null);
  const { parent, replies, loading, refetch } = isWs ? wsThread : taskThread;
  const { user } = useAuth();
  const handleEdit = useCallback(
    async (msgTs: string, newText: string) => {
      if (isWs) {
        await apiPatch(`/workspaces/${workspaceId}/messages/${msgTs}`, { text: newText });
      } else {
        await apiPatch(`/tasks/${taskPath}/channels/${channelName}/messages/${msgTs}`, { text: newText });
      }
      refetch();
    },
    [isWs, workspaceId, taskPath, channelName, refetch],
  );
  const currentUserId = user?.id ?? null;
  return (
    <aside
      className="hidden md:flex flex-col shrink-0 bg-[var(--color-layer-1)] border-l border-[var(--color-border)]"
      style={{ width }}
    >
      {/* Header */}
      <div className="shrink-0 h-[60px] px-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center justify-between">
        <div>
          <div className="text-[15px] font-bold leading-tight text-[var(--color-text)]">Thread</div>
          <div className="text-[12px] text-[var(--color-text-secondary)]">{isWs ? channelName : `#${channelName}`}</div>
        </div>
        <button
          onClick={onClose}
          className="w-7 h-7 flex items-center justify-center rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
          aria-label="Close thread"
        >
          <LuX size={16} />
        </button>
      </div>

      {/* Body — input lives inline below the last reply, not pinned to the bottom */}
      <div className="flex-1 min-h-0 overflow-y-auto pt-4">
        {loading && !parent ? (
          <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">Loading…</div>
        ) : parent ? (
          <>
            <MessageRow
              message={parent}
              showAvatar={true}
              onOpenThread={() => {}}
              onOpenProfile={onOpenProfile}
              onEdit={handleEdit}
              currentUserId={currentUserId}
              isActive={false}
              hideReplyAffordance
            />
            {replies.length > 0 && (
              <div className="px-5 my-3 flex items-center gap-3">
                <span className="text-[13px] text-[var(--color-text-secondary)]">
                  {replies.length} {replies.length === 1 ? "reply" : "replies"}
                </span>
                <div className="flex-1 h-px bg-[var(--color-border)]" />
              </div>
            )}
            {replies.map((reply, i) => {
              const prev = replies[i - 1];
              const showAvatar = shouldShowAvatar(reply, prev);
              return (
                <MessageRow
                  key={reply.ts}
                  message={reply}
                  showAvatar={showAvatar}
                  onOpenThread={() => {}}
                  onOpenProfile={onOpenProfile}
                  onEdit={handleEdit}
                  currentUserId={currentUserId}
                  isActive={false}
                  hideReplyAffordance
                />
              );
            })}
            <div className="mt-3">
              <MessageInput
                taskPath={isWs ? undefined : taskPath}
                channelName={isWs ? undefined : channelName}
                workspaceId={isWs ? workspaceId : undefined}
                threadTs={ts}
                placeholder="Reply..."
                onSent={refetch}
              />
            </div>
          </>
        ) : (
          <div className="px-5 text-[13px] text-[var(--color-text-secondary)]">Thread not found.</div>
        )}
      </div>
    </aside>
  );
}

/* ──────────────────────────────────────────────── helpers ──────────────────────────────────────────────── */

function shouldShowAvatar(current: Message, previous: Message | undefined): boolean {
  if (!previous) return true;
  // Compare via the author block so two user-authored messages from
  // *different* users don't get grouped under the same avatar — agent_id
  // alone is null for any user message, so comparing it would fold them.
  if (
    current.author.kind !== previous.author.kind ||
    current.author.id !== previous.author.id
  ) {
    return true;
  }
  const cur = new Date(current.created_at).getTime();
  const prev = new Date(previous.created_at).getTime();
  if (!isSameDay(new Date(current.created_at), new Date(previous.created_at))) return true;
  return cur - prev > GROUP_GAP_MS;
}

function shouldShowDateSeparator(current: Message, previous: Message | undefined): boolean {
  if (!previous) return true;
  return !isSameDay(new Date(current.created_at), new Date(previous.created_at));
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatHM(date: Date): string {
  let h = date.getHours();
  const m = date.getMinutes();
  const ampm = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return `${h}:${m.toString().padStart(2, "0")} ${ampm}`;
}

/** Compact 12-hour clock without AM/PM, used in the hover gutter on follow-up messages. */
function formatHMCompact(date: Date): string {
  let h = date.getHours();
  const m = date.getMinutes();
  h = h % 12 || 12;
  return `${h}:${m.toString().padStart(2, "0")}`;
}

function formatFull(date: Date): string {
  return date.toLocaleString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDateSeparator(date: Date): string {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (isSameDay(date, today)) return "Today";
  if (isSameDay(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}
