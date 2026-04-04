"use client";

import { useEffect } from "react";
import { Item, ItemActivity } from "@/types/items";
import { Avatar } from "@/components/shared/avatar";
import { relativeTime } from "@/lib/time";

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
  onRunClick?: (runId: string) => void;
  taskId: string;
}

export function KanbanCardModal({ item, activities, activitiesLoading, onClose, onRunClick, taskId }: ModalProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

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
              return (
                <div key={`${a.type}-${a.id}`} className="flex gap-2.5">
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
                    <div
                      className={`text-[11px] text-[var(--color-text-secondary)] leading-relaxed mt-0.5 line-clamp-3${a.type === "run" ? " cursor-pointer hover:underline" : ""}`}
                      onClick={a.type === "run" ? () => onRunClick?.(a.id) : undefined}
                    >
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
                    {/* Action buttons (UI only) */}
                    <div className="flex items-center gap-3 mt-1 text-[var(--color-text-tertiary)]">
                      <button className="text-[10px] hover:text-emerald-600 transition-colors">
                        <svg width="10" height="10" viewBox="0 0 14 14" fill="none" className="inline -mt-px mr-0.5">
                          <path d="M7 3l-4 5h2.8v3h2.4V8H11L7 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
                        </svg>
                      </button>
                      <button className="text-[10px] hover:text-red-400 transition-colors">
                        <svg width="10" height="10" viewBox="0 0 14 14" fill="none" className="inline -mt-px mr-0.5">
                          <path d="M7 11l4-5H8.2V3H5.8v3H3l4 5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
                        </svg>
                      </button>
                      <button className="text-[10px] hover:text-[var(--color-accent)] transition-colors">reply</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
