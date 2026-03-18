import { useCallback, useEffect, useRef, useState } from "react";
import { FeedItem } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface FeedResponse {
  items: FeedItem[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export function useFeed(taskId: string) {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(1);

  const fetchFeed = useCallback(() => {
    pageRef.current = 1;
    setLoading(true);
    apiFetch<FeedResponse>(`/tasks/${taskId}/feed?page=1&per_page=50`)
      .then((data) => {
        setItems(data.items);
        setHasMore(data.has_next);
      })
      .catch(() => {
        setItems([]);
        setHasMore(false);
      })
      .finally(() => setLoading(false));
  }, [taskId]);

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return;
    const nextPage = pageRef.current + 1;
    setLoadingMore(true);
    apiFetch<FeedResponse>(`/tasks/${taskId}/feed?page=${nextPage}&per_page=50`)
      .then((data) => {
        pageRef.current = nextPage;
        setItems((prev) => [...prev, ...data.items]);
        setHasMore(data.has_next);
      })
      .catch(() => setHasMore(false))
      .finally(() => setLoadingMore(false));
  }, [taskId, loadingMore, hasMore]);

  useEffect(() => {
    fetchFeed();
  }, [fetchFeed]);

  return { items, loading, loadingMore, hasMore, loadMore, refetch: fetchFeed };
}
