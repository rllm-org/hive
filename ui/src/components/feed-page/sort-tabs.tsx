"use client";

const FILTERS: { value: FilterKey; label: string }[] = [
  { value: "all", label: "All" },
  { value: "result", label: "Runs" },
  { value: "post", label: "Posts" },
  { value: "claim", label: "Claims" },
];

export type FilterKey = "all" | "result" | "post" | "claim";
export type SortKey = "new" | "top";

const SORTABLE_FILTERS: FilterKey[] = ["all", "result", "post"];

function ClockIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="5.5" />
      <path d="M7 4.5V7l2 1.5" />
    </svg>
  );
}

function FlameIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 1.5c0 2.5-3 4-3 6.5a3.5 3.5 0 0 0 7 0c0-1.5-.8-2.8-1.5-3.5-.3.8-1 1.5-1.5 1.5 0-1.5-.5-3-1-4.5Z" />
    </svg>
  );
}

const btnClass = (active: boolean) =>
  `px-3 py-1 text-xs font-medium rounded transition-colors ${
    active
      ? "bg-white text-[var(--color-text)] shadow-sm"
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
      <div className="flex gap-0.5 bg-[#f0f1f3] rounded-lg p-1">
        {FILTERS.map((opt) => (
          <button key={opt.value} onClick={() => onFilterChange?.(opt.value)} className={btnClass(filter === opt.value)}>
            {opt.label}
          </button>
        ))}
      </div>
      {showSort && (
        <div className="flex gap-0.5 bg-[#f0f1f3] rounded-lg p-1">
          <button onClick={() => onSortChange?.("top")} className={`flex items-center gap-1.5 ${btnClass(sort === "top")}`}>
            <FlameIcon />
            Top
          </button>
          <button onClick={() => onSortChange?.("new")} className={`flex items-center gap-1.5 ${btnClass(sort === "new")}`}>
            <ClockIcon />
            New
          </button>
        </div>
      )}
    </div>
  );
}
