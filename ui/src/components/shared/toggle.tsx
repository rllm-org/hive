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
