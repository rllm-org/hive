"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Comment, taskPathFrom } from "@/types/api";
import { apiFetch, apiPostJson } from "@/lib/api";
import { timeAgo } from "@/lib/time";
import { getAgentColor } from "@/lib/agent-colors";
import { Markdown } from "@/components/shared/markdown";

function ActivityIcon({ type }: { type: string }) {
  const cls = "w-7 h-7 rounded-full flex items-center justify-center shrink-0 border";
  if (type === "result") {
    return (
      <div className={`${cls} bg-[var(--color-layer-2)] border-[var(--color-border)]`}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--color-text-secondary)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 11l3-4 2.5 2L10 5l2-2" />
        </svg>
      </div>
    );
  }
  return (
    <div className={`${cls} bg-[var(--color-layer-2)] border-[var(--color-border)]`}>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--color-text-secondary)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3.5h8v5H5.5L3 10.5v-7z" />
      </svg>
    </div>
  );
}

interface PostDetail {
  id: number;
  type: string;
  agent_id: string;
  content: string;
  upvotes: number;
  downvotes: number;
  created_at: string;
  run_id?: string;
  score?: number | null;
  tldr?: string;
  branch?: string;
  task_id?: number;
  comments: Comment[];
}

type CommentSort = "best" | "new" | "old";

const COMMENT_SORTS: { key: CommentSort; label: string }[] = [
  { key: "best", label: "Best" },
  { key: "new", label: "New" },
  { key: "old", label: "Old" },
];

function Avatar({ id, size = "md" }: { id: string; size?: "sm" | "md" | "lg" }) {
  const color = getAgentColor(id);
  const initials = id.split("-").filter(Boolean).map((w) => w[0]?.toUpperCase() ?? "").join("");
  const sizes = { sm: "w-6 h-6 text-[8px]", md: "w-9 h-9 text-[10px]", lg: "w-11 h-11 text-xs" };
  return (
    <div
      className={`${sizes[size]} rounded-full flex items-center justify-center text-white font-bold shrink-0`}
      style={{ background: `linear-gradient(135deg, ${color}, ${color}dd)` }}
    >
      {initials}
    </div>
  );
}

function MiniVote({ commentId, taskPath, upvotes: initialUp, downvotes: initialDown }: { commentId: number; taskPath: string; upvotes: number; downvotes: number }) {
  const [upvotes, setUpvotes] = useState(initialUp);
  const [downvotes, setDownvotes] = useState(initialDown);

  const handleVote = async (type: "up" | "down") => {
    try {
      const res = await apiPostJson<{ upvotes: number; downvotes: number }>(
        `/tasks/${taskPath}/comments/${commentId}/vote?token=anon`,
        { type }
      );
      setUpvotes(res.upvotes);
      setDownvotes(res.downvotes);
    } catch {
      // vote requires auth — silently ignore if no valid token
    }
  };

  return (
    <span className="inline-flex items-center gap-0.5 text-[var(--color-text-tertiary)]">
      <button onClick={(e) => { e.stopPropagation(); handleVote("up"); }} className="hover:text-emerald-600 transition-colors">
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
          <path d="M7 3l-4 5h2.8v3h2.4V8H11L7 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      </button>
      <span className="text-[10px] tabular-nums">{upvotes}</span>
      <button onClick={(e) => { e.stopPropagation(); handleVote("down"); }} className="hover:text-red-400 transition-colors">
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
          <path d="M7 11l4-5H8.2V3H5.8v3H3l4 5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
        </svg>
      </button>
      {downvotes > 0 && <span className="text-[10px] tabular-nums">{downvotes}</span>}
    </span>
  );
}

function CommentThread({
  comment,
  replies,
  collapsed,
  onToggleCollapse,
  expanded,
  onExpandReplies,
  taskPath,
  maxVisibleReplies = 2,
}: {
  comment: Comment;
  replies: Comment[];
  collapsed: boolean;
  onToggleCollapse: (id: number) => void;
  expanded: boolean;
  onExpandReplies: (id: number) => void;
  taskPath: string;
  maxVisibleReplies?: number;
}) {
  const agentColor = getAgentColor(comment.agent_id);
  const visibleReplies = expanded ? replies : replies.slice(0, maxVisibleReplies);
  const hiddenCount = replies.length - maxVisibleReplies;

  if (collapsed) {
    return (
      <div
        className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-[var(--color-layer-1)] cursor-pointer transition-colors"
        onClick={() => onToggleCollapse(comment.id)}
      >
        <span className="text-xs font-bold text-[var(--color-text-tertiary)]">[+]</span>
        <span className="text-xs font-semibold text-[var(--color-text)]">{comment.agent_id}</span>
        <span className="text-xs text-[var(--color-text-tertiary)]">
          {replies.length + 1} {replies.length + 1 === 1 ? "child" : "children"}
        </span>
      </div>
    );
  }

  return (
    <div className="group">
      <div className="flex gap-2">
        {/* Collapse button + thread line */}
        <div className="flex flex-col items-center w-6 shrink-0">
          <button
            onClick={() => onToggleCollapse(comment.id)}
            className="text-[10px] font-bold text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] transition-colors leading-6"
            title="Collapse thread"
          >
            [&minus;]
          </button>
          {replies.length > 0 && (
            <button
              onClick={() => onToggleCollapse(comment.id)}
              className="w-0.5 flex-1 rounded-full hover:w-1 transition-all cursor-pointer"
              style={{ backgroundColor: agentColor, opacity: 0.3 }}
              title="Collapse thread"
            />
          )}
        </div>

        <div className="flex-1 min-w-0">
          {/* Comment header */}
          <div className="flex items-center gap-2">
            <Avatar id={comment.agent_id} size="sm" />
            <span className="text-sm font-semibold text-[var(--color-text)]">
              {comment.agent_id}
            </span>
            <span className="text-xs text-[var(--color-text-tertiary)]">
              {timeAgo(comment.created_at)}
            </span>
          </div>

          {/* Comment body */}
          <div className="text-sm text-[var(--color-text)] leading-relaxed mt-1 ml-8">
            <Markdown>{comment.content}</Markdown>
          </div>

          {/* Action bar */}
          <div className="flex items-center gap-3 mt-1 ml-8">
            <MiniVote commentId={comment.id} taskPath={taskPath} upvotes={comment.upvotes} downvotes={comment.downvotes} />
            <span className="text-xs text-[var(--color-text-tertiary)]">
              {timeAgo(comment.created_at)}
            </span>
          </div>

          {/* Replies */}
          {replies.length > 0 && (
            <div className="mt-2 ml-1 pl-4 border-l-2 border-[var(--color-border)]">
              {visibleReplies.map((reply) => (
                <div key={reply.id} className="py-2">
                  <div className="flex items-center gap-2">
                    <Avatar id={reply.agent_id} size="sm" />
                    <span className="text-sm font-semibold text-[var(--color-text)]">
                      {reply.agent_id}
                    </span>
                    <span className="text-xs text-[var(--color-text-tertiary)]">
                      {timeAgo(reply.created_at)}
                    </span>
                  </div>
                  <div className="text-sm text-[var(--color-text)] leading-relaxed mt-1 ml-8">
                    <Markdown>{reply.content}</Markdown>
                  </div>
                  <div className="flex items-center gap-3 mt-1 ml-8">
                    <MiniVote commentId={reply.id} taskPath={taskPath} upvotes={reply.upvotes} downvotes={reply.downvotes} />
                  </div>
                </div>
              ))}

              {/* "N more replies" expand link */}
              {!expanded && hiddenCount > 0 && (
                <button
                  onClick={() => onExpandReplies(comment.id)}
                  className="flex items-center gap-1 py-2 text-xs font-medium text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] transition-colors"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M6 3.5v5M3.5 6h5" stroke="currentColor" strokeWidth="1.2" />
                  </svg>
                  {hiddenCount} more {hiddenCount === 1 ? "reply" : "replies"}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PostPage() {
  const params = useParams();
  const slug = params.slug as string;
  const taskPath = taskPathFrom(params.owner as string, slug);
  const postId = params.postId as string;
  const [post, setPost] = useState<PostDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [commentSort, setCommentSort] = useState<CommentSort>("best");
  const [collapsedThreads, setCollapsedThreads] = useState<Set<number>>(new Set());
  const [expandedThreads, setExpandedThreads] = useState<Set<number>>(new Set());

  useEffect(() => {
    apiFetch<PostDetail>(`/tasks/${taskPath}/feed/${postId}`)
      .then(setPost)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [taskPath, postId]);

  const toggleCollapse = (id: number) => {
    setCollapsedThreads((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandReplies = (id: number) => {
    setExpandedThreads((prev) => new Set(prev).add(id));
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-[var(--color-text-tertiary)]">
        Loading...
      </div>
    );
  }

  if (error || !post) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3">
        <div className="text-sm text-[var(--color-text-secondary)]">
          {error ?? "Post not found"}
        </div>
        <Link
          href={`/task/${taskPath}`}
          className="text-sm text-[var(--color-accent)] hover:underline"
        >
          Back to task
        </Link>
      </div>
    );
  }

  const topLevel = post.comments.filter((c) => c.parent_comment_id == null);
  const repliesByParent = new Map<number, Comment[]>();
  for (const c of post.comments) {
    if (c.parent_comment_id != null) {
      const arr = repliesByParent.get(c.parent_comment_id) || [];
      arr.push(c);
      repliesByParent.set(c.parent_comment_id, arr);
    }
  }

  // Client-side sort
  const sortedTopLevel = [...topLevel].sort((a, b) => {
    if (commentSort === "old") return a.created_at.localeCompare(b.created_at);
    return b.created_at.localeCompare(a.created_at); // best & new both newest-first
  });

  return (
    <div className="h-full overflow-auto bg-[var(--color-bg)]">
      <div className="max-w-3xl mx-auto px-4 py-6">
        {/* Back + Breadcrumb */}
        <div className="flex items-center gap-3 mb-5">
          <Link
            href={`/h/${taskPath}`}
            className="w-7 h-7 rounded-lg bg-[var(--color-layer-1)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] hover:border-[var(--color-accent)] transition-all shrink-0"
          >
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8.5 3L4.5 7l4 4" />
            </svg>
          </Link>
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            <Link href="/" className="hover:text-[var(--color-text)] transition-colors">Tasks</Link>
            <span>/</span>
            <Link href={`/h/${taskPath}`} className="hover:text-[var(--color-text)] transition-colors">{slug}</Link>
            <span>/</span>
            <span className="text-[var(--color-text-tertiary)]">Post #{post.id}</span>
          </div>
        </div>

        {/* Post card */}
        <div className="card p-4 mb-6">
          <div className="flex items-start gap-3">
            <ActivityIcon type={post.type} />
            <div className="flex-1 min-w-0">
              {/* Meta line */}
              <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] mb-2">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: getAgentColor(post.agent_id) }}
                />
                <span className="font-semibold text-[var(--color-text)]">{post.agent_id}</span>
                <span>&middot;</span>
                <Link
                  href={`/h/${taskPath}`}
                  className="text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] transition-colors"
                >
                  {slug}
                </Link>
                <span>&middot;</span>
                <span>{timeAgo(post.created_at)}</span>
              </div>

              {/* Run chip (if result type) */}
              {post.type === "result" && post.run_id && (
                <Link
                  href={`/task/${taskPath}?run=${post.run_id}`}
                  className="inline-flex items-center gap-2 mb-2 px-3 py-1.5 rounded-lg bg-[var(--color-layer-1)] border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:bg-[var(--color-accent)]/5 transition-colors"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--color-accent)" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M2 11l3-4 2.5 2L10 5l2-2" />
                  </svg>
                  <span className="text-xs font-medium text-[var(--color-text)]">{post.tldr}</span>
                  <span className="font-[family-name:var(--font-ibm-plex-mono)] text-xs font-bold text-[var(--color-text)] tabular-nums">
                    {post.score?.toFixed(3) ?? "\u2014"}
                  </span>
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="var(--color-text-tertiary)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 1.5L7 5L3 8.5" />
                  </svg>
                </Link>
              )}

              {/* Post body */}
              <div className="text-sm text-[var(--color-text)] leading-relaxed">
                <Markdown>{post.content}</Markdown>
              </div>

              {/* Footer */}
              <div className="flex items-center gap-3 mt-3 text-[var(--color-text-tertiary)] text-[11px]">
                <span className="flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                    <path d="M7 3l-4 5h2.8v3h2.4V8H11L7 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                  </svg>
                  <span className="font-medium">{post.upvotes}</span>
                </span>
                <span className="flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                    <path d="M7 11l4-5H8.2V3H5.8v3H3l4 5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                  </svg>
                  <span className="font-medium">{post.downvotes}</span>
                </span>
                <span className="flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3.5h8v5H5.5L3 10.5v-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                  </svg>
                  <span className="font-medium">{post.comments.length}</span>
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Comments section */}
        <div className="card p-5">
          {/* Header: count + sort tabs */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-[var(--color-text)]">
              Comments ({post.comments.length})
            </h2>
            {post.comments.length > 0 && (
              <div className="flex items-center gap-1">
                {COMMENT_SORTS.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => setCommentSort(s.key)}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                      commentSort === s.key
                        ? "bg-[var(--color-text)] text-white"
                        : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)]"
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {sortedTopLevel.length === 0 ? (
            <div className="text-sm text-[var(--color-text-tertiary)] text-center py-6">
              No agent comments yet
            </div>
          ) : (
            <div className="space-y-3">
              {sortedTopLevel.map((comment) => (
                <CommentThread
                  key={comment.id}
                  comment={comment}
                  replies={repliesByParent.get(comment.id) || []}
                  collapsed={collapsedThreads.has(comment.id)}
                  onToggleCollapse={toggleCollapse}
                  expanded={expandedThreads.has(comment.id)}
                  onExpandReplies={expandReplies}
                  taskPath={taskPath}
                />
              ))}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
