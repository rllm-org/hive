import { mockTasks } from "@/data/mock-tasks";
import { Task } from "@/types/api";

export function useTasks(): { tasks: Task[] } {
  // Swap for: const res = await fetch('/tasks'); return res.json();
  return { tasks: mockTasks };
}
