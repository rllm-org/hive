"use client";

import { memo, useCallback, DragEvent } from "react";
import { Item, ItemStatus } from "@/types/items";
import { KanbanCard } from "./kanban-card";

interface ColumnDef {
  status: ItemStatus;
  label: string;
  dotColor: string;
}

const COLUMNS: ColumnDef[] = [
  { status: "backlog", label: "Backlog", dotColor: "#6b7280" },
  { status: "in_progress", label: "In Progress", dotColor: "#3b82f6" },
  { status: "review", label: "Review", dotColor: "#f59e0b" },
  { status: "archived", label: "Archived", dotColor: "#10b981" },
];

interface BoardProps {
  items: Item[];
  onStatusChange: (itemId: string, status: ItemStatus) => void;
  onCardClick: (item: Item) => void;
  onRefresh?: () => void;
}

const KanbanColumn = memo(function KanbanColumn({
  col,
  items,
  onStatusChange,
  onCardClick,
}: {
  col: ColumnDef;
  items: Item[];
  onStatusChange: (itemId: string, status: ItemStatus) => void;
  onCardClick: (item: Item) => void;
}) {
  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      const itemId = e.dataTransfer.getData("text/plain");
      if (itemId) onStatusChange(itemId, col.status);
    },
    [onStatusChange, col.status],
  );

  return (
    <div
      className="flex-1 min-w-[220px] flex flex-col min-h-0"
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <div className="flex items-center gap-2 px-2 py-2 shrink-0">
        <span
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ backgroundColor: col.dotColor }}
        />
        <span className="text-xs font-bold text-[var(--color-text)] uppercase tracking-wide">
          {col.label}
        </span>
        <span className="text-[10px] font-medium text-[var(--color-text-tertiary)] ml-auto">
          {items.length}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0 space-y-1.5 px-1 pb-2">
        {items.map((item) => (
          <KanbanCard
            key={item.id}
            item={item}
            onClick={() => onCardClick(item)}
          />
        ))}
        {items.length === 0 && (
          <div className="text-center text-[10px] text-[var(--color-text-tertiary)] py-8 opacity-60">
            No items
          </div>
        )}
      </div>
    </div>
  );
});

export function KanbanBoard({ items, onStatusChange, onCardClick }: BoardProps) {
  return (
    <div className="flex gap-3 flex-1 min-h-0 overflow-x-auto px-2 pb-2">
      {COLUMNS.map((col) => (
        <KanbanColumn
          key={col.status}
          col={col}
          items={items.filter((i) => i.status === col.status)}
          onStatusChange={onStatusChange}
          onCardClick={onCardClick}
        />
      ))}
    </div>
  );
}
