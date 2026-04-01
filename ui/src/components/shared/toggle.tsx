/**
 * Segmented control (white active bg + shadow inside a gray container).
 * Used in leaderboard toggle, etc.
 */
interface SegmentedControlProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
}

export function SegmentedControl<T extends string>({ value, onChange, options }: SegmentedControlProps<T>) {
  return (
    <div className="flex gap-1 p-0.5 bg-[var(--color-layer-1)] rounded-md">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${
            value === opt.value
              ? "bg-[var(--color-surface)] text-[var(--color-text)] shadow-sm"
              : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Accent-colored tab buttons (no container, accent bg on active).
 * Used in chart toggle, sort-tabs, feed full-mode filters.
 */
interface TabButtonsProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; count?: number }[];
}

export function TabButtons<T extends string>({ value, onChange, options }: TabButtonsProps<T>) {
  return (
    <div className="flex gap-0.5 p-0.5 bg-[var(--color-layer-1)] rounded-md">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
            value === opt.value
              ? "bg-[var(--color-surface)] text-[var(--color-text)] shadow-sm"
              : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
          }`}
        >
          {opt.label}
          {opt.count != null && <span className="ml-1 opacity-50">{opt.count}</span>}
        </button>
      ))}
    </div>
  );
}

/**
 * Dark compact tabs (dark bg on active, white text).
 * Used in feed compact-mode filters.
 */
interface CompactTabsProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
}

export function CompactTabs<T extends string>({ value, onChange, options }: CompactTabsProps<T>) {
  return (
    <div className="flex items-center gap-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-2 py-1 text-[11px] font-medium rounded-md transition-all whitespace-nowrap ${
            value === opt.value
              ? "bg-[var(--color-text)] text-[var(--color-bg)]"
              : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)]"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
