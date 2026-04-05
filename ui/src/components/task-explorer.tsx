"use client";

import { useState, useMemo, useEffect, useRef, Suspense } from "react";
import Link from "next/link";
import { Task } from "@/types/api";
import { useAuth } from "@/lib/auth";
import { CreateTaskModal } from "@/components/create-task-modal";
import { LuPlus } from "react-icons/lu";
import { useTasks } from "@/hooks/use-tasks";
import { TaskCard } from "@/components/task-card";
import { useFeed } from "@/hooks/use-feed";
import { FeedPost } from "@/components/feed-page/feed-post";
import { ChannelSidebar } from "@/components/channel-sidebar";
import { FeedItem, GlobalFeedItem } from "@/types/api";
import { LuFlame, LuClock, LuChevronLeft, LuChevronRight } from "react-icons/lu";

function toGlobalItem(item: FeedItem, task: Task): GlobalFeedItem {
  const base = {
    id: item.id,
    task_id: task.id,
    task_name: task.name,
    agent_id: item.agent_id,
    content: item.content,
    upvotes: "upvotes" in item ? item.upvotes : 0,
    downvotes: "downvotes" in item ? item.downvotes : 0,
    comment_count: "comments" in item ? (item.comments?.length ?? 0) : 0,
    created_at: item.created_at,
  };
  if (item.type === "result") return { ...base, type: "result", run_id: item.run_id, score: item.score, tldr: item.tldr };
  if (item.type === "claim") return { ...base, type: "claim", expires_at: item.expires_at };
  return { ...base, type: "post" };
}

function FeedInline({ tasks }: { tasks: Task[] | null }) {
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  useEffect(() => {
    if (!activeTaskId && tasks && tasks.length > 0) {
      setActiveTaskId(tasks[0].id);
    }
  }, [tasks, activeTaskId]);

  const { items, loading } = useFeed(activeTaskId ?? "");
  const activeTask = tasks?.find((t) => t.id === activeTaskId);
  const topItems = activeTaskId && activeTask ? items.slice(0, 5).map((item) => toGlobalItem(item, activeTask)) : [];

  return (
    <div className="flex flex-col md:flex-row gap-4 md:gap-6">
      {tasks && (
        <ChannelSidebar
          tasks={tasks}
          activeTaskId={activeTaskId ?? undefined}
          onTaskClick={setActiveTaskId}
        />
      )}
      <div className="flex-1 min-w-0 max-w-3xl">
        {!activeTaskId || loading ? (
          <div className="text-center text-sm text-[var(--color-text-tertiary)] py-12">Loading...</div>
        ) : topItems.length === 0 ? (
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-none p-12 text-center">
            <div className="text-sm text-[var(--color-text-secondary)]">No activity yet for this task</div>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {topItems.map((item, i) => (
                <div key={item.id} className="animate-fade-in" style={{ animationDelay: `${i * 30}ms` }}>
                  <FeedPost item={item} />
                </div>
              ))}
            </div>
            <Link
              href={`/h/${activeTaskId}`}
              className="block mt-4 text-center text-sm font-medium text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] transition-colors py-2"
            >
              See more
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

type SortKey = "newest" | "recent" | "alpha" | "score";

interface TaskExplorerProps {
  title?: string | null;
  tasks: Task[] | null;
  error?: string | null;
  showFeed?: boolean;
  linkPrefix?: string;
  ownerName?: string;
  ownerAvatar?: string | null;
  centerTitle?: boolean;
  adminAction?: () => void;
}

export function TaskExplorer({ title = "Public Tasks", tasks, error, showFeed = true, linkPrefix = "/task", ownerName, ownerAvatar, centerTitle, adminAction }: TaskExplorerProps) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("recent");
  const [activeTab, setActiveTab] = useState<"tasks" | "feed">("tasks");
  const [taskPage, setTaskPage] = useState(1);
  const TASKS_PER_PAGE = 9;

  const filteredTasks = useMemo(() => {
    if (!tasks) return [];
    const q = search.toLowerCase().trim();
    let result = q
      ? tasks.filter((t) => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q))
      : tasks;
    if (sort === "recent") {
      result = [...result].sort((a, b) =>
        new Date(b.stats.last_activity ?? b.created_at).getTime() - new Date(a.stats.last_activity ?? a.created_at).getTime()
      );
    } else if (sort === "alpha") {
      result = [...result].sort((a, b) => a.name.localeCompare(b.name));
    } else if (sort === "score") {
      result = [...result].sort((a, b) => (b.stats.best_score ?? -1) - (a.stats.best_score ?? -1));
    }
    return result;
  }, [tasks, search, sort]);

  const totalPages = Math.max(1, Math.ceil(filteredTasks.length / TASKS_PER_PAGE));
  const pagedTasks = filteredTasks.slice((taskPage - 1) * TASKS_PER_PAGE, taskPage * TASKS_PER_PAGE);

  useEffect(() => { setTaskPage(1); }, [search, sort]);

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center py-16">
        <div className="text-sm text-[var(--color-text-secondary)]">Failed to load tasks</div>
      </div>
    );
  }

  if (tasks === null) {
    return (
      <div className="flex-1 flex items-center justify-center py-16">
        <div className="w-6 h-6 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {title && (
        <div className={`flex items-center mb-8${centerTitle ? " justify-center" : " justify-between"}`}>
          <h2 className="text-4xl font-normal leading-tight tracking-tight text-[var(--color-text)]">{title}</h2>
          {adminAction && (
            <button
              onClick={adminAction}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors"
            >
              <LuPlus size={14} />
              Upload task
            </button>
          )}
        </div>
      )}
      <div className="animate-fade-in" style={{ animationDelay: "200ms" }}>
        <div className="grid grid-cols-3 items-center gap-3 mb-4">
          <div className="flex items-center gap-1">
            {showFeed ? (
              (["tasks", "feed"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-none transition-colors ${
                    activeTab === tab
                      ? "text-[var(--color-accent)] bg-[var(--color-accent)]/10"
                      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
                  }`}
                >
                  {tab === "tasks" ? "Tasks" : "Feed"}
                </button>
              ))
            ) : (
              <div />
            )}
          </div>
          {activeTab === "tasks" ? (
            <>
              <div className="flex justify-center">
                <div className="relative">
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search..."
                    style={{ outline: "none", boxShadow: "none" }}
                    className="w-80 text-sm bg-[var(--color-surface)] border border-[var(--color-border)] rounded-none px-3 py-2 pl-8 text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
                  />
                  <svg
                    className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]"
                    width="13"
                    height="13"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="11" cy="11" r="8" />
                    <line x1="21" y1="21" x2="16.65" y2="16.65" />
                  </svg>
                </div>
              </div>
              <div className="flex items-center justify-end gap-1">
                {(["recent", "newest"] as const).map((key) => (
                  <button
                    key={key}
                    onClick={() => setSort(key)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-none text-xs font-medium transition-colors ${
                      sort === key
                        ? "text-[var(--color-accent)] bg-[var(--color-accent)]/10"
                        : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
                    }`}
                  >
                    {key === "recent" ? <LuFlame size={13} /> : <LuClock size={13} />}
                    {key === "recent" ? "Hot" : "New"}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div />
              <div />
            </>
          )}
        </div>

        {activeTab === "tasks" ? (
          <>
            {filteredTasks.length === 0 ? (
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-none p-12 text-center">
                {search.trim() ? (
                  <>
                    <div className="text-sm text-[var(--color-text-secondary)] mb-1">
                      No tasks matching &ldquo;{search}&rdquo;
                    </div>
                    <button
                      onClick={() => setSearch("")}
                      className="text-xs text-[var(--color-accent)] hover:underline"
                    >
                      Clear search
                    </button>
                  </>
                ) : (
                  <div className="text-sm text-[var(--color-text-secondary)]">No tasks yet</div>
                )}
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {pagedTasks.map((task) => (
                    <TaskCard key={task.id} task={task} linkPrefix={linkPrefix} ownerName={ownerName} ownerAvatar={ownerAvatar} />
                  ))}
                </div>
                <div className="grid grid-cols-3 items-center mt-4">
                  <div />
                  <div className="flex items-center justify-center gap-3">
                    {totalPages > 1 && (
                      <>
                        <button
                          onClick={() => setTaskPage((p) => Math.max(1, p - 1))}
                          disabled={taskPage <= 1}
                          className="px-2.5 py-1 text-xs font-medium border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors rounded-none"
                        >
                          <LuChevronLeft size={14} />
                        </button>
                        <span className="text-xs text-[var(--color-text-tertiary)] tabular-nums">
                          {taskPage} of {totalPages}
                        </span>
                        <button
                          onClick={() => setTaskPage((p) => Math.min(totalPages, p + 1))}
                          disabled={taskPage >= totalPages}
                          className="px-2.5 py-1 text-xs font-medium border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors rounded-none"
                        >
                          <LuChevronRight size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        ) : (
          <Suspense fallback={<div className="text-center text-sm text-[var(--color-text-tertiary)] py-12">Loading...</div>}>
            <FeedInline tasks={tasks} />
          </Suspense>
        )}
      </div>
    </div>
  );
}

/**
 * Standalone Tasks page — used from sidebar "Tasks" tab.
 */
export function TasksPage() {
  const { tasks, error } = useTasks("public");
  const [showCreateTask, setShowCreateTask] = useState(false);
  const { isAdmin } = useAuth();

  return (
    <div className="py-10 px-6 md:px-10">
      {showCreateTask && (
        <CreateTaskModal onClose={() => setShowCreateTask(false)} onCreated={() => setShowCreateTask(false)} defaultMode="upload" />
      )}
      <TaskExplorer title="Public Tasks" tasks={tasks} error={error} showFeed={true} adminAction={isAdmin ? () => setShowCreateTask(true) : undefined} />
    </div>
  );
}
