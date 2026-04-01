"use client";

import { useState, useRef, useEffect } from "react";
import { useParams } from "next/navigation";
import { toPng } from "html-to-image";
import { useContext } from "@/hooks/use-context";
import { useGraph } from "@/hooks/use-graph";
import { apiFetch } from "@/lib/api";
import { BestRunsResponse } from "@/types/api";
import { ShareImage } from "@/components/share-image";

export default function SharePage() {
  const params = useParams();
  const taskId = params.id as string;
  const { data: context, loading: ctxLoading } = useContext(taskId);
  const { runs, loading: graphLoading } = useGraph(taskId);
  const [leaderboard, setLeaderboard] = useState<BestRunsResponse | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "dark";
    return document.documentElement.classList.contains("dark") ? "dark" : "light";
  });
  const [title, setTitle] = useState("");
  const [fontSize, setFontSize] = useState(72);
  const [downloading, setDownloading] = useState(false);
  const captureRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch<BestRunsResponse>(`/tasks/${taskId}/runs?view=best_runs`)
      .then(setLeaderboard)
      .catch(() => {});
  }, [taskId]);

  const loading = ctxLoading || graphLoading || !leaderboard;

  async function handleDownload() {
    if (!captureRef.current) return;
    setDownloading(true);
    try {
      const dataUrl = await toPng(captureRef.current, {
        width: 1250,
        height: 500,
        pixelRatio: 2,
      });
      const link = document.createElement("a");
      link.download = `hive-${taskId}.png`;
      link.href = dataUrl;
      link.click();
    } finally {
      setDownloading(false);
    }
  }

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center text-[var(--color-text-secondary)]">
        Loading...
      </div>
    );
  }

  if (!context) {
    return (
      <div className="h-screen flex items-center justify-center text-[var(--color-text-secondary)]">
        Task not found
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg)] flex flex-col items-center justify-center gap-6 p-8">
      {/* Controls */}
      <div className="flex items-center gap-4">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={context.task.name}
          className="px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] rounded-none w-80 placeholder:text-[var(--color-text-tertiary)]"
        />
        <div className="flex items-center border border-[var(--color-border)] rounded-none overflow-hidden">
          <button
            onClick={() => setFontSize((s) => Math.min(s + 2, 90))}
            className="px-2 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 8L6 4l4 4" /></svg>
          </button>
          <span className="px-2 text-xs text-[var(--color-text-tertiary)] tabular-nums">{fontSize}</span>
          <button
            onClick={() => setFontSize((s) => Math.max(s - 2, 20))}
            className="px-2 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4l4 4 4-4" /></svg>
          </button>
        </div>
        <div className="flex items-center border border-[var(--color-border)] rounded-none overflow-hidden">
          <button
            onClick={() => setTheme("light")}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              theme === "light"
                ? "bg-[var(--color-text)] text-[var(--color-bg)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
            }`}
          >
            Light
          </button>
          <button
            onClick={() => setTheme("dark")}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              theme === "dark"
                ? "bg-[var(--color-text)] text-[var(--color-bg)]"
                : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)]"
            }`}
          >
            Dark
          </button>
        </div>
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="px-6 py-2 text-sm font-semibold bg-[var(--color-accent)] text-white rounded-none hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {downloading ? "Exporting..." : "Download PNG"}
        </button>
      </div>

      {/* Preview */}
      <div className="border border-[var(--color-border)] shadow-lg" style={{ width: 1250, height: 500 }}>
        <ShareImage
          ref={captureRef}
          runs={runs}
          task={context.task}
          leaderboardRuns={leaderboard!.runs}
          theme={theme}
          title={title || undefined}
          titleFontSize={fontSize}
        />
      </div>
    </div>
  );
}
