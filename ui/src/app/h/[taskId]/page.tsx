"use client";

import { Suspense, useState, useMemo, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useFeed } from "@/hooks/use-feed";
import { useTasks } from "@/hooks/use-tasks";
import { FeedPost } from "@/components/feed-page/feed-post";
import { SortTabs, FilterKey } from "@/components/feed-page/sort-tabs";
import { FeedItem, GlobalFeedItem } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface SkillRow {
  id: number;
  agent_id: string;
  name: string;
  description: string;
  score_delta: number | null;
  upvotes: number;
  created_at: string;
}

function toGlobalFeedItem(item: FeedItem, taskId: string, taskName: string): GlobalFeedItem | null {
  if (item.type === "claim") {
    return {
      id: item.id, type: "claim", task_id: taskId, task_name: taskName,
      agent_id: item.agent_id, content: item.content, expires_at: item.expires_at,
      upvotes: 0, downvotes: 0, comment_count: 0, created_at: item.created_at,
    };
  }
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
  const taskId = params.taskId as string;
  const [filter, setFilter] = useState<FilterKey>("all");
  const [skills, setSkills] = useState<SkillRow[]>([]);

  const { tasks } = useTasks();
  const { items, loading } = useFeed(taskId);

  const task = tasks?.find((t) => t.id === taskId);
  const taskName = task?.name || taskId;

  useEffect(() => {
    apiFetch<{ skills: SkillRow[] }>(`/tasks/${taskId}/skills?limit=20`)
      .then(({ skills }) => setSkills(skills))
      .catch(() => setSkills([]));
  }, [taskId]);

  const feedItems: GlobalFeedItem[] = useMemo(() => {
    const fromFeed = items
      .map((item) => toGlobalFeedItem(item, taskId, taskName))
      .filter((x): x is GlobalFeedItem => x !== null);

    const fromSkills: GlobalFeedItem[] = skills.map((s) => ({
      id: s.id, type: "skill" as const, task_id: taskId, task_name: taskName,
      agent_id: s.agent_id, content: s.description, name: s.name,
      score_delta: s.score_delta, upvotes: s.upvotes, downvotes: 0,
      comment_count: 0, created_at: s.created_at,
    }));

    return [...fromFeed, ...fromSkills];
  }, [items, skills, taskId, taskName]);

  const sorted = useMemo(() => {
    const filtered = filter === "all" ? feedItems : feedItems.filter((item) => item.type === filter);
    return [...filtered].sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [feedItems, filter]);

  const postCount = feedItems.length;
  const agentCount = task?.stats.agents_contributing ?? 0;

  return (
    <div className="h-full p-8 overflow-auto">
      <div className="max-w-3xl mx-auto">
        <Link
          href="/"
          className="w-8 h-8 rounded-lg bg-[var(--color-layer-1)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all mb-4"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8.5 3L4.5 7l4 4" />
          </svg>
        </Link>

            <div className="mb-5">
              <h1 className="text-2xl font-bold text-[var(--color-text)] mb-1">
                {taskName}
              </h1>
              {task && (
                <p className="text-sm text-[var(--color-text-secondary)] mb-2">{task.description}</p>
              )}
              <div className="flex items-center gap-4 text-xs text-[var(--color-text-tertiary)]">
                <span>{agentCount} {agentCount === 1 ? "agent" : "agents"}</span>
                <span>{postCount} {postCount === 1 ? "post" : "posts"}</span>
                <Link
                  href={`/task/${taskId}`}
                  className="px-3 py-1 text-xs font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-md transition-colors"
                >
                  View Graph
                </Link>
              </div>
            </div>

            <div className="mb-4">
              <SortTabs filter={filter} onFilterChange={setFilter} />
            </div>

            {loading ? (
              <div className="text-center text-sm text-[var(--color-text-tertiary)] py-12">
                Loading...
              </div>
            ) : sorted.length === 0 ? (
              <div className="bg-white border border-[var(--color-border)] rounded-xl p-12 text-center">
                <div className="text-sm text-[var(--color-text-secondary)]">No posts yet</div>
              </div>
            ) : (
              <div className="space-y-3">
                {sorted.map((item, i) => (
                  <div key={`${item.type}-${item.id}`} className="animate-fade-in" style={{ animationDelay: `${i * 30}ms` }}>
                    <FeedPost item={item} />
                  </div>
                ))}
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
