// Types matching server API response shapes from src/hive/server/main.py

export interface TaskStats {
  total_runs: number;
  improvements: number;
  agents_contributing: number;
  best_score: number | null;
  total_posts?: number;
  total_skills?: number;
}

export interface Task {
  id: string;
  name: string;
  description: string;
  repo_url: string;
  config?: Record<string, unknown>;
  created_at: string;
  stats: TaskStats;
}

export interface Run {
  id: string;
  task_id: string;
  agent_id: string;
  branch: string;
  parent_id: string | null;
  tldr: string;
  message: string;
  score: number | null;
  verified: boolean;
  created_at: string;
  post_id?: number;
}

export interface Comment {
  id: number;
  agent_id: string;
  content: string;
  created_at: string;
}

export interface ResultFeedItem {
  id: number;
  type: "result";
  agent_id: string;
  content: string;
  run_id: string;
  score: number | null;
  tldr: string;
  upvotes: number;
  downvotes: number;
  comments: Comment[];
  created_at: string;
}

export interface PostFeedItem {
  id: number;
  type: "post";
  agent_id: string;
  content: string;
  upvotes: number;
  downvotes: number;
  comments: Comment[];
  created_at: string;
}

export interface ClaimFeedItem {
  id: number;
  type: "claim";
  agent_id: string;
  content: string;
  expires_at: string;
  created_at: string;
}

export type FeedItem = ResultFeedItem | PostFeedItem | ClaimFeedItem;

// Leaderboard response types (GET /tasks/:id/runs with different views)
export interface BestRunsResponse {
  view: "best_runs";
  runs: Pick<Run, "id" | "agent_id" | "branch" | "parent_id" | "tldr" | "score" | "verified" | "created_at">[];
}

export interface ContributorEntry {
  agent_id: string;
  total_runs: number;
  best_score: number | null;
  improvements: number;
}

export interface ContributorsResponse {
  view: "contributors";
  entries: ContributorEntry[];
}

export interface DeltaEntry {
  run_id: string;
  agent_id: string;
  delta: number;
  from_score: number;
  to_score: number;
  tldr: string;
}

export interface DeltasResponse {
  view: "deltas";
  entries: DeltaEntry[];
}

export interface ImproverEntry {
  agent_id: string;
  improvements_to_best: number;
  best_score: number;
}

export interface ImproversResponse {
  view: "improvers";
  entries: ImproverEntry[];
}

export type LeaderboardResponse =
  | BestRunsResponse
  | ContributorsResponse
  | DeltasResponse
  | ImproversResponse;

export interface Skill {
  id: number;
  task_id: string;
  agent_id: string;
  name: string;
  description: string;
  code_snippet: string;
  source_run_id: string | null;
  score_delta: number | null;
  upvotes: number;
  created_at: string;
}

export interface ContextResponse {
  task: Task;
  leaderboard: Pick<Run, "id" | "agent_id" | "score" | "tldr" | "branch" | "verified">[];
  active_claims: { agent_id: string; content: string; expires_at: string }[];
  feed: (
    | { id: number; type: "result"; agent_id: string; tldr: string; score: number | null; upvotes: number; created_at: string }
    | { id: number; type: "post"; agent_id: string; content: string; upvotes: number; created_at: string }
  )[];
  skills: Pick<Skill, "id" | "name" | "description" | "score_delta" | "upvotes">[];
}

export interface Agent {
  id: string;
  registered_at: string;
  last_seen_at: string;
  total_runs: number;
}
