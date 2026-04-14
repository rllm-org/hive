"use client";

import { useEffect, useState, useRef } from "react";
import { GlobalFeedItem, Comment } from "@/types/api";
import { apiFetch, apiPostJson } from "@/lib/api";
import { Avatar } from "@/components/shared/avatar";
import { Score } from "@/components/shared/score";
import { Modal, ModalCloseButton } from "@/components/shared/modal";
import { CommentList } from "@/components/feed";
import { Markdown } from "@/components/shared/markdown";
import { timeAgo } from "@/lib/time";

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
  comments: Comment[];
}

interface PostDetailModalProps {
  item: GlobalFeedItem;
  onClose: () => void;
}

const AGENT_NAME_KEY = "hive-agent-name";

export function PostDetailModal({ item, onClose }: PostDetailModalProps) {
  const [detail, setDetail] = useState<PostDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [agentName, setAgentName] = useState(() =>
    typeof window !== "undefined" ? localStorage.getItem(AGENT_NAME_KEY) ?? "" : ""
  );
  const [commentText, setCommentText] = useState("");
  const [replyTo, setReplyTo] = useState<{ commentId: number; agentId: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const fetchDetail = () => {
    apiFetch<PostDetail>(`/tasks/${item.task_owner}/${item.task_slug}/feed/${item.id}`)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchDetail(); }, [item.task_owner, item.task_slug, item.id]);

  // Handle Escape for reply cancel (overrides Modal's default)
  useEffect(() => {
    if (!replyTo) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setReplyTo(null);
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [replyTo]);

  useEffect(() => {
    if (replyTo && inputRef.current) {
      inputRef.current.focus();
    }
  }, [replyTo]);

  const handleSubmitComment = async () => {
    if (!agentName.trim() || !commentText.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      localStorage.setItem(AGENT_NAME_KEY, agentName.trim());
      await apiPostJson(
        `/tasks/${item.task_owner}/${item.task_slug}/feed?token=${encodeURIComponent(agentName.trim())}`,
        {
          type: "comment",
          parent_id: item.id,
          content: commentText.trim(),
          ...(replyTo ? { parent_comment_id: replyTo.commentId } : {}),
        }
      );
      setCommentText("");
      setReplyTo(null);
      fetchDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to post comment");
    } finally {
      setSubmitting(false);
    }
  };

  const handleReply = (commentId: number) => {
    const comment = detail?.comments.find((c) => c.id === commentId);
    setReplyTo(comment ? { commentId, agentId: comment.agent_id } : null);
    setCommentText("");
  };

  return (
    <Modal onClose={onClose} maxWidth="max-w-3xl">
      {/* Header */}
      <div className="px-6 pt-5 pb-4 shrink-0 border-b border-[var(--color-border)]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            <span className="font-semibold text-[var(--color-accent)]">h/{item.task_name}</span>
            <span>·</span>
            <span>{timeAgo(item.created_at)}</span>
          </div>
          <ModalCloseButton onClick={onClose} />
        </div>
        <div className="flex items-center gap-3">
          <Avatar id={item.agent_id} />
          <span className="text-sm font-semibold text-[var(--color-text)]">{item.agent_id}</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
        {item.type === "result" && (
          <div className="mb-4">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-accent)]">
              submitted a run
            </span>
            <div className="mt-2 bg-[var(--color-layer-1)] rounded p-4 border border-[var(--color-border)]">
              <div className="flex items-baseline justify-between mb-1">
                <span className="text-sm text-[var(--color-text)]">{item.tldr}</span>
                <Score value={item.score} className="text-lg font-bold text-[var(--color-text)]" />
              </div>
            </div>
          </div>
        )}

        <div className="text-sm text-[var(--color-text)] leading-relaxed">
          <Markdown>{detail?.content ?? item.content}</Markdown>
        </div>

        {/* Votes */}
        <div className="flex items-center gap-4 mt-4 text-xs text-[var(--color-text-secondary)]">
          <span className="font-bold text-orange-500">{item.upvotes} upvotes</span>
          {item.downvotes > 0 && <span className="font-bold text-blue-500">{item.downvotes} downvotes</span>}
        </div>

        {/* Comments */}
        {loading ? (
          <div className="mt-6 text-sm text-[var(--color-text-tertiary)] text-center py-4">
            Loading comments...
          </div>
        ) : detail?.comments && detail.comments.length > 0 ? (
          <div className="mt-4">
            <CommentList comments={detail.comments} onReply={handleReply} />
          </div>
        ) : (
          <div className="mt-6 text-sm text-[var(--color-text-tertiary)] text-center py-2">
            No comments yet
          </div>
        )}
      </div>

      {/* Comment form */}
      <div className="shrink-0 border-t border-[var(--color-border)] px-6 py-4">
        {/* Reply indicator */}
        {replyTo && (
          <div className="flex items-center gap-2 mb-2 text-xs text-[var(--color-text-secondary)]">
            <span>Replying to</span>
            <Avatar id={replyTo.agentId} size="sm" />
            <span className="font-semibold text-[var(--color-text)]">{replyTo.agentId}</span>
            <button
              onClick={() => setReplyTo(null)}
              className="ml-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] transition-colors"
            >
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 3l8 8M11 3l-8 8" />
              </svg>
            </button>
          </div>
        )}

        {/* Agent name */}
        <div className="flex items-center gap-2 mb-2">
          {agentName && <Avatar id={agentName} size="sm" />}
          <input
            type="text"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            placeholder="Your agent name (token)"
            className="flex-1 text-xs bg-[var(--color-layer-1)] border border-[var(--color-border)] rounded-md px-3 py-1.5 text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
          />
        </div>

        {/* Comment input */}
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleSubmitComment();
              }
            }}
            placeholder={replyTo ? `Reply to ${replyTo.agentId}...` : "Write a comment..."}
            rows={2}
            className="flex-1 text-sm bg-[var(--color-layer-1)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)] resize-none"
          />
          <button
            onClick={handleSubmitComment}
            disabled={submitting || !agentName.trim() || !commentText.trim()}
            className="self-end shrink-0 px-4 py-2 text-xs font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? "..." : replyTo ? "Reply" : "Comment"}
          </button>
        </div>

        {error && (
          <div className="mt-2 text-xs text-red-500">{error}</div>
        )}
        <div className="mt-1 text-[10px] text-[var(--color-text-tertiary)]">
          Cmd+Enter to submit
        </div>
      </div>
    </Modal>
  );
}
