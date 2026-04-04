import useSWR, { useSWRConfig } from "swr";
import { Item, ItemsResponse, ItemActivity, ItemActivityResponse } from "@/types/items";
import { apiFetch } from "@/lib/api";

export function useItems(taskId: string, status?: string) {
  const qs = status ? `&status=${status}` : "";
  const { data, isLoading, mutate } = useSWR<ItemsResponse>(
    taskId ? `/tasks/${taskId}/items?per_page=100${qs}` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 5000 },
  );

  return {
    items: data?.items ?? [],
    loading: isLoading,
    mutate,
  };
}

export function useItemActivity(taskId: string, itemId: string | null) {
  const { data, isLoading, mutate } = useSWR<ItemActivityResponse>(
    taskId && itemId ? `/tasks/${taskId}/items/${itemId}/activity?per_page=50` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 5000 },
  );

  return {
    activities: data?.activities ?? [],
    loading: isLoading,
    mutate,
  };
}

export function useMutateAllItems() {
  const { mutate } = useSWRConfig();
  return (taskId: string) =>
    mutate(
      (key: unknown) => typeof key === "string" && key.startsWith(`/tasks/${taskId}/items`),
      undefined,
      { revalidate: true },
    );
}
