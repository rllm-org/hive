"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type ComponentType } from "react";
import { LuHash, LuX, LuMessageSquare, LuChevronRight, LuInfo, LuActivity, LuTerminal, LuPencil, LuPlus } from "react-icons/lu";
import { useChannels, useMessages, useThread, type Channel, type Message, type ThreadParticipant } from "@/hooks/use-chat";
import { getAgentColor } from "@/lib/agent-colors";
import { RenderMessage } from "@/components/chat/render-message";
import { ResizeHandle, useResizableWidth } from "@/components/shared/resize-handle";
import { AgentLink, AgentProfilePanel, UserLink, UserProfilePanel, type ProfileTarget } from "@/components/chat/agent-profile";
import { MessageInput, EditMessageInline } from "@/components/chat/message-input";
import { CreateChannelDialog } from "@/components/chat/create-channel-dialog";
import { useAuth } from "@/lib/auth";
import { apiPatch } from "@/lib/api";

interface ChatPanelProps {
  taskPath: string;
  sidebarHeader?: ReactNode;
  aboutContent?: ReactNode;
  runsContent?: ReactNode;
  sandboxContent?: ReactNode;
}

const HIVE_SIDEBAR_BG = "#264d80"; // hive accent-hover, used as Slack-style dark sidebar
const GROUP_GAP_MS = 5 * 60 * 1000;

/* ────────────── System views (not channels — hardcoded sidebar surfaces) ────────────── */

type SystemView = "about" | "runs" | "sandbox";

interface SystemViewDef {
  id: SystemView;
  label: string;
  Icon: ComponentType<{ size?: number; className?: string }>;
}

const SYSTEM_VIEWS: SystemViewDef[] = [
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

export function ChatPanel({ taskPath, sidebarHeader, aboutContent, runsContent, sandboxContent }: ChatPanelProps) {
  const { channels, loading: channelsLoading, refetch: refetchChannels } = useChannels(taskPath);
  const { user } = useAuth();
  const [createChannelOpen, setCreateChannelOpen] = useState(false);
  const showSandbox = sandboxContent != null;
  const visibleSystemViews = useMemo(
    () => SYSTEM_VIEWS.filter((v) => v.id !== "sandbox" || showSandbox),
    [showSandbox],
  );

  const [selection, setSelection] = useState<Selection>(() => {
    return loadSelection(taskPath) ?? { kind: "system", view: "about" };
  });
  const [activeThreadTs, setActiveThreadTs] = useState<string | null>(null);
  const [activeProfile, setActiveProfile] = useState<ProfileTarget | null>(null);

  // If saved selection is no longer valid (channel deleted, sandbox revoked), fall back to About
  const effectiveSelection: Selection = useMemo(() => {
    if (selection.kind === "system") {
      if (selection.view === "sandbox" && !showSandbox) {
        return { kind: "system", view: "about" };
      }
      return selection;
    }
    if (channels.some((c) => c.name === selection.name)) {
      return selection;
    }
    return { kind: "system", view: "about" };
  }, [selection, channels, showSandbox]);

  const handleSelectSystem = useCallback(
    (view: SystemView) => {
      const next: Selection = { kind: "system", view };
      setSelection(next);
      setActiveThreadTs(null);
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
    },
    [taskPath],
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
    initial: 360,
    min: 300,
    max: 560,
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

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden pt-1 bg-[var(--color-surface)]">
      {/* Inner blue chrome — top + left only; right and bottom continue to the page edge */}
      <div
        className="flex-1 min-h-0 flex flex-col rounded-tl-2xl overflow-hidden"
        style={{ backgroundColor: HIVE_SIDEBAR_BG }}
      >
        {/* Thin horizontal top bar — same hive blue, visually one piece with the sidebar */}
        <div className="shrink-0 h-[10px] w-full" />

        {/* Sidebar + content */}
        <div className="flex-1 min-h-0 flex">
          <ChannelSidebar
            header={sidebarHeader}
            systemViews={visibleSystemViews}
            channels={channels}
            selection={effectiveSelection}
            loading={channelsLoading}
            onSelectSystem={handleSelectSystem}
            onSelectChannel={handleSelectChannel}
            onCreateChannel={user ? () => setCreateChannelOpen(true) : undefined}
            width={sidebarResize.width}
          />
          <ResizeHandle
            isDragging={sidebarResize.isDragging}
            onMouseDown={sidebarResize.onMouseDown}
            variant="dark"
          />
          <ChannelMain
            taskPath={taskPath}
            selection={effectiveSelection}
            onOpenThread={handleOpenThread}
            onOpenProfile={handleOpenProfile}
            activeThreadTs={activeThreadTs}
            aboutContent={aboutContent}
            runsContent={runsContent}
            sandboxContent={sandboxContent}
          />
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
              />
            </>
          )}
          {activeProfile && (
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
      </div>
      </div>
      <CreateChannelDialog
        open={createChannelOpen}
        taskPath={taskPath}
        onClose={() => setCreateChannelOpen(false)}
        onCreated={(name) => {
          refetchChannels();
          handleSelectChannel(name);
        }}
      />
    </div>
  );
}

/* ──────────────────────────────────────────────── Sidebar ──────────────────────────────────────────────── */

function ChannelSidebar({
  header,
  systemViews,
  channels,
  selection,
  loading,
  onSelectSystem,
  onSelectChannel,
  onCreateChannel,
  width,
}: {
  header?: ReactNode;
  systemViews: SystemViewDef[];
  channels: Channel[];
  selection: Selection;
  loading: boolean;
  onSelectSystem: (view: SystemView) => void;
  onSelectChannel: (name: string) => void;
  onCreateChannel?: () => void;
  width: number;
}) {
  return (
    <aside
      className="hidden md:flex flex-col shrink-0"
      style={{ width, backgroundColor: HIVE_SIDEBAR_BG }}
    >
      {header && <div className="shrink-0">{header}</div>}
      <div className="flex-1 overflow-y-auto pt-1 pb-3">
        {/* System views (About, Runs, Sandbox) */}
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
        {/* Divider */}
        <div className="mx-4 my-4 h-px bg-white/15" />
        {/* Channels section header */}
        <div className="group/header flex w-[calc(100%-16px)] items-center gap-2.5 h-[30px] mx-2 pl-4 pr-2 text-[15px] text-white/75">
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
        {/* Chat channel items */}
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
              />
            ))
          )}
        </div>
      </div>
    </aside>
  );
}

const SIDEBAR_ITEM_BASE =
  "flex w-[calc(100%-16px)] items-center gap-2.5 h-[30px] mx-2 pr-2 text-[15px] text-left rounded-[6px] transition-colors";

function SidebarSystemItem({
  label,
  Icon,
  isActive,
  onClick,
}: {
  label: string;
  Icon: ComponentType<{ size?: number; className?: string }>;
  isActive: boolean;
  onClick: () => void;
}) {
  if (isActive) {
    return (
      <button
        onClick={onClick}
        className={`${SIDEBAR_ITEM_BASE} pl-4 bg-white text-[#1D1C1D] font-bold`}
      >
        <Icon size={14} className="shrink-0 opacity-80" />
        <span className="truncate">{label}</span>
      </button>
    );
  }
  return (
    <button
      onClick={onClick}
      className={`${SIDEBAR_ITEM_BASE} pl-4 text-white/75 hover:bg-white/10 hover:text-white`}
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
}: {
  name: string;
  isActive: boolean;
  onClick: () => void;
}) {
  // Chat channels are nested under the "Channels" header, so indent them more
  if (isActive) {
    return (
      <button
        onClick={onClick}
        className={`${SIDEBAR_ITEM_BASE} pl-6 bg-white text-[#1D1C1D] font-bold`}
      >
        <LuHash size={14} className="shrink-0 opacity-80" />
        <span className="truncate">{name}</span>
      </button>
    );
  }
  return (
    <button
      onClick={onClick}
      className={`${SIDEBAR_ITEM_BASE} pl-6 text-white/75 hover:bg-white/10 hover:text-white`}
    >
      <LuHash size={14} className="shrink-0 opacity-80" />
      <span className="truncate">{name}</span>
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
}: {
  taskPath: string;
  selection: Selection;
  activeThreadTs: string | null;
  onOpenThread: (ts: string) => void;
  onOpenProfile: (target: ProfileTarget) => void;
  aboutContent?: ReactNode;
  runsContent?: ReactNode;
  sandboxContent?: ReactNode;
}) {
  if (selection.kind === "system") {
    let content: ReactNode;
    if (selection.view === "about") content = aboutContent ?? <SystemViewEmpty view="about" />;
    else if (selection.view === "runs") content = runsContent ?? <SystemViewEmpty view="runs" />;
    else content = sandboxContent ?? <SystemViewEmpty view="sandbox" />;
    return (
      <div className="flex-1 min-w-0 flex flex-col bg-[var(--color-surface)] overflow-hidden rounded-tl-2xl">
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

function ChatChannelView({
  taskPath,
  channelName,
  activeThreadTs,
  onOpenThread,
  onOpenProfile,
}: {
  taskPath: string;
  channelName: string;
  activeThreadTs: string | null;
  onOpenThread: (ts: string) => void;
  onOpenProfile: (target: ProfileTarget) => void;
}) {
  const { messages, loading, refetch } = useMessages(taskPath, channelName);
  const { user } = useAuth();
  const handleEdit = useCallback(
    async (ts: string, newText: string) => {
      await apiPatch(`/tasks/${taskPath}/channels/${channelName}/messages/${ts}`, { text: newText });
      refetch();
    },
    [taskPath, channelName, refetch],
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

  return (
    <div className="flex-1 min-w-0 flex flex-col bg-[var(--color-layer-1)] overflow-hidden rounded-tl-2xl">
      <div className="shrink-0 h-[60px] px-5 flex items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <LuHash size={20} className="text-[var(--color-text)]" />
        <span className="font-bold text-[18px] text-[var(--color-text)]">{channelName}</span>
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
              <div
                className={`w-9 h-9 ${avatarRadius} text-white font-bold text-[12px] flex items-center justify-center mt-[2px] hover:brightness-110 transition-all`}
                style={{ backgroundColor: color }}
                aria-label={displayName}
              >
                {initials}
              </div>
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
  return (
    <RenderMessage
      text={text}
      validatedMentions={mentions}
      renderMention={(id) => <MentionPill agent={id} onOpenProfile={onOpenProfile} />}
    />
  );
}

function MentionPill({
  agent,
  onOpenProfile,
}: {
  agent: string;
  onOpenProfile?: (target: ProfileTarget) => void;
}) {
  const pill = (
    <span className="hive-mention-pill inline-flex items-center mx-px hover:brightness-95 transition-all">
      @{agent}
    </span>
  );
  if (!onOpenProfile) return pill;
  return (
    <AgentLink agentId={agent} onOpenProfile={onOpenProfile}>
      {pill}
    </AgentLink>
  );
}

function ThreadAvatars({ participants }: { participants: ThreadParticipant[] }) {
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
        const radius = p.kind === "user" ? "rounded-full" : "rounded";
        if (p.avatar_url) {
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={`${p.kind}:${p.name}`}
              src={p.avatar_url}
              alt={p.name}
              className={`w-5 h-5 ${radius} object-cover ring-1 ring-[var(--color-surface)]`}
              title={p.name}
            />
          );
        }
        return (
          <span
            key={`${p.kind}:${p.name}`}
            className={`w-5 h-5 ${radius} text-white text-[9px] font-bold flex items-center justify-center ring-1 ring-[var(--color-surface)]`}
            style={{ backgroundColor: getAgentColor(p.name) }}
            title={p.name}
          >
            {p.name.slice(0, 2).toUpperCase()}
          </span>
        );
      })}
    </span>
  );
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
}: {
  taskPath: string;
  channelName: string;
  ts: string;
  onClose: () => void;
  onOpenProfile: (target: ProfileTarget) => void;
  width: number;
}) {
  const { parent, replies, loading, refetch } = useThread(taskPath, channelName, ts);
  const { user } = useAuth();
  const handleEdit = useCallback(
    async (msgTs: string, newText: string) => {
      await apiPatch(`/tasks/${taskPath}/channels/${channelName}/messages/${msgTs}`, { text: newText });
      refetch();
    },
    [taskPath, channelName, refetch],
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
          <div className="text-[12px] text-[var(--color-text-secondary)]">#{channelName}</div>
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
                taskPath={taskPath}
                channelName={channelName}
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
