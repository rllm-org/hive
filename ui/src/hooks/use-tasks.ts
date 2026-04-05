import { useCallback, useEffect, useRef, useState } from "react";
import { Task } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface TasksResponse {
  tasks: Task[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export function useTasks(type?: "public" | "private") {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const pageRef = useRef(1);
  const typeParam = type ? `&type=${type}` : "";

  const fetchTasks = useCallback(() => {
    pageRef.current = 1;
    apiFetch<TasksResponse>(`/tasks?page=1&per_page=50${typeParam}`)
      .then((data) => {
        setTasks(data.tasks);
        setHasMore(data.has_next);
      })
      .catch((err) => setError(err.message));
  }, [typeParam]);

  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return;
    const nextPage = pageRef.current + 1;
    setLoadingMore(true);
    apiFetch<TasksResponse>(`/tasks?page=${nextPage}&per_page=50${typeParam}`)
      .then((data) => {
        pageRef.current = nextPage;
        setTasks((prev) => [...(prev ?? []), ...data.tasks]);
        setHasMore(data.has_next);
      })
      .catch(() => setHasMore(false))
      .finally(() => setLoadingMore(false));
  }, [loadingMore, hasMore, typeParam]);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  return { tasks, error, hasMore, loadingMore, loadMore, refetch: fetchTasks };
}
