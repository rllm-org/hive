import useSWR from "swr";
import { ContextResponse } from "@/types/api";
import { apiFetch } from "@/lib/api";

/** @param taskPath - "owner/slug" identifier for API URLs */
export function useContext(taskPath: string) {
  const { data, error, isLoading, mutate } = useSWR<ContextResponse>(
    taskPath ? `/tasks/${taskPath}/context` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 5000 },
  );

  return { data: data ?? null, loading: isLoading, error: error?.message ?? null, refetch: () => mutate() };
}
