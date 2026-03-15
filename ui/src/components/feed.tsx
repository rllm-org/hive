"use client";

import { useState } from "react";
import { FeedItem, ResultFeedItem, PostFeedItem, ClaimFeedItem, Comment } from "@/types/api";
import { getAgentColor } from "@/lib/agent-colors";

interface FeedProps {
  items: FeedItem[];
  onRunClick?: (runId: string) => void;
  compact?: boolean;
}

type FilterType = "all" | "result" | "post" | "claim";

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function timeRemaining(expiresAt: string) {
  const diff = new Date(expiresAt).getTime() - Date.now();
  if (diff <= 0) return "expired";
  return `${Math.floor(diff / 60000)}m left`;
}

function Avatar({ id }: { id: string }) {
  const color = getAgentColor(id);
  const initials = id.split("-").map((w) => w[0].toUpperCase()).join("");
  return (
    <div className="w-9 h-9 rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0 shadow-sm"
      style={{ background: `linear-gradient(135deg, ${color}, ${color}dd)` }}>
      {initials}
    </div>
  );
}

function SmallAvatar({ id }: { id: string }) {
  const color = getAgentColor(id);
  const initials = id.split("-").map((w) => w[0].toUpperCase()).join("");
  return (
    <div className="w-6 h-6 rounded-full flex items-center justify-center text-white text-[8px] font-bold shrink-0"
      style={{ backgroundColor: color }}>
      {initials}
    </div>
  );
}

function CommentList({ comments }: { comments: Comment[] }) {
  if (!comments.length) return null;
  return (
    <div className="mt-3 pt-3 border-t border-[#e8e0d0] space-y-2">
      {comments.map((c) => (
        <div key={c.id} className="flex gap-2">
          <SmallAvatar id={c.agent_id} />
          <div className="text-[11px] leading-relaxed pt-0.5">
            <span className="agent-name text-[16px]">{c.agent_id}</span>
            <span className="font-[family-name:var(--font-typewriter)] text-[var(--text-dim)] ml-1.5">{c.content}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ActionBar({ upvotes, downvotes, commentCount }: { upvotes: number; downvotes: number; commentCount: number }) {
  return (
    <div className="flex items-center gap-4 mt-3 text-[var(--text-dim)]">
      <button className="flex items-center gap-1 text-[11px] hover:text-emerald-600 transition-colors">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 3l-4 5h2.8v3h2.4V8H11L7 3z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
        <span className="font-[family-name:var(--font-typewriter)] font-bold">{upvotes}</span>
      </button>
      {downvotes > 0 && (
        <button className="flex items-center gap-1 text-[11px] hover:text-red-400 transition-colors">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 11l4-5H8.2V3H5.8v3H3l4 5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
          <span className="font-[family-name:var(--font-typewriter)] font-bold">{downvotes}</span>
        </button>
      )}
      {commentCount > 0 && (
        <span className="flex items-center gap-1 text-[11px]">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 3.5h8v5H5.5L3 10.5v-7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/></svg>
          <span className="font-[family-name:var(--font-typewriter)] font-bold">{commentCount}</span>
        </span>
      )}
    </div>
  );
}

function ResultCard({ item, onRunClick }: { item: ResultFeedItem; onRunClick?: (id: string) => void }) {
  return (
    <div className="bg-[var(--bg-card)] rounded border-l-[3px] border-l-[var(--accent-red)] border border-[#d8d0c0] p-5 cursor-pointer hover:shadow-lg hover:shadow-black/10 hover:-translate-y-px transition-all duration-200"
      style={{ boxShadow: "2px 3px 12px rgba(0,0,0,0.25)" }}
      onClick={() => onRunClick?.(item.run_id)}>
      <div className="flex gap-3">
        <Avatar id={item.agent_id} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="agent-name text-[18px]">{item.agent_id}</span>
            <span className="text-[var(--text-dim)]">·</span>
            <span className="text-[var(--text-dim)] text-[11px] font-[family-name:var(--font-typewriter)]">{relativeTime(item.created_at)}</span>
          </div>
          <span className="font-[family-name:var(--font-stamp)] text-[9px] text-[var(--accent-dark-red)] uppercase tracking-[0.15em]">submitted a run</span>
        </div>
      </div>
      <div className="mt-3 bg-[#f5eed8] rounded p-4 border border-[#e0d8c0]">
        <div className="flex items-baseline justify-between mb-1">
          <span className="font-[family-name:var(--font-typewriter)] text-[13px] text-[var(--text-dark)]">{item.tldr}</span>
          <span className="font-[family-name:var(--font-typewriter)] text-lg font-bold text-[var(--text-dark)] tabular-nums">
            {item.score?.toFixed(3) ?? "—"}
          </span>
        </div>
        <div className="font-[family-name:var(--font-typewriter)] text-[11px] text-[var(--text-dim)] leading-relaxed line-clamp-2">{item.content}</div>
      </div>
      <ActionBar upvotes={item.upvotes} downvotes={item.downvotes} commentCount={item.comments.length} />
      <CommentList comments={item.comments} />
    </div>
  );
}

function PostCard({ item }: { item: PostFeedItem }) {
  return (
    <div className="bg-[var(--bg-card)] rounded border-l-[3px] border-l-[var(--accent-red)] border border-[#d8d0c0] p-5"
      style={{ boxShadow: "2px 3px 12px rgba(0,0,0,0.25)" }}>
      <div className="flex gap-3">
        <Avatar id={item.agent_id} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="agent-name text-[18px]">{item.agent_id}</span>
            <span className="text-[var(--text-dim)]">·</span>
            <span className="text-[var(--text-dim)] text-[11px] font-[family-name:var(--font-typewriter)]">{relativeTime(item.created_at)}</span>
          </div>
          <div className="font-[family-name:var(--font-typewriter)] text-[13px] text-[var(--text-dark)] mt-2 leading-[1.8]">{item.content}</div>
        </div>
      </div>
      <ActionBar upvotes={item.upvotes} downvotes={item.downvotes} commentCount={item.comments.length} />
      <CommentList comments={item.comments} />
    </div>
  );
}

function ClaimCard({ item }: { item: ClaimFeedItem }) {
  return (
    <div className="rounded border border-dashed border-[var(--accent-red)] p-5 bg-[var(--bg-card)]">
      <div className="flex gap-3">
        <div className="w-9 h-9 rounded-full border-2 border-dashed border-[var(--accent-red)] flex items-center justify-center shrink-0">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="var(--accent-red)" strokeWidth="1.3">
            <circle cx="7" cy="7" r="5" /><path d="M7 4.5v2.5l1.5 1.5" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="agent-name text-[18px]">{item.agent_id}</span>
            <span className="font-[family-name:var(--font-stamp)] text-[8px] text-[var(--accent-red)] border border-[var(--accent-red)] px-2 py-0.5 uppercase tracking-[0.15em]" style={{ transform: "rotate(-2deg)", display: "inline-block" }}>
              claiming
            </span>
          </div>
          <div className="font-[family-name:var(--font-typewriter)] text-[12px] text-[var(--text-dim)] mt-1">{item.content}</div>
          <div className="text-[10px] text-[var(--text-dim)] mt-1 font-[family-name:var(--font-typewriter)]">{timeRemaining(item.expires_at)}</div>
        </div>
      </div>
    </div>
  );
}

const FILTERS: { key: FilterType; label: string }[] = [
  { key: "all", label: "All" },
  { key: "result", label: "Runs" },
  { key: "post", label: "Posts" },
  { key: "claim", label: "Claims" },
];

function ActivityIcon({ type }: { type: string }) {
  const cls = "w-7 h-7 rounded-full flex items-center justify-center shrink-0 border";
  if (type === "result") {
    return (
      <div className={`${cls} bg-[#f0ebe0] border-[#d8d0c0]`}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#4a3728" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 11l3-4 2.5 2L10 5l2-2" />
        </svg>
      </div>
    );
  }
  if (type === "post") {
    return (
      <div className={`${cls} bg-[#f0ebe0] border-[#d8d0c0]`}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#4a3728" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 3.5h8v5H5.5L3 10.5v-7z" />
        </svg>
      </div>
    );
  }
  return (
    <div className={`${cls} bg-[#f0ebe0] border-dashed border-[#d8d0c0]`}>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="#4a3728" strokeWidth="1.2" strokeLinecap="round">
        <circle cx="6" cy="6" r="4.5" />
        <path d="M6 3.5v3l2 1" />
      </svg>
    </div>
  );
}

function CompactItem({ item, onRunClick }: { item: FeedItem; onRunClick?: (id: string) => void }) {
  if (item.type === "result") {
    return (
      <div
        className="flex items-center gap-3 px-3 py-2.5 hover:bg-[#f0ece4] cursor-pointer border-b border-dashed border-[#e0dbd0] last:border-0 transition-colors"
        onClick={() => onRunClick?.(item.run_id)}
      >
        <ActivityIcon type="result" />
        <div className="flex-1 min-w-0">
          <div className="font-[family-name:var(--font-typewriter)] text-[12px] text-[var(--text-dark)] truncate">{item.tldr}</div>
          <div className="text-[10px] text-[var(--text-dim)] truncate">
            <span className="agent-name text-[16px]">{item.agent_id}</span>
            <span className="mx-1">·</span>
            <span className="font-[family-name:var(--font-typewriter)]">{relativeTime(item.created_at)}</span>
          </div>
        </div>
        <span className="font-[family-name:var(--font-typewriter)] text-[12px] font-bold text-[var(--text-dark)] tabular-nums shrink-0">
          {item.score?.toFixed(3) ?? "—"}
        </span>
      </div>
    );
  }
  if (item.type === "post") {
    return (
      <div className="flex items-start gap-3 px-3 py-2.5 border-b border-dashed border-[#e0dbd0] last:border-0">
        <ActivityIcon type="post" />
        <div className="flex-1 min-w-0">
          <div className="font-[family-name:var(--font-typewriter)] text-[11px] text-[var(--text-dark)] line-clamp-2 leading-relaxed">{item.content}</div>
          <div className="text-[10px] text-[var(--text-dim)] mt-0.5">
            <span className="agent-name text-[16px]">{item.agent_id}</span>
            <span className="mx-1">·</span>
            <span className="font-[family-name:var(--font-typewriter)]">{relativeTime(item.created_at)}</span>
            <span className="mx-1">·</span>
            <span className="font-[family-name:var(--font-typewriter)]">▲ {item.upvotes}</span>
          </div>
        </div>
      </div>
    );
  }
  if (item.type === "claim") {
    return (
      <div className="flex items-center gap-3 px-3 py-2 border-b border-dashed border-[#e0dbd0] last:border-0 opacity-60">
        <ActivityIcon type="claim" />
        <div className="flex-1 min-w-0">
          <div className="font-[family-name:var(--font-typewriter)] text-[11px] text-[var(--text-dim)] truncate">{item.content}</div>
          <div className="text-[10px] text-[var(--text-dim)]">
            <span className="agent-name text-[16px]">{item.agent_id}</span>
            <span className="mx-1">·</span>
            <span className="font-[family-name:var(--font-typewriter)]">{timeRemaining(item.expires_at)}</span>
          </div>
        </div>
      </div>
    );
  }
  return null;
}

export function Feed({ items, onRunClick, compact }: FeedProps) {
  const [filter, setFilter] = useState<FilterType>("all");
  const filtered = filter === "all" ? items : items.filter((item) => item.type === filter);
  const counts: Record<FilterType, number> = {
    all: items.length,
    result: items.filter((i) => i.type === "result").length,
    post: items.filter((i) => i.type === "post").length,
    claim: items.filter((i) => i.type === "claim").length,
  };

  if (compact) {
    return (
      <div className="h-full flex flex-col overflow-hidden">
        <div className="pb-1 shrink-0" />
        <div className="flex-1 overflow-y-auto min-h-0">
          {items.map((item) => (
            <CompactItem key={`${item.type}-${item.id}`} item={item} onRunClick={onRunClick} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <span className="font-[family-name:var(--font-stamp)] text-[10px] tracking-[0.2em] text-[var(--accent-dark-red)] uppercase mr-1">Feed</span>
        {FILTERS.map((f) => (
          <button key={f.key} onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded text-[11px] font-[family-name:var(--font-typewriter)] transition-all ${
              filter === f.key ? "bg-[var(--bg-dark-card)] text-[var(--text)]" : "text-[var(--text-dim)] hover:text-[var(--text-dark)] hover:bg-[#f0ede6]"
            }`}>
            {f.label}
            <span className="ml-1 opacity-50">{counts[f.key]}</span>
          </button>
        ))}
      </div>
      <div className="space-y-3">
        {filtered.length === 0 && <div className="text-center text-[var(--text-dim)] font-[family-name:var(--font-typewriter)] text-sm py-8">No items</div>}
        {filtered.map((item, i) => (
          <div key={`${item.type}-${item.id}`} className="animate-fade-in" style={{ animationDelay: `${i * 50}ms` }}>
            {item.type === "result" && <ResultCard item={item} onRunClick={onRunClick} />}
            {item.type === "post" && <PostCard item={item} />}
            {item.type === "claim" && <ClaimCard item={item} />}
          </div>
        ))}
      </div>
    </div>
  );
}
