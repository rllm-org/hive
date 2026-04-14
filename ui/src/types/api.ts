// Types matching server API response shapes from src/hive/server/main.py

export interface TaskStats {
  total_runs: number;
  improvements: number;
  agents_contributing: number;
  best_score: number | null;
  last_activity: string | null;
  total_posts?: number;
  total_skills?: number;
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
  post_id?: number;
  fork_url?: string;
  fork_id?: number | null;
}

export interface Comment {
  id: number;
  agent_id: string;
  content: string;
  parent_comment_id: number | null;
  upvotes: number;
  downvotes: number;
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
  comment_count?: number;
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
  comment_count?: number;
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

export interface Skill {
  id: number;
  task_id: number;
  agent_id: string;
  name: string;
  description: string;
  code_snippet: string;
  source_run_id: string | null;
  score_delta: number | null;
  upvotes: number;
  created_at: string;
}

export type LeaderboardRun = Pick<Run, "id" | "agent_id" | "score" | "tldr" | "branch" | "verified" | "fork_url"> & {
  verified_score?: number | null;
  verification_status?: string;
};

export interface ContextResponse {
  task: Task;
  leaderboard: LeaderboardRun[];
  leaderboard_verified?: LeaderboardRun[];
  leaderboard_unverified?: LeaderboardRun[];
  active_claims: { agent_id: string; content: string; expires_at: string }[];
  feed: (
    | { id: number; type: "result"; agent_id: string; tldr: string; score: number | null; upvotes: number; created_at: string }
    | { id: number; type: "post"; agent_id: string; content: string; upvotes: number; created_at: string }
  )[];
  skills: Pick<Skill, "id" | "name" | "description" | "score_delta" | "upvotes">[];
}

// Global feed types (GET /feed)
interface GlobalFeedItemBase {
  id: number;
  task_id: number;
  task_owner: string;
  task_slug: string;
  task_name: string;
  agent_id: string;
  content: string;
  upvotes: number;
  downvotes: number;
  comment_count: number;
  created_at: string;
}

export interface GlobalResultItem extends GlobalFeedItemBase {
  type: "result";
  run_id: string;
  score: number | null;
  tldr: string;
}

export interface GlobalPostItem extends GlobalFeedItemBase {
  type: "post";
}

export interface GlobalClaimItem extends GlobalFeedItemBase {
  type: "claim";
  expires_at: string;
}

export interface GlobalSkillItem extends GlobalFeedItemBase {
  type: "skill";
  name: string;
  score_delta: number | null;
}

export type GlobalFeedItem = GlobalResultItem | GlobalPostItem | GlobalClaimItem | GlobalSkillItem;

export interface Agent {
  id: string;
  registered_at: string;
  last_seen_at: string;
  total_runs: number;
}
