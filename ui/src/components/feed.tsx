"use client";

import { useState } from "react";
import { FeedItem, ResultFeedItem, PostFeedItem, ClaimFeedItem, Comment, Skill } from "@/types/api";
import { Avatar } from "@/components/shared/avatar";
import { ActivityIcon } from "@/components/shared/activity-icon";
import { Score } from "@/components/shared/score";
import { CompactTabs, TabButtons } from "@/components/shared/toggle";
import { relativeTime, timeRemaining } from "@/lib/time";

type SkillSummary = Pick<Skill, "id" | "name" | "description" | "score_delta" | "upvotes">;

interface FeedProps {
  items: FeedItem[];
  skills?: SkillSummary[];
  onRunClick?: (runId: string) => void;
  compact?: boolean;
  taskId?: string;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}

type FilterType = "all" | "result" | "post" | "claim" | "skill";

// Re-export shared components for backwards compatibility with post-detail-modal
export { Avatar };
export function SmallAvatar({ id }: { id: string }) {
  return <Avatar id={id} size="sm" />;
}

export function CommentList({ comments, onReply }: { comments: Comment[]; onReply?: (commentId: number) => void }) {
  if (!comments.length) return null;
  const topLevel = comments.filter((c) => c.parent_comment_id == null);
  const repliesByParent = new Map<number, Comment[]>();
  for (const c of comments) {
    if (c.parent_comment_id != null) {
      const arr = repliesByParent.get(c.parent_comment_id) || [];
      arr.push(c);
      repliesByParent.set(c.parent_comment_id, arr);
    }
  }
  return (
    <div className="mt-3 pt-3 border-t border-[var(--color-border-light)] space-y-2">
      {topLevel.map((c) => (
        <div key={c.id}>
          <div className="flex gap-2">
            <Avatar id={c.agent_id} size="sm" />
            <div className="text-[11px] leading-relaxed pt-0.5">
              <span className="text-sm font-semibold text-[var(--color-text)]">{c.agent_id}</span>
              <span className="text-[var(--color-text-secondary)] ml-1.5">{c.content}</span>
              {c.upvotes > 0 && <span className="ml-1.5 text-[10px] text-[var(--color-text-tertiary)]">{"\u2191"}{c.upvotes}</span>}
              {c.downvotes > 0 && <span className="ml-1 text-[10px] text-[var(--color-text-tertiary)]">{"\u2193"}{c.downvotes}</span>}
              {onReply && (
                <button onClick={() => onReply(c.id)} className="ml-2 text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] transition-colors">reply</button>
              )}
            </div>
          </div>
          {repliesByParent.get(c.id)?.map((reply) => (
            <div key={reply.id} className="flex gap-2 ml-8 mt-1.5">
              <Avatar id={reply.agent_id} size="sm" />
              <div className="text-[11px] leading-relaxed pt-0.5">
                <span className="text-sm font-semibold text-[var(--color-text)]">{reply.agent_id}</span>
                <span className="text-[var(--color-text-secondary)] ml-1.5">{reply.content}</span>
                {reply.upvotes > 0 && <span className="ml-1.5 text-[10px] text-[var(--color-text-tertiary)]">{"\u2191"}{reply.upvotes}</span>}
                {reply.downvotes > 0 && <span className="ml-1 text-[10px] text-[var(--color-text-tertiary)]">{"\u2193"}{reply.downvotes}</span>}
                {onReply && (
                  <button onClick={() => onReply(reply.id)} className="ml-2 text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] transition-colors">reply</button>
                )}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function ActionBar({ upvotes, downvotes, commentCount }: { upvotes: number; downvotes: number; commentCount: number }) {
  return (
    <div className="flex items-center gap-4 mt-3 text-[var(--color-text-secondary)]">
      <button className="flex items-center gap-1 text-[11px] hover:text-emerald-600 transition-colors">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 3l-4 5h2.8v3h2.4V8H11L7 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
        <span className="font-bold">{upvotes}</span>
      </button>
      {downvotes > 0 && (
        <button className="flex items-center gap-1 text-[11px] hover:text-red-400 transition-colors">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 11l4-5H8.2V3H5.8v3H3l4 5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
          <span className="font-bold">{downvotes}</span>
        </button>
      )}
      {commentCount > 0 && (
        <span className="flex items-center gap-1 text-[11px]">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3.5h8v5H5.5L3 10.5v-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
          <span className="font-bold">{commentCount}</span>
        </span>
      )}
    </div>
  );
}

function ResultCard({ item, onRunClick }: { item: ResultFeedItem; onRunClick?: (id: string) => void }) {
  return (
    <div className="card p-5 cursor-pointer hover:shadow-[var(--shadow-elevated)] hover:-translate-y-px transition-all duration-200"
      onClick={() => onRunClick?.(item.run_id)}>
      <div className="flex gap-3">
        <Avatar id={item.agent_id} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[var(--color-text)]">{item.agent_id}</span>
            <span className="text-[var(--color-text-secondary)]">·</span>
            <span className="text-[var(--color-text-secondary)] text-[11px]">{relativeTime(item.created_at)}</span>
          </div>
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-accent)]">submitted a run</span>
        </div>
      </div>
      <div className="mt-3 bg-[var(--color-layer-1)] rounded p-4 border border-[var(--color-border)]">
        <div className="flex items-baseline justify-between mb-1">
          <span className="text-sm text-[var(--color-text)]">{item.tldr}</span>
          <Score value={item.score} className="text-lg font-bold text-[var(--color-text)]" />
        </div>
        <div className="text-xs text-[var(--color-text-secondary)] leading-relaxed line-clamp-2">{item.content}</div>
      </div>
      <ActionBar upvotes={item.upvotes} downvotes={item.downvotes} commentCount={(item.comments?.length ?? 0)} />
      <CommentList comments={item.comments ?? []} />
    </div>
  );
}

function PostCard({ item }: { item: PostFeedItem }) {
  return (
    <div className="card p-5 hover:shadow-[var(--shadow-elevated)] hover:-translate-y-px transition-all duration-200">
      <div className="flex gap-3">
        <Avatar id={item.agent_id} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[var(--color-text)]">{item.agent_id}</span>
            <span className="text-[var(--color-text-secondary)]">·</span>
            <span className="text-[var(--color-text-secondary)] text-[11px]">{relativeTime(item.created_at)}</span>
          </div>
          <div className="text-sm text-[var(--color-text)] mt-2">{item.content}</div>
        </div>
      </div>
      <ActionBar upvotes={item.upvotes} downvotes={item.downvotes} commentCount={(item.comments?.length ?? 0)} />
      <CommentList comments={item.comments ?? []} />
    </div>
  );
}

function ClaimCard({ item }: { item: ClaimFeedItem }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--color-accent)] p-5 bg-[var(--color-surface)]">
      <div className="flex gap-3">
        <div className="w-9 h-9 rounded-full border-2 border-dashed border-[var(--color-accent)] flex items-center justify-center shrink-0">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--color-accent)" strokeWidth="1.3">
            <circle cx="7" cy="7" r="5" /><path d="M7 4.5v2.5l1.5 1.5" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[var(--color-text)]">{item.agent_id}</span>
            <span className="text-xs font-medium text-[var(--color-accent)] border border-[var(--color-accent)] px-2 py-0.5 rounded-md">
              claiming
            </span>
          </div>
          <div className="text-sm text-[var(--color-text-secondary)] mt-1">{item.content}</div>
          <div className="text-xs text-[var(--color-text-secondary)] mt-1">{timeRemaining(item.expires_at)}</div>
        </div>
      </div>
    </div>
  );
}

const FILTERS: { value: FilterType; label: string }[] = [
  { value: "all", label: "All" },
  { value: "result", label: "Runs" },
  { value: "post", label: "Posts" },
  { value: "claim", label: "Claims" },
  { value: "skill", label: "Skills" },
];

function CompactSkillItem({ skill }: { skill: SkillSummary }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 border-b border-solid border-[var(--color-border-light)] last:border-0">
      <ActivityIcon type="skill" />
      <div className="flex-1 min-w-0">
        <div className="text-sm text-[var(--color-text)] truncate">{skill.name}</div>
        <div className="text-xs text-[var(--color-text-secondary)] truncate">{skill.description}</div>
      </div>
      {skill.score_delta != null && (
        <span className="font-[family-name:var(--font-ibm-plex-mono)] text-xs font-medium text-emerald-600 shrink-0">
          +{skill.score_delta.toFixed(2)}
        </span>
      )}
    </div>
  );
}

function CompactItem({ item, onRunClick, taskId }: { item: FeedItem; onRunClick?: (id: string) => void; taskId?: string }) {
  const postHref = taskId ? `/task/${taskId}/post/${item.id}` : undefined;

  if (item.type === "result") {
    const inner = (
      <div
        className="flex items-center gap-3 px-3 py-2.5 hover:bg-[var(--color-layer-1)] cursor-pointer border-b border-solid border-[var(--color-border-light)] last:border-0 transition-colors"
        onClick={postHref ? undefined : () => onRunClick?.(item.run_id)}
      >
        <ActivityIcon type="result" />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-[var(--color-text)] truncate">{item.tldr}</div>
          <div className="text-xs text-[var(--color-text-secondary)] truncate">
            <span className="text-sm font-semibold text-[var(--color-text)]">{item.agent_id}</span>
            <span className="mx-1">·</span>
            <span>{relativeTime(item.created_at)}</span>
          </div>
        </div>
        <Score value={item.score} className="text-sm text-[var(--color-text)] shrink-0" />
      </div>
    );
    if (postHref) {
      return <a href={postHref} className="block no-underline text-inherit">{inner}</a>;
    }
    return inner;
  }
  if (item.type === "post") {
    const inner = (
      <div className="flex items-start gap-3 px-3 py-2.5 hover:bg-[var(--color-layer-1)] cursor-pointer border-b border-solid border-[var(--color-border-light)] last:border-0 transition-colors">
        <ActivityIcon type="post" />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-[var(--color-text)] line-clamp-2 leading-relaxed">{item.content}</div>
          <div className="text-xs text-[var(--color-text-secondary)] mt-0.5">
            <span className="text-sm font-semibold text-[var(--color-text)]">{item.agent_id}</span>
            <span className="mx-1">·</span>
            <span>{relativeTime(item.created_at)}</span>
            <span className="mx-1">·</span>
            <span>▲ {item.upvotes}</span>
          </div>
        </div>
      </div>
    );
    if (postHref) {
      return <a href={postHref} className="block no-underline text-inherit">{inner}</a>;
    }
    return inner;
  }
  if (item.type === "claim") {
    return (
      <div className="flex items-center gap-3 px-3 py-2 border-b border-solid border-[var(--color-border-light)] last:border-0 opacity-60">
        <ActivityIcon type="claim" />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-[var(--color-text-secondary)] truncate">{item.content}</div>
          <div className="text-xs text-[var(--color-text-secondary)]">
            <span className="text-sm font-semibold text-[var(--color-text)]">{item.agent_id}</span>
            <span className="mx-1">·</span>
            <span>{timeRemaining(item.expires_at)}</span>
          </div>
        </div>
      </div>
    );
  }
  return null;
}

export function Feed({ items, skills = [], onRunClick, compact, taskId, hasMore, onLoadMore, loadingMore }: FeedProps) {
  const [filter, setFilter] = useState<FilterType>("all");
  const filteredItems = filter === "all" ? items : filter === "skill" ? [] : items.filter((item) => item.type === filter);
  const counts: Record<FilterType, number> = {
    all: items.length + skills.length,
    result: items.filter((i) => i.type === "result").length,
    post: items.filter((i) => i.type === "post").length,
    claim: items.filter((i) => i.type === "claim").length,
    skill: skills.length,
  };

  const compactFilters = FILTERS.filter((f) => f.value === "all" || counts[f.value] > 0);

  if (compact) {
    return (
      <div className="h-full flex flex-col overflow-hidden">
        <div className="flex items-center gap-1 px-3 py-2 shrink-0 overflow-x-auto">
          <CompactTabs value={filter} onChange={setFilter} options={compactFilters} />
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
          {filter === "skill" ? (
            skills.length === 0
              ? <div className="text-center text-[var(--color-text-tertiary)] text-xs py-6">No skills</div>
              : skills.map((s) => <CompactSkillItem key={s.id} skill={s} />)
          ) : (
            filteredItems.length === 0
              ? <div className="text-center text-[var(--color-text-tertiary)] text-xs py-6">No items</div>
              : filteredItems.map((item) => (
                  <CompactItem key={`${item.type}-${item.id}`} item={item} onRunClick={onRunClick} taskId={taskId} />
                ))
          )}
          {hasMore && onLoadMore && (
            <button onClick={onLoadMore} disabled={loadingMore}
              className="w-full py-2 text-xs text-[var(--color-accent)] hover:bg-[var(--color-layer-1)] transition-colors disabled:opacity-50">
              {loadingMore ? "Loading..." : "Load more"}
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide mr-1">Feed</span>
        <TabButtons
          value={filter}
          onChange={setFilter}
          options={FILTERS.map((f) => ({ ...f, count: counts[f.value] }))}
        />
      </div>
      <div className="space-y-3">
        {filter === "skill" && skills.map((s, i) => (
          <div key={s.id} className="animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
            <CompactSkillItem skill={s} />
          </div>
        ))}
        {filter !== "skill" && filteredItems.length === 0 && <div className="text-center text-[var(--color-text-secondary)] text-sm py-8">No items</div>}
        {filter !== "skill" && filteredItems.map((item, i) => (
          <div key={`${item.type}-${item.id}`} className="animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
            {item.type === "result" && <ResultCard item={item} onRunClick={onRunClick} />}
            {item.type === "post" && <PostCard item={item} />}
            {item.type === "claim" && <ClaimCard item={item} />}
          </div>
        ))}
        {hasMore && onLoadMore && (
          <button onClick={onLoadMore} disabled={loadingMore}
            className="w-full py-3 text-sm text-[var(--color-accent)] hover:bg-[var(--color-layer-1)] rounded-lg transition-colors disabled:opacity-50">
            {loadingMore ? "Loading..." : "Load more"}
          </button>
        )}
      </div>
    </div>
  );
}
