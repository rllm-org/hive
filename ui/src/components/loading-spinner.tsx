"use client";

export function LoadingSpinner({ className }: { className?: string }) {
  return (
    <div className={`flex justify-center py-16 ${className ?? ""}`}>
      <div className="w-6 h-6 border-2 border-[var(--color-border)] border-t-[var(--color-accent)] rounded-full animate-spin" />
    </div>
  );
}
