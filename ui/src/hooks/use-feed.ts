import { mockFeedItems } from "@/data/mock-feed";
import { FeedItem } from "@/types/api";

export function useFeed(taskId: string): { items: FeedItem[] } {
  // Swap for: const res = await fetch(`/tasks/${taskId}/feed`); return res.json();
  void taskId;
  return { items: mockFeedItems };
}
