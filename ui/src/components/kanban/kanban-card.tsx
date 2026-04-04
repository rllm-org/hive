"use client";

import { memo } from "react";
import { Item } from "@/types/items";

const priorityColors: Record<string, string> = {
  urgent: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#6b7280",
  none: "transparent",
};

const KanbanCard = memo(function KanbanCard({
  item,
  onClick,
}: {
  item: Item;
  onClick: () => void;
}) {
  const pColor = priorityColors[item.priority] ?? "transparent";

  return (
    <div
      draggable
      data-kanban-item-id={item.id}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", item.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={onClick}
      className="relative bg-[var(--color-surface)] border border-[var(--color-border)] cursor-pointer hover:shadow-[var(--shadow-elevated)] hover:-translate-y-px transition-all duration-150 select-none"
      style={{ borderLeftWidth: pColor !== "transparent" ? 3 : 1, borderLeftColor: pColor }}
    >
      <div className="px-3 py-2.5">
        <div className="text-[12px] font-medium text-[var(--color-text)] leading-snug line-clamp-2">
          {item.title}
        </div>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="font-[family-name:var(--font-ibm-plex-mono)] text-[10px] text-[var(--color-text-tertiary)]">
            {item.id}
          </span>
          {item.labels.map((l) => (
            <span
              key={l}
              className="text-[9px] font-medium px-1.5 py-0.5 bg-[var(--color-layer-2)] text-[var(--color-text-secondary)]"
            >
              {l}
            </span>
          ))}
        </div>
        {item.assignee_id && (
          <div className="mt-1.5 flex items-center gap-1.5">
            <div className="w-4 h-4 rounded-full bg-purple-500 flex items-center justify-center shrink-0">
              <span className="text-[7px] font-bold text-white">
                {item.assignee_id.slice(0, 2).toUpperCase()}
              </span>
            </div>
            <span className="text-[10px] text-[var(--color-text-tertiary)] truncate">
              {item.assignee_id}
            </span>
          </div>
        )}
        {item.comment_count > 0 && (
          <span className="absolute top-2 right-2 text-[9px] text-[var(--color-text-tertiary)]">
            <svg width="10" height="10" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.3" className="inline -mt-px mr-0.5">
              <path d="M3 3.5h8v5H5.5L3 10.5v-7z" />
            </svg>
            {item.comment_count}
          </span>
        )}
      </div>
    </div>
  );
});

export { KanbanCard };
