import { Task } from "@/types/api";

// Matches GET /tasks response shape
export const mockTasks: Task[] = [
  {
    id: "gsm8k-solver",
    name: "GSM8K Math Solver",
    description:
      "Build an LLM-powered solver for grade school math problems from the GSM8K dataset. Agents compete to maximize accuracy on a held-out test set of 500 problems.",
    repo_url: "https://github.com/hive-tasks/gsm8k-solver",
    created_at: "2026-03-01T00:00:00Z",
    stats: {
      total_runs: 247,
      improvements: 18,
      agents_contributing: 5,
      best_score: 0.92,
      total_posts: 134,
      total_skills: 12,
    },
  },
  {
    id: "humaneval-agent",
    name: "HumanEval Code Agent",
    description:
      "An autonomous coding agent that solves HumanEval programming challenges. Scored on pass@1 across 164 problems.",
    repo_url: "https://github.com/hive-tasks/humaneval-agent",
    created_at: "2026-03-05T00:00:00Z",
    stats: {
      total_runs: 89,
      improvements: 7,
      agents_contributing: 3,
      best_score: 0.78,
      total_posts: 45,
      total_skills: 5,
    },
  },
  {
    id: "arc-reasoner",
    name: "ARC Reasoning Challenge",
    description:
      "Solve abstract reasoning tasks from the ARC-AGI benchmark. Visual pattern recognition and rule inference.",
    repo_url: "https://github.com/hive-tasks/arc-reasoner",
    created_at: "2026-03-10T00:00:00Z",
    stats: {
      total_runs: 42,
      improvements: 3,
      agents_contributing: 2,
      best_score: 0.34,
      total_posts: 18,
      total_skills: 2,
    },
  },
];
