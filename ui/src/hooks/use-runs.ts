import { mockRuns, mockBestRuns, mockContributors, mockDeltas, mockImprovers } from "@/data/mock-runs";
import { Run, LeaderboardResponse } from "@/types/api";

export function useRuns(taskId: string): Run[] {
  // Swap for: fetch all runs for chart/tree
  void taskId;
  return mockRuns;
}

export function useLeaderboard(taskId: string, view: string): LeaderboardResponse {
  // Swap for: const res = await fetch(`/tasks/${taskId}/runs?view=${view}`); return res.json();
  void taskId;
  switch (view) {
    case "contributors": return mockContributors;
    case "deltas": return mockDeltas;
    case "improvers": return mockImprovers;
    default: return mockBestRuns;
  }
}
