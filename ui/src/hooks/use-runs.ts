import { useEffect, useState } from "react";
import { Run, LeaderboardResponse } from "@/types/api";
import { apiFetch } from "@/lib/api";

export function useRuns(taskId: string): Run[] {
  const [runs, setRuns] = useState<Run[]>([]);

  useEffect(() => {
    apiFetch<{ runs: Run[] }>(`/tasks/${taskId}/runs?sort=recent&per_page=100`)
      .then((data) => setRuns(data.runs))
      .catch(() => setRuns([]));
  }, [taskId]);

  return runs;
}

export function useLeaderboard(taskId: string, view: string): LeaderboardResponse | null {
  const [data, setData] = useState<LeaderboardResponse | null>(null);

  useEffect(() => {
    apiFetch<LeaderboardResponse>(`/tasks/${taskId}/runs?view=${view}`)
      .then((res) => setData(res))
      .catch(() => setData(null));
  }, [taskId, view]);

  return data;
}
