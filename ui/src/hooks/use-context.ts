import { useCallback, useEffect, useState } from "react";
import { ContextResponse } from "@/types/api";
import { apiFetch } from "@/lib/api";

export function useContext(taskId: string) {
  const [data, setData] = useState<ContextResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    setLoading(true);
    apiFetch<ContextResponse>(`/tasks/${taskId}/context`)
      .then((res) => setData(res))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [taskId]);

  useEffect(() => { refetch(); }, [refetch]);

  return { data, loading, error, refetch };
}
