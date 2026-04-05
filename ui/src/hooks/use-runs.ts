import { useCallback, useRef, useState } from "react";
import useSWR from "swr";
import { Run, LeaderboardResponse } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface RunsResponse {
  runs: Run[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export function useRuns(taskId: string) {
  const [extraRuns, setExtraRuns] = useState<Run[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(1);

  const { data, isLoading, mutate } = useSWR<RunsResponse>(
    taskId ? `/tasks/${taskId}/runs?sort=recent&page=1&per_page=50` : null,
    apiFetch,
    {
      revalidateOnFocus: false,
      dedupingInterval: 5000,
      onSuccess: (d) => {
        setHasMore(d.has_next);
        pageRef.current = 1;
        setExtraRuns([]);
      },
    },
  );

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return;
    const nextPage = pageRef.current + 1;
    setLoadingMore(true);
    apiFetch<RunsResponse>(`/tasks/${taskId}/runs?sort=recent&page=${nextPage}&per_page=50`)
      .then((d) => {
        pageRef.current = nextPage;
        setExtraRuns((prev) => [...prev, ...d.runs]);
        setHasMore(d.has_next);
      })
      .catch(() => setHasMore(false))
      .finally(() => setLoadingMore(false));
  }, [taskId, loadingMore, hasMore]);

  const runs = data ? [...data.runs, ...extraRuns] : [];

  return { runs, loading: isLoading, loadingMore, hasMore, loadMore, refetch: () => mutate() };
}

export function useLeaderboard(taskId: string, view: string): LeaderboardResponse | null {
  const { data } = useSWR<LeaderboardResponse>(
    taskId ? `/tasks/${taskId}/runs?view=${view}` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 5000 },
  );
  return data ?? null;
}
