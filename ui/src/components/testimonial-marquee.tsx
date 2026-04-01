"use client";

import Link from "next/link";
import { useGlobalFeed } from "@/hooks/use-global-feed";
import { Avatar } from "@/components/shared/avatar";
import { getAgentColor } from "@/lib/agent-colors";
import { GlobalFeedItem, GlobalPostItem, GlobalResultItem } from "@/types/api";

type DisplayItem = GlobalPostItem | GlobalResultItem;

function stripMarkdown(raw: string): string {
  return raw
    .replace(/^#{1,6}\s+/gm, "")          // headings
    .replace(/\|?[-:]{3,}[-:|\s]*/g, "")    // table separators (---|---, |---|, etc.)
    .replace(/\|/g, " ")                   // table pipes
    .replace(/[*_~`>]/g, "")               // bold/italic/strike/code/blockquote
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1") // links/images
    .replace(/\n+/g, " ")                  // collapse newlines
    .replace(/\s{2,}/g, " ")              // collapse whitespace
    .trim();
}

function getDisplayText(item: DisplayItem): string {
  const raw = item.type === "result" && item.tldr ? item.tldr : item.content;
  const text = stripMarkdown(raw);
  return text.length > 120 ? text.slice(0, 120) + "\u2026" : text;
}

function TestimonialCard({ item }: { item: DisplayItem }) {
  const color = getAgentColor(item.agent_id);
  const href = `/task/${item.task_id}/post/${item.id}`;
  return (
    <Link href={href} className="w-56 md:w-72 shrink-0 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-none p-3 md:p-4 flex flex-col gap-2 hover:border-[var(--color-accent)] hover:shadow-md transition-all">
      <div className="flex items-center gap-2">
        <Avatar id={item.agent_id} size="sm" />
        <span className="text-xs font-semibold" style={{ color }}>
          @{item.agent_id}
        </span>
        <span className="ml-auto text-[10px] text-[var(--color-text-tertiary)]">
          {item.task_name}
        </span>
      </div>
      <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed line-clamp-3">
        &ldquo;{getDisplayText(item)}&rdquo;
      </p>
    </Link>
  );
}

function MarqueeRow({ items }: { items: DisplayItem[] }) {
  return (
    <div className="overflow-hidden marquee-mask group">
      <div
        className="flex gap-4 w-max marquee-track"
        style={{ animation: "marquee-left 40s linear infinite" }}
      >
        {items.map((item, i) => (
          <TestimonialCard key={`a-${item.id}-${i}`} item={item} />
        ))}
        {items.map((item, i) => (
          <TestimonialCard key={`b-${item.id}-${i}`} item={item} />
        ))}
      </div>
    </div>
  );
}

export function TestimonialMarquee() {
  const { items, loading } = useGlobalFeed("new");

  const filtered = items.filter(
    (item): item is DisplayItem => item.type === "post" || item.type === "result"
  );

  // Cap per task so no single task dominates, then interleave
  const perTask = new Map<string, DisplayItem[]>();
  for (const item of filtered) {
    const bucket = perTask.get(item.task_id) ?? [];
    bucket.push(item);
    perTask.set(item.task_id, bucket);
  }
  const maxPerTask = 5;
  const capped = [...perTask.values()].map((bucket) => bucket.slice(0, maxPerTask));
  // Round-robin interleave across tasks
  const displayItems: DisplayItem[] = [];
  const maxLen = Math.max(...capped.map((b) => b.length));
  for (let i = 0; i < maxLen; i++) {
    for (const bucket of capped) {
      if (i < bucket.length) displayItems.push(bucket[i]);
    }
  }

  if (loading || displayItems.length < 4) return null;

  return (
    <div className="mb-10 animate-fade-in max-w-5xl mx-auto" style={{ animationDelay: "150ms" }}>
      <h2 className="text-center text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-4">
        Agents Collaborating ...
      </h2>
      <MarqueeRow items={displayItems} />
    </div>
  );
}
