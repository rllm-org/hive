"use client";

import { useState, useMemo, useEffect } from "react";
import { Task } from "@/types/api";
import { useAuth } from "@/lib/auth";
import { CreateTaskModal } from "@/components/create-task-modal";
import { LuPlus, LuFlame, LuClock, LuChevronLeft, LuChevronRight } from "react-icons/lu";
import { useTasks } from "@/hooks/use-tasks";
import { TaskCard } from "@/components/task-card";

type SortKey = "newest" | "recent" | "alpha" | "score";

interface TaskExplorerProps {
  title?: string | null;
  tasks: Task[] | null;
  error?: string | null;
  linkPrefix?: string;
  ownerName?: string;
  ownerAvatar?: string | null;
  centerTitle?: boolean;
  adminAction?: () => void;
}

export function TaskExplorer({ title = "Public Tasks", tasks, error, linkPrefix = "/task", ownerName, ownerAvatar, centerTitle, adminAction }: TaskExplorerProps) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("recent");
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
          <div />
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
        </div>

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
      </div>
    </div>
  );
}

export function TasksPage() {
  const { tasks, error } = useTasks("public");
  const [showCreateTask, setShowCreateTask] = useState(false);
  const { isAdmin } = useAuth();

  return (
    <div className="py-10 px-6 md:px-10">
      {showCreateTask && (
        <CreateTaskModal onClose={() => setShowCreateTask(false)} onCreated={() => setShowCreateTask(false)} defaultMode="upload" />
      )}
      <TaskExplorer title="Public Tasks" tasks={tasks} error={error} adminAction={isAdmin ? () => setShowCreateTask(true) : undefined} />
    </div>
  );
}
