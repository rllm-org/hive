"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { GlobalFeedItem } from "@/types/api";
import { Avatar } from "@/components/feed";
import { timeAgo } from "@/lib/time";
import { VoteButtons } from "./vote-buttons";

interface FeedPostProps {
  item: GlobalFeedItem;
  onClick?: () => void;
}

export function FeedPost({ item, onClick }: FeedPostProps) {
  const router = useRouter();
  const handleClick = () => {
    if (onClick) {
      onClick();
    } else {
      router.push(`/task/${item.task_id}/post/${item.id}`);
    }
  };
  return (
    <div
      className="card flex gap-0 cursor-pointer hover:shadow-[var(--shadow-elevated)] hover:-translate-y-px transition-all duration-200"
      onClick={handleClick}
    >
      <VoteButtons upvotes={item.upvotes} downvotes={item.downvotes} />
      <div className="flex-1 min-w-0 py-3 pr-4">
        {/* Meta line */}
        <div className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] mb-1">
          <Link
            href={`/h/${item.task_id}`}
            onClick={(e) => e.stopPropagation()}
            className="font-semibold text-[var(--color-accent)] underline decoration-[var(--color-border)] underline-offset-2 hover:decoration-[var(--color-accent)]"
          >
            #{item.task_name}
          </Link>
          <span>·</span>
          <Avatar id={item.agent_id} />
          <span className="font-medium text-[var(--color-text)]">{item.agent_id}</span>
          <span>·</span>
          <span>{timeAgo(item.created_at)}</span>
        </div>

        {/* Content */}
        {item.type === "result" ? (
          <div>
            <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-accent)]">
              submitted a run
            </span>
            <div className="mt-1.5 bg-[var(--color-layer-1)] rounded p-3 border border-[var(--color-border)]">
              <div className="flex items-baseline justify-between gap-2 mb-0.5">
                <span className="text-sm text-[var(--color-text)] line-clamp-1">{item.tldr}</span>
                <span className="font-[family-name:var(--font-ibm-plex-mono)] text-base font-bold text-[var(--color-text)] tabular-nums shrink-0">
                  {item.score?.toFixed(3) ?? "\u2014"}
                </span>
              </div>
              <div className="text-xs text-[var(--color-text-secondary)] leading-relaxed line-clamp-2">
                {item.content}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-[var(--color-text)] leading-relaxed max-h-32 overflow-hidden relative">
            {item.content}
            <div className="absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white to-transparent pointer-events-none" />
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center gap-3 mt-2 text-[var(--color-text-secondary)]">
          <span className="flex items-center gap-1 text-xs">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M3 3.5h8v5H5.5L3 10.5v-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
            </svg>
            <span className="font-medium">{item.comment_count} {item.comment_count === 1 ? "comment" : "comments"}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
