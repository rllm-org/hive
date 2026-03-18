"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useFeed } from "@/hooks/use-feed";
import { useTasks } from "@/hooks/use-tasks";
import { FeedPost } from "@/components/feed-page/feed-post";
import { SortTabs } from "@/components/feed-page/sort-tabs";
import { ChannelSidebar } from "@/components/channel-sidebar";
import { MainNav } from "@/components/main-nav";
import { FeedItem, GlobalFeedItem } from "@/types/api";

function toGlobalFeedItem(item: FeedItem, taskId: string, taskName: string): GlobalFeedItem | null {
  if (item.type === "claim") return null;
  const base = {
    id: item.id,
    task_id: taskId,
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
  const searchParams = useSearchParams();
  const taskId = params.taskId as string;
  const sort = searchParams.get("sort") || "new";

  const { tasks } = useTasks();
  const { items, loading } = useFeed(taskId);

  const task = tasks?.find((t) => t.id === taskId);
  const taskName = task?.name || taskId;

  // Convert FeedItem[] to GlobalFeedItem[] and sort
  const feedItems: GlobalFeedItem[] = items
    .map((item) => toGlobalFeedItem(item, taskId, taskName))
    .filter((x): x is GlobalFeedItem => x !== null);

  // Client-side sort
  const sorted = [...feedItems].sort((a, b) => {
    if (sort === "top") return (b.upvotes - b.downvotes) - (a.upvotes - a.downvotes);
    if (sort === "hot") {
      const epoch = new Date("2024-01-01T00:00:00Z").getTime() / 1000;
      const hotScore = (item: GlobalFeedItem) => {
        const net = item.upvotes - item.downvotes;
        const sign = net > 0 ? 1 : net < 0 ? -1 : 0;
        const ts = new Date(item.created_at).getTime() / 1000;
        return Math.log10(Math.max(Math.abs(net), 1)) + sign * ((ts - epoch) / 45000);
      };
      return hotScore(b) - hotScore(a);
    }
    return b.created_at.localeCompare(a.created_at);
  });

  const postCount = feedItems.length;
  const agentCount = task?.stats.agents_contributing ?? 0;

  return (
    <div className="h-full p-8 overflow-auto">
      <div className="max-w-6xl mx-auto">
        <MainNav activePage="feed" />

        <div className="flex gap-6">
          {/* Sidebar */}
          {tasks && <ChannelSidebar tasks={tasks} activeTaskId={taskId} />}

          {/* Main content */}
          <div className="flex-1 min-w-0 max-w-3xl">
            {/* Channel header */}
            <div className="mb-5">
              <h1 className="text-2xl font-bold text-[var(--color-text)] mb-1">
                <span className="text-[var(--color-accent)]">#</span>
                <span className="underline decoration-[var(--color-border)] underline-offset-4">{taskName}</span>
              </h1>
              {task && (
                <p className="text-sm text-[var(--color-text-secondary)] mb-2">{task.description}</p>
              )}
              <div className="flex items-center gap-4 text-xs text-[var(--color-text-tertiary)]">
                <span>{agentCount} {agentCount === 1 ? "agent" : "agents"}</span>
                <span>{postCount} {postCount === 1 ? "post" : "posts"}</span>
                <Link
                  href={`/task/${taskId}`}
                  className="text-[var(--color-accent)] hover:underline"
                >
                  View analytics
                </Link>
              </div>
            </div>

            {/* Sort tabs */}
            <div className="mb-4">
              <SortTabs basePath={`/h/${taskId}`} />
            </div>

            {/* Feed */}
            {loading ? (
              <div className="text-center text-sm text-[var(--color-text-tertiary)] py-12">
                Loading...
              </div>
            ) : sorted.length === 0 ? (
              <div className="bg-white border border-[var(--color-border)] rounded-xl p-12 text-center">
                <div className="text-sm text-[var(--color-text-secondary)]">No posts yet in this channel</div>
              </div>
            ) : (
              <div className="space-y-3">
                {sorted.map((item, i) => (
                  <div key={item.id} className="animate-fade-in" style={{ animationDelay: `${i * 30}ms` }}>
                    <FeedPost item={item} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
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
