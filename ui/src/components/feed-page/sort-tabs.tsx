"use client";

import { LuFlame, LuClock } from "react-icons/lu";

const FILTERS: { value: FilterKey; label: string }[] = [
  { value: "all", label: "All" },
  { value: "result", label: "Runs" },
  { value: "post", label: "Posts" },
  { value: "claim", label: "Claims" },
];

export type FilterKey = "all" | "result" | "post" | "claim";
export type SortKey = "new" | "top";

const SORTABLE_FILTERS: FilterKey[] = ["all", "result", "post"];


const btnClass = (active: boolean) =>
  `px-3 py-1 text-xs font-medium rounded transition-colors ${
    active
      ? "bg-[var(--color-surface)] text-[var(--color-text)] shadow-sm"
      : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
  }`;

interface SortTabsProps {
  filter?: FilterKey;
  onFilterChange?: (filter: FilterKey) => void;
  sort?: SortKey;
  onSortChange?: (sort: SortKey) => void;
}

export function SortTabs({ filter = "all", onFilterChange, sort = "new", onSortChange }: SortTabsProps) {
  const showSort = SORTABLE_FILTERS.includes(filter);

  return (
    <div className="flex items-center justify-between">
      <div className="flex gap-0.5 bg-[var(--color-layer-1)] rounded-lg p-1">
        {FILTERS.map((opt) => (
          <button key={opt.value} onClick={() => onFilterChange?.(opt.value)} className={btnClass(filter === opt.value)}>
            {opt.label}
          </button>
        ))}
      </div>
      {showSort && (
        <div className="flex gap-0.5 bg-[var(--color-layer-1)] rounded-lg p-1">
          <button onClick={() => onSortChange?.("top")} className={`flex items-center gap-1.5 ${btnClass(sort === "top")}`}>
            <LuFlame size={13} />
            Top
          </button>
          <button onClick={() => onSortChange?.("new")} className={`flex items-center gap-1.5 ${btnClass(sort === "new")}`}>
            <LuClock size={13} />
            New
          </button>
        </div>
      )}
    </div>
  );
}
