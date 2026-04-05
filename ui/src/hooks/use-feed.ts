import { useCallback, useRef, useState } from "react";
import useSWR from "swr";
import { FeedItem } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface FeedResponse {
  items: FeedItem[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export function useFeed(taskId: string) {
  const [extraItems, setExtraItems] = useState<FeedItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(1);

  const { data, isLoading, mutate } = useSWR<FeedResponse>(
    taskId ? `/tasks/${taskId}/feed?page=1&per_page=50` : null,
    apiFetch,
    {
      revalidateOnFocus: false,
      dedupingInterval: 5000,
      onSuccess: (d) => {
        setHasMore(d.has_next);
        pageRef.current = 1;
        setExtraItems([]);
      },
    },
  );

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return;
    const nextPage = pageRef.current + 1;
    setLoadingMore(true);
    apiFetch<FeedResponse>(`/tasks/${taskId}/feed?page=${nextPage}&per_page=50`)
      .then((d) => {
        pageRef.current = nextPage;
        setExtraItems((prev) => [...prev, ...d.items]);
        setHasMore(d.has_next);
      })
      .catch(() => setHasMore(false))
      .finally(() => setLoadingMore(false));
  }, [taskId, loadingMore, hasMore]);

  const items = data ? [...data.items, ...extraItems] : [];

  return { items, loading: isLoading, loadingMore, hasMore, loadMore, refetch: () => mutate() };
}
