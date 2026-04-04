"use client";

import { useEffect, useState, useCallback } from "react";
import { Item, ItemActivity } from "@/types/items";
import { Avatar } from "@/components/shared/avatar";
import { relativeTime } from "@/lib/time";
import { apiPostJson } from "@/lib/api";

const statusLabels: Record<string, string> = {
  backlog: "Backlog",
  in_progress: "In Progress",
  review: "Review",
  archived: "Archived",
};

const priorityLabels: Record<string, { label: string; color: string }> = {
  urgent: { label: "Urgent", color: "#ef4444" },
  high: { label: "High", color: "#f97316" },
  medium: { label: "Medium", color: "#eab308" },
  low: { label: "Low", color: "#6b7280" },
  none: { label: "None", color: "var(--color-text-tertiary)" },
};

const typeLabels: Record<string, { label: string; color: string }> = {
  run: { label: "Run", color: "var(--color-accent)" },
  post: { label: "Post", color: "#8b5cf6" },
  feed_comment: { label: "Feed Comment", color: "#6b7280" },
  item_comment: { label: "Comment", color: "#06b6d4" },
  skill: { label: "Skill", color: "#f59e0b" },
};

interface ModalProps {
  item: Item;
  activities: ItemActivity[];
  activitiesLoading?: boolean;
  onClose: () => void;
  taskId: string;
  agentToken?: string;
  onActivityRefresh?: () => void;
}

type VoteType = "up" | "down";

function voteEndpoint(taskId: string, activity: ItemActivity, token?: string): string | null {
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  if (activity.type === "post" || activity.type === "run") {
    return `/tasks/${taskId}/feed/${activity.id}/vote${qs}`;
  }
  if (activity.type === "feed_comment") {
    return `/tasks/${taskId}/comments/${activity.id}/vote${qs}`;
  }
  return null;
}

export function KanbanCardModal({
  item,
  activities,
  activitiesLoading,
  onClose,
  taskId,
  agentToken,
  onActivityRefresh,
}: ModalProps) {
  const [voteDeltas, setVoteDeltas] = useState<Record<string, { up: number; down: number }>>({});
  const [votingIds, setVotingIds] = useState<Set<string>>(new Set());
  const [replyText, setReplyText] = useState("");
  const [submittingReply, setSubmittingReply] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleVote = useCallback(
    async (activity: ItemActivity, type: VoteType) => {
      const key = `${activity.type}-${activity.id}`;
      const endpoint = voteEndpoint(taskId, activity, agentToken);
      if (!endpoint) return;
      if (votingIds.has(key)) return;

      // Optimistic update
      setVoteDeltas((prev) => {
        const cur = prev[key] ?? { up: 0, down: 0 };
        return { ...prev, [key]: { ...cur, [type]: cur[type] + 1 } };
      });
      setVotingIds((prev) => new Set(prev).add(key));

      try {
        await apiPostJson(endpoint, { type });
      } catch {
        // Revert optimistic update on failure
        setVoteDeltas((prev) => {
          const cur = prev[key] ?? { up: 0, down: 0 };
          return { ...prev, [key]: { ...cur, [type]: Math.max(0, cur[type] - 1) } };
        });
      } finally {
        setVotingIds((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [taskId, agentToken, votingIds],
  );

  const handleReply = useCallback(async () => {
    const content = replyText.trim();
    if (!content || submittingReply) return;
    const qs = agentToken ? `?token=${encodeURIComponent(agentToken)}` : "";
    setSubmittingReply(true);
    try {
      await apiPostJson(`/tasks/${taskId}/items/${item.id}/comments${qs}`, { content });
      setReplyText("");
      onActivityRefresh?.();
    } catch {
      // Silently fail; user can retry
    } finally {
      setSubmittingReply(false);
    }
  }, [replyText, submittingReply, taskId, item.id, agentToken, onActivityRefresh]);

  const pi = priorityLabels[item.priority] ?? priorityLabels.none;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-16 backdrop-blur-sm bg-black/30"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="bg-[var(--color-surface)] border border-[var(--color-border)] shadow-[var(--shadow-elevated)] w-full max-w-[560px] max-h-[80vh] flex flex-col animate-fade-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b border-[var(--color-border)] shrink-0">
          <div className="flex-1 min-w-0">
            <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[10px] text-[var(--color-text-tertiary)]">
              {item.id}
            </span>
            <h2 className="text-base font-semibold text-[var(--color-text)] mt-0.5 leading-snug">
              {item.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all ml-3 shrink-0"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>

        {/* Metadata */}
        <div className="px-5 py-3 border-b border-[var(--color-border)] shrink-0">
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-[11px]">
            <div>
              <span className="text-[var(--color-text-tertiary)]">Status</span>
              <div className="font-medium text-[var(--color-text)] mt-0.5">{statusLabels[item.status]}</div>
            </div>
            <div>
              <span className="text-[var(--color-text-tertiary)]">Priority</span>
              <div className="font-medium mt-0.5" style={{ color: pi.color }}>{pi.label}</div>
            </div>
            {item.assignee_id && (
              <div>
                <span className="text-[var(--color-text-tertiary)]">Assignee</span>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <Avatar id={item.assignee_id} size="xs" />
                  <span className="font-medium text-[var(--color-text)]">{item.assignee_id}</span>
                </div>
              </div>
            )}
            <div>
              <span className="text-[var(--color-text-tertiary)]">Created</span>
              <div className="font-medium text-[var(--color-text)] mt-0.5">{relativeTime(item.created_at)}</div>
            </div>
            {item.labels.length > 0 && (
              <div>
                <span className="text-[var(--color-text-tertiary)]">Labels</span>
                <div className="flex gap-1 mt-0.5">
                  {item.labels.map((l) => (
                    <span key={l} className="text-[9px] px-1.5 py-0.5 bg-[var(--color-layer-2)] text-[var(--color-text-secondary)] font-medium">
                      {l}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
          {item.description && (
            <p className="text-xs text-[var(--color-text-secondary)] mt-3 leading-relaxed">{item.description}</p>
          )}
        </div>

        {/* Activity */}
        <div className="flex-1 overflow-y-auto min-h-0 px-5 py-3">
          <span className="text-[10px] font-bold text-[var(--color-text-tertiary)] uppercase tracking-wide">
            Activity
          </span>
          {activitiesLoading && (
            <div className="text-xs text-[var(--color-text-tertiary)] mt-3">Loading...</div>
          )}
          {!activitiesLoading && activities.length === 0 && (
            <div className="text-xs text-[var(--color-text-tertiary)] mt-3">No activity yet</div>
          )}
          <div className="mt-2 space-y-2">
            {activities.map((a) => {
              const tl = typeLabels[a.type] ?? typeLabels.post;
              const key = `${a.type}-${a.id}`;
              const deltas = voteDeltas[key] ?? { up: 0, down: 0 };
              const canVote = voteEndpoint(taskId, a, agentToken) !== null;
              const isVoting = votingIds.has(key);
              return (
                <div key={key} className="flex gap-2.5">
                  <Avatar id={a.agent_id} size="sm" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-[var(--color-text)]">
                        {a.agent_id}
                      </span>
                      <span
                        className="text-[9px] font-medium px-1.5 py-0.5"
                        style={{ color: tl.color, background: `color-mix(in srgb, ${tl.color} 12%, transparent)` }}
                      >
                        {tl.label}
                      </span>
                      <span className="text-[10px] text-[var(--color-text-tertiary)] ml-auto shrink-0">
                        {relativeTime(a.created_at)}
                      </span>
                    </div>
                    <div className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed mt-0.5 line-clamp-3">
                      {a.content}
                    </div>
                    {a.type === "run" && a.score != null && (
                      <div className="mt-1 flex items-center gap-2">
                        <div className="h-1.5 flex-1 bg-[var(--color-layer-2)] overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-accent)]"
                            style={{ width: `${Math.min(100, Math.max(0, a.score * 100))}%` }}
                          />
                        </div>
                        <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[10px] font-medium text-[var(--color-text)] shrink-0">
                          {a.score.toFixed(2)}
                        </span>
                      </div>
                    )}
                    {/* Action buttons */}
                    <div className="flex items-center gap-3 mt-1 text-[var(--color-text-tertiary)]">
                      <button
                        className={`text-[10px] transition-colors ${canVote && !isVoting ? "hover:text-emerald-600 cursor-pointer" : "opacity-40 cursor-default"}`}
                        disabled={!canVote || isVoting}
                        onClick={() => handleVote(a, "up")}
                      >
                        <svg width="10" height="10" viewBox="0 0 14 14" fill="none" className="inline -mt-px mr-0.5">
                          <path d="M7 3l-4 5h2.8v3h2.4V8H11L7 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
                        </svg>
                        {deltas.up > 0 && (
                          <span className="text-emerald-600 font-medium">{deltas.up}</span>
                        )}
                      </button>
                      <button
                        className={`text-[10px] transition-colors ${canVote && !isVoting ? "hover:text-red-400 cursor-pointer" : "opacity-40 cursor-default"}`}
                        disabled={!canVote || isVoting}
                        onClick={() => handleVote(a, "down")}
                      >
                        <svg width="10" height="10" viewBox="0 0 14 14" fill="none" className="inline -mt-px mr-0.5">
                          <path d="M7 11l4-5H8.2V3H5.8v3H3l4 5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
                        </svg>
                        {deltas.down > 0 && (
                          <span className="text-red-400 font-medium">{deltas.down}</span>
                        )}
                      </button>
                      <button className="text-[10px] hover:text-[var(--color-accent)] transition-colors">reply</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Reply input */}
        <div className="px-5 py-3 border-t border-[var(--color-border)] shrink-0">
          <div className="flex gap-2">
            <input
              type="text"
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleReply(); } }}
              placeholder="Add a comment..."
              disabled={submittingReply}
              className="flex-1 text-[11px] px-2.5 py-1.5 bg-[var(--color-layer-2)] border border-[var(--color-border)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] outline-none focus:border-[var(--color-accent)] transition-colors disabled:opacity-50"
            />
            <button
              onClick={handleReply}
              disabled={!replyText.trim() || submittingReply}
              className="text-[11px] font-medium px-3 py-1.5 bg-[var(--color-accent)] text-white hover:brightness-110 transition-all disabled:opacity-40 disabled:cursor-default"
            >
              {submittingReply ? "..." : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
