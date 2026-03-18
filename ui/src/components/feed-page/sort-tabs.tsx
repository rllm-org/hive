"use client";

import { useSearchParams, useRouter } from "next/navigation";

const SORTS = [
  { key: "hot", label: "Hot" },
  { key: "new", label: "New" },
  { key: "top", label: "Top" },
] as const;

interface SortTabsProps {
  basePath?: string;
}

export function SortTabs({ basePath = "/feed" }: SortTabsProps) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const current = searchParams.get("sort") || "new";

  return (
    <div className="flex items-center gap-1">
      {SORTS.map((s) => (
        <button
          key={s.key}
          onClick={() => router.push(`${basePath}?sort=${s.key}`)}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
            current === s.key
              ? "bg-[var(--color-text)] text-white"
              : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)]"
          }`}
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
