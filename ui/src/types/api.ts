// Types matching server API response shapes from src/hive/server/main.py

export interface TaskStats {
  total_runs: number;
  improvements: number;
  agents_contributing: number;
  best_score: number | null;
  last_activity: string | null;
}

export interface Task {
  id: number;
  slug: string;
  owner: string;
  name: string;
  description: string;
  repo_url: string;
  config?: Record<string, unknown>;
  created_at: string;
  stats: TaskStats;
  task_type?: "public" | "private";
  owner_id?: number;
  installation_id?: string | null;
  verification_enabled?: boolean;
}

/** Build the API path segment for a task: "owner/slug" */
export function taskPath(task: Task): string {
  return `${task.owner}/${task.slug}`;
}

/** Build the API path segment from owner and slug strings */
export function taskPathFrom(owner: string, slug: string): string {
  return `${owner}/${slug}`;
}

export interface SandboxInfo {
  sandbox_id: number;
  status: string;
  daytona_sandbox_id?: string | null;
  created_at: string;
  last_accessed_at?: string | null;
  ssh_command?: string;
  ssh_token?: string;
  ssh_expires_at?: string;
  error_message?: string;
}

export interface SandboxTerminalSessionRow {
  id: number;
  title: string | null;
  created_at: string;
  last_activity_at: string | null;
  closed_at: string | null;
}

export interface SandboxSessionCreateResponse {
  id: number;
  title: string | null;
  ticket: string;
  ticket_expires_at: string;
}

export interface Run {
  id: string;
  task_id: number;
  agent_id: string;
  branch: string;
  parent_id: string | null;
  tldr: string;
  message: string;
  score: number | null;
  verified: boolean;
  verified_score?: number | null;
  verification_status?: string;
  valid?: boolean;
  created_at: string;
  fork_url?: string;
  fork_id?: number | null;
}

// Leaderboard response types (GET /tasks/:id/runs with different views)
export interface BestRunsResponse {
  view: "best_runs";
  runs: Pick<Run, "id" | "agent_id" | "branch" | "parent_id" | "tldr" | "score" | "verified" | "created_at" | "fork_url">[];
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

export type LeaderboardRun = Pick<Run, "id" | "agent_id" | "score" | "tldr" | "branch" | "verified" | "fork_url"> & {
  verified_score?: number | null;
  verification_status?: string;
};

export interface ContextResponse {
  task: Task;
  leaderboard: LeaderboardRun[];
  leaderboard_verified?: LeaderboardRun[];
  leaderboard_unverified?: LeaderboardRun[];
}

export interface Agent {
  id: string;
  registered_at: string;
  last_seen_at: string;
  total_runs: number;
}
