import { useCallback, useEffect, useRef, useState } from "react";
import { GlobalFeedItem } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface GlobalFeedResponse {
  items: GlobalFeedItem[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export function useGlobalFeed(sort: string) {
  const [items, setItems] = useState<GlobalFeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(1);

  const fetchFeed = useCallback(async () => {
    pageRef.current = 1;
    setLoading(true);
    try {
      const data = await apiFetch<GlobalFeedResponse>(`/feed?sort=${sort}&page=1&per_page=30`);
      setItems(data.items);
      setHasMore(data.has_next);
    } catch {
      setItems([]);
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }, [sort]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    const nextPage = pageRef.current + 1;
    setLoadingMore(true);
    try {
      const data = await apiFetch<GlobalFeedResponse>(`/feed?sort=${sort}&page=${nextPage}&per_page=30`);
      pageRef.current = nextPage;
      setItems((prev) => [...prev, ...data.items]);
      setHasMore(data.has_next);
    } catch {
      setHasMore(false);
    } finally {
      setLoadingMore(false);
    }
  }, [sort, loadingMore, hasMore]);

  useEffect(() => {
    fetchFeed();
  }, [fetchFeed]);

  return { items, loading, loadingMore, hasMore, loadMore, refetch: fetchFeed };
}
