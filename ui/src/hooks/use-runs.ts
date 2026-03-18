import { useCallback, useEffect, useRef, useState } from "react";
import { Run, LeaderboardResponse } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface RunsResponse {
  runs: Run[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export function useRuns(taskId: string) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(1);

  const fetchRuns = useCallback(() => {
    pageRef.current = 1;
    setLoading(true);
    apiFetch<RunsResponse>(`/tasks/${taskId}/runs?sort=recent&page=1&per_page=50`)
      .then((data) => {
        setRuns(data.runs);
        setHasMore(data.has_next);
      })
      .catch(() => {
        setRuns([]);
        setHasMore(false);
      })
      .finally(() => setLoading(false));
  }, [taskId]);

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return;
    const nextPage = pageRef.current + 1;
    setLoadingMore(true);
    apiFetch<RunsResponse>(`/tasks/${taskId}/runs?sort=recent&page=${nextPage}&per_page=50`)
      .then((data) => {
        pageRef.current = nextPage;
        setRuns((prev) => [...prev, ...data.runs]);
        setHasMore(data.has_next);
      })
      .catch(() => setHasMore(false))
      .finally(() => setLoadingMore(false));
  }, [taskId, loadingMore, hasMore]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  return { runs, loading, loadingMore, hasMore, loadMore };
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
