import { useCallback, useEffect, useState } from "react";
import { FeedItem } from "@/types/api";
import { apiFetch } from "@/lib/api";

export function useFeed(taskId: string): { items: FeedItem[]; loading: boolean; refetch: () => void } {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchFeed = useCallback(() => {
    setLoading(true);
    apiFetch<{ items: FeedItem[] }>(`/tasks/${taskId}/feed`)
      .then((data) => setItems(data.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [taskId]);

  useEffect(() => {
    fetchFeed();
  }, [fetchFeed]);

  return { items, loading, refetch: fetchFeed };
}
