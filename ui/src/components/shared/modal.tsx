"use client";

import { useEffect, type ReactNode } from "react";

interface ModalProps {
  open?: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Max width class, e.g. "max-w-[480px]", "max-w-[380px]" */
  maxWidth?: string;
  className?: string;
  /** Z-index (default 9999) */
  zIndex?: number;
  /** Vertical alignment: "center" (default) or "top" (offset from top) */
  align?: "center" | "top";
}

export function Modal({
  open = true,
  onClose,
  children,
  maxWidth = "max-w-[480px]",
  className = "",
  zIndex = 9999,
  align = "center",
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div
      className={`fixed inset-0 flex ${align === "top" ? "items-start pt-24" : "items-center"} justify-center backdrop-blur-md bg-black/30`}
      style={{ zIndex }}
      onClick={onClose}
    >
      <div
        className={`bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] rounded-lg ${maxWidth} w-full flex flex-col animate-fade-in ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

export function ModalHeader({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] shrink-0">
      <h2 className="text-base font-semibold text-[var(--color-text)]">{children}</h2>
      <ModalCloseButton onClick={onClose} />
    </div>
  );
}

export function ModalBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`px-6 py-5 ${className}`}>
      {children}
    </div>
  );
}

export function ModalCloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all shrink-0"
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 3l8 8M11 3l-8 8" />
      </svg>
    </button>
  );
}
