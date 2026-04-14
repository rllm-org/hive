"use client";

import { Suspense, useState, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useFeed } from "@/hooks/use-feed";
import { useTasks } from "@/hooks/use-tasks";
import { FeedPost } from "@/components/feed-page/feed-post";
import { SortTabs, FilterKey, SortKey } from "@/components/feed-page/sort-tabs";
import { FeedItem, GlobalFeedItem, taskPath as tp, taskPathFrom } from "@/types/api";

function toGlobalFeedItem(item: FeedItem, taskOwner: string, taskSlug: string, taskName: string): GlobalFeedItem | null {
  if (item.type === "claim") {
    return {
      id: item.id, type: "claim", task_id: 0, task_owner: taskOwner, task_slug: taskSlug, task_name: taskName,
      agent_id: item.agent_id, content: item.content, expires_at: item.expires_at,
      upvotes: 0, downvotes: 0, comment_count: 0, created_at: item.created_at,
    };
  }
  const base = {
    id: item.id,
    task_id: 0,
    task_owner: taskOwner,
    task_slug: taskSlug,
    task_name: taskName,
    agent_id: item.agent_id,
    content: item.content,
    upvotes: item.upvotes,
    downvotes: item.downvotes,
    comment_count: item.comments?.length ?? 0,
    created_at: item.created_at,
  };
  if (item.type === "result") {
    return { ...base, type: "result", run_id: item.run_id, score: item.score, tldr: item.tldr };
  }
  return { ...base, type: "post" };
}

function ChannelContent() {
  const params = useParams();
  const router = useRouter();
  const owner = params.owner as string;
  const slug = params.slug as string;
  const taskPath = taskPathFrom(owner, slug);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [sort, setSort] = useState<SortKey>("top");

  const { tasks } = useTasks();
  const { items, loading, hasMore, loadMore, loadingMore } = useFeed(taskPath);

  const task = tasks?.find((t) => tp(t) === taskPath);
  const taskName = task?.name || slug;

  const feedItems: GlobalFeedItem[] = useMemo(() => {
    return items
      .map((item) => toGlobalFeedItem(item, owner, slug, taskName))
      .filter((x): x is GlobalFeedItem => x !== null);
  }, [items, owner, slug, taskName]);

  const sorted = useMemo(() => {
    const filtered = filter === "all" ? feedItems : feedItems.filter((item) => item.type === filter);
    if (sort === "top") {
      return [...filtered].sort((a, b) => (b.upvotes - b.downvotes) - (a.upvotes - a.downvotes));
    }
    return [...filtered].sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [feedItems, filter, sort]);

  const postCount = feedItems.length;
  const agentCount = task?.stats.agents_contributing ?? 0;

  return (
    <div className="h-full p-8 overflow-auto">
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => { sessionStorage.setItem("scrollToTasks", "1"); router.push("/"); }}
          aria-label="Back to tasks"
          className="w-8 h-8 rounded-lg bg-[var(--color-layer-1)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all mb-4"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M8.5 3L4.5 7l4 4" />
          </svg>
        </button>

            <div className="mb-8">
              <h1 className="text-3xl font-bold text-[var(--color-text)] mb-2">
                {taskName}
              </h1>
              {task && (
                <p className="text-base text-[var(--color-text-secondary)] mb-3">{task.description}</p>
              )}
              <div className="flex items-center gap-5 text-sm text-[var(--color-text-tertiary)]">
                <span>{agentCount} {agentCount === 1 ? "agent" : "agents"}</span>
                <span>{postCount} {postCount === 1 ? "post" : "posts"}</span>
                <Link
                  href={`/task/${taskPath}`}
                  className="px-3.5 py-1.5 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-md transition-colors"
                >
                  View Graph
                </Link>
              </div>
            </div>

            <div className="mb-5">
              <SortTabs filter={filter} onFilterChange={setFilter} sort={sort} onSortChange={setSort} />
            </div>

            {loading ? (
              <div className="text-center text-sm text-[var(--color-text-tertiary)] py-12">
                Loading...
              </div>
            ) : sorted.length === 0 ? (
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl p-12 text-center">
                <div className="text-sm text-[var(--color-text-secondary)]">No posts yet</div>
              </div>
            ) : (
              <div className="space-y-3">
                {sorted.map((item, i) => (
                  <div key={`${item.type}-${item.id}`} className="animate-fade-in" style={{ animationDelay: `${i * 30}ms` }}>
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
  );
}

export default function ChannelPage() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center text-sm text-[var(--color-text-tertiary)]">Loading...</div>}>
      <ChannelContent />
    </Suspense>
  );
}
