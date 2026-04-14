import useSWR, { useSWRConfig } from "swr";
import { Item, ItemsResponse, ItemActivity, ItemActivityResponse } from "@/types/items";
import { apiFetch } from "@/lib/api";

/** @param taskPath - "owner/slug" identifier for API URLs */
export function useItems(taskPath: string, status?: string) {
  const qs = status ? `&status=${status}` : "";
  const { data, isLoading, mutate } = useSWR<ItemsResponse>(
    taskPath ? `/tasks/${taskPath}/items?per_page=100${qs}` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 5000 },
  );

  return {
    items: data?.items ?? [],
    loading: isLoading,
    mutate,
  };
}

/** @param taskPath - "owner/slug" identifier for API URLs */
export function useItemActivity(taskPath: string, itemId: string | null) {
  const { data, isLoading } = useSWR<ItemActivityResponse>(
    taskPath && itemId ? `/tasks/${taskPath}/items/${itemId}/activity?per_page=50` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 5000 },
  );

  return {
    activities: data?.activities ?? [],
    loading: isLoading,
  };
}

export function useMutateAllItems() {
  const { mutate } = useSWRConfig();
  return (taskPath: string) =>
    mutate(
      (key: unknown) => typeof key === "string" && key.startsWith(`/tasks/${taskPath}/items`),
      undefined,
      { revalidate: true },
    );
}
