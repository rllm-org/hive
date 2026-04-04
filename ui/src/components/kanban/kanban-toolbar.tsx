"use client";

import { useState } from "react";
import { ItemStatus, ItemPriority } from "@/types/items";

export interface KanbanFilters {
  status: ItemStatus | "all";
  priority: ItemPriority | "all";
}

interface ToolbarProps {
  onFilterChange: (filters: KanbanFilters) => void;
  onSearchChange: (q: string) => void;
  activeAgents?: string[];
}

const STATUS_CHIPS: { value: KanbanFilters["status"]; label: string }[] = [
  { value: "all", label: "All" },
  { value: "backlog", label: "Backlog" },
  { value: "in_progress", label: "In Progress" },
  { value: "review", label: "Review" },
];

const PRIORITY_CHIPS: { value: KanbanFilters["priority"]; label: string }[] = [
  { value: "all", label: "All" },
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
];

export function KanbanToolbar({ onFilterChange, onSearchChange, activeAgents }: ToolbarProps) {
  const [status, setStatus] = useState<KanbanFilters["status"]>("all");
  const [priority, setPriority] = useState<KanbanFilters["priority"]>("all");
  const [search, setSearch] = useState("");

  const handleStatus = (v: KanbanFilters["status"]) => {
    setStatus(v);
    onFilterChange({ status: v, priority });
  };

  const handlePriority = (v: KanbanFilters["priority"]) => {
    setPriority(v);
    onFilterChange({ status, priority: v });
  };

  const handleSearch = (v: string) => {
    setSearch(v);
    onSearchChange(v);
  };

  return (
    <div className="flex items-center gap-3 px-3 py-2 border-b border-[var(--color-border)] shrink-0 overflow-x-auto">
      {/* Status chips */}
      <div className="flex items-center gap-0.5">
        {STATUS_CHIPS.map((c) => (
          <button
            key={c.value}
            onClick={() => handleStatus(c.value)}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${
              status === c.value
                ? "bg-[var(--color-accent)] text-white"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)]"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="w-px h-4 bg-[var(--color-border)]" />

      {/* Priority chips */}
      <div className="flex items-center gap-0.5">
        {PRIORITY_CHIPS.map((c) => (
          <button
            key={c.value}
            onClick={() => handlePriority(c.value)}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${
              priority === c.value
                ? "bg-[var(--color-accent)] text-white"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)]"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="w-px h-4 bg-[var(--color-border)]" />

      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => handleSearch(e.target.value)}
        placeholder="Search items..."
        className="text-[11px] px-2 py-1 bg-[var(--color-layer-1)] border border-[var(--color-border)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] w-40 focus:outline-none focus:border-[var(--color-accent)] transition-colors"
      />

      {activeAgents && activeAgents.length > 0 && (
        <>
          <div className="w-px h-4 bg-[var(--color-border)]" />
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[10px] text-[var(--color-text-tertiary)]">
              {activeAgents.length} active
            </span>
          </div>
        </>
      )}
    </div>
  );
}
