"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseResizableOptions {
  initial: number;
  min: number;
  max: number;
  /** Which edge of the resized panel the handle sits on. */
  edge: "right" | "left";
  /** Optional localStorage key to persist the width across reloads. */
  storageKey?: string;
}

export function useResizableWidth({ initial, min, max, edge, storageKey }: UseResizableOptions) {
  const [width, setWidth] = useState<number>(() => {
    if (typeof window !== "undefined" && storageKey) {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const n = parseInt(saved, 10);
        if (!isNaN(n)) return Math.max(min, Math.min(max, n));
      }
    }
    return initial;
  });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; width: number } | null>(null);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragStartRef.current = { x: e.clientX, width };
      setIsDragging(true);
    },
    [width],
  );

  useEffect(() => {
    if (!isDragging) return;
    const handleMove = (e: MouseEvent) => {
      const start = dragStartRef.current;
      if (!start) return;
      const delta = edge === "right" ? e.clientX - start.x : start.x - e.clientX;
      const next = Math.max(min, Math.min(max, start.width + delta));
      setWidth(next);
    };
    const handleUp = () => {
      setIsDragging(false);
      dragStartRef.current = null;
    };
    document.addEventListener("mousemove", handleMove);
    document.addEventListener("mouseup", handleUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging, edge, min, max]);

  // Persist on width change
  useEffect(() => {
    if (storageKey && typeof window !== "undefined") {
      localStorage.setItem(storageKey, String(width));
    }
  }, [width, storageKey]);

  return { width, isDragging, onMouseDown };
}

interface ResizeHandleProps {
  isDragging: boolean;
  onMouseDown: (e: React.MouseEvent) => void;
  /** Optional dark variant for use against dark sidebar backgrounds. */
  variant?: "default" | "dark";
}

export function ResizeHandle({ isDragging, onMouseDown, variant = "default" }: ResizeHandleProps) {
  return (
    <div
      onMouseDown={onMouseDown}
      className="hidden md:block shrink-0 group relative"
      style={{ width: 8, marginLeft: -4, marginRight: -4, cursor: "col-resize", zIndex: 10 }}
    >
      <div
        className={`absolute inset-y-0 left-1/2 -translate-x-1/2 w-0.5 transition-colors ${
          isDragging
            ? "bg-[var(--color-accent)]"
            : variant === "dark"
              ? "group-hover:bg-white/30 bg-transparent"
              : "group-hover:bg-[var(--color-accent)] bg-transparent"
        }`}
      />
    </div>
  );
}
