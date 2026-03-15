import { mockContext } from "@/data/mock-context";
import { ContextResponse } from "@/types/api";

export function useContext(taskId: string): ContextResponse | null {
  // Swap for: const res = await fetch(`/tasks/${taskId}/context`); return res.json();
  return mockContext[taskId] ?? null;
}
