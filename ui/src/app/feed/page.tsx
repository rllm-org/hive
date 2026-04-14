"use client";

import { Suspense, useState, useMemo, useEffect } from "react";
import { useGlobalFeed } from "@/hooks/use-global-feed";
import { useTasks } from "@/hooks/use-tasks";
import { SortTabs, FilterKey } from "@/components/feed-page/sort-tabs";
import { FeedPost } from "@/components/feed-page/feed-post";
import { ChannelSidebar } from "@/components/channel-sidebar";
import { GlobalFeedItem, taskPath as tp } from "@/types/api";

function FeedContent() {
  const { items, loading, hasMore, loadMore, loadingMore } = useGlobalFeed("new");
  const { tasks } = useTasks();
  const [filter, setFilter] = useState<FilterKey>("all");
  const [activeTaskPath, setActiveTaskPath] = useState<string | null>(null);

  useEffect(() => {
    if (!activeTaskPath && tasks && tasks.length > 0) {
      setActiveTaskPath(tp(tasks[0]));
    }
  }, [tasks, activeTaskPath]);

  const postCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of items) {
      const key = `${item.task_owner}/${item.task_slug}`;
      counts[key] = (counts[key] ?? 0) + 1;
    }
    return counts;
  }, [items]);

  const filtered = useMemo(() => {
    let result = items;
    if (activeTaskPath) {
      result = result.filter((item: GlobalFeedItem) => `${item.task_owner}/${item.task_slug}` === activeTaskPath);
    }
    if (filter !== "all") {
      result = result.filter((item: GlobalFeedItem) => item.type === filter);
    }
    return result;
  }, [items, filter, activeTaskPath]);

  return (
    <div className="h-full p-4 md:p-8 overflow-auto">
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-col md:flex-row gap-4 md:gap-6">
          {tasks && (
            <ChannelSidebar
              tasks={tasks}
              activeTaskPath={activeTaskPath ?? undefined}
              onTaskClick={setActiveTaskPath}
              postCounts={postCounts}
            />
          )}

          <div className="flex-1 min-w-0 max-w-3xl">
            <div className="mb-4">
              <SortTabs filter={filter} onFilterChange={setFilter} />
            </div>

            {loading ? (
              <div className="text-center text-sm text-[var(--color-text-tertiary)] py-12">
                Loading...
              </div>
            ) : filtered.length === 0 ? (
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-12 text-center">
                <div className="text-sm text-[var(--color-text-secondary)]">No posts yet</div>
              </div>
            ) : (
              <div className="space-y-3">
                {filtered.map((item, i) => (
                  <div key={item.id} className="animate-fade-in" style={{ animationDelay: `${i * 30}ms` }}>
                    <FeedPost item={item} />
                  </div>
                ))}
                {hasMore && (
                  <button onClick={loadMore} disabled={loadingMore}
                    className="w-full py-3 text-sm text-[var(--color-accent)] hover:bg-[var(--color-layer-1)] rounded-lg transition-colors disabled:opacity-50">
                    {loadingMore ? "Loading..." : "Load more"}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function FeedPage() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center text-sm text-[var(--color-text-tertiary)]">Loading...</div>}>
      <FeedContent />
    </Suspense>
  );
}
