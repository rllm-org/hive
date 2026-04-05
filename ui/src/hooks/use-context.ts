import useSWR from "swr";
import { ContextResponse } from "@/types/api";
import { apiFetch } from "@/lib/api";

export function useContext(taskId: string) {
  const { data, error, isLoading, mutate } = useSWR<ContextResponse>(
    taskId ? `/tasks/${taskId}/context` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 5000 },
  );

  return { data: data ?? null, loading: isLoading, error: error?.message ?? null, refetch: () => mutate() };
}
