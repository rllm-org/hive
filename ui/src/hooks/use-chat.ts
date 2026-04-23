import useSWR from "swr";
import { apiFetch } from "@/lib/api";

export interface Channel {
  id: number;
  task_id: number;
  name: string;
  is_default: boolean;
  created_by: string | null;
  created_at: string;
}

export type AuthorKind = "agent" | "user";

export interface MessageAuthor {
  kind: AuthorKind;
  id: string | number;
  display: string;
  handle: string | null;
  /** Profile picture URL — only set for user authors with a connected avatar. */
  avatar_url: string | null;
}

export interface ThreadParticipant {
  kind: AuthorKind;
  name: string;
  /** Profile picture URL — only set for user participants with a connected avatar. */
  avatar_url: string | null;
}

export interface Message {
  channel_id: number;
  ts: string;
  agent_id: string | null;
  user_id: number | null;
  author: MessageAuthor;
  text: string;
  thread_ts: string | null;
  mentions: string[];
  edited_at: string | null;
  created_at: string;
  reply_count: number;
  thread_participants: ThreadParticipant[];
}

interface ChannelsResponse {
  channels: Channel[];
}

interface MessagesResponse {
  channel: Channel;
  messages: Message[];
  has_more: boolean;
}

interface RepliesResponse {
  channel: Channel;
  parent: Message;
  replies: Message[];
}

const POLL_MS = 5000;

export type AgentType = "local" | "cloud" | "persistent";

export interface HarnessUsage {
  harness: string;
  model: string;
  run_count: number;
  last_used: string;
}

export interface AgentProfile {
  id: string;
  registered_at: string;
  last_seen_at: string;
  total_runs: number;
  owner_handle: string | null;
  type: AgentType;
  harness: string;
  model: string;
  avatar_seed: string | null;
  workspace_id: number | null;
  role: string | null;
  description: string | null;
  /** Per harness/model run counts, derived from the runs table. */
  harnesses: HarnessUsage[];
}

export function useAgent(agentId: string | null) {
  const { data, isLoading } = useSWR<AgentProfile>(
    agentId ? `/agents/${agentId}` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 30_000 },
  );
  return { agent: data ?? null, loading: isLoading };
}

export interface UserProfile {
  id: number;
  handle: string;
  avatar_url: string | null;
  avatar_seed: string | null;
  created_at: string;
  agent_count: number;
}

export function useUser(handle: string | null) {
  const { data, isLoading } = useSWR<UserProfile>(
    handle ? `/users/${handle}` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 30_000 },
  );
  return { user: data ?? null, loading: isLoading };
}

export interface AgentSummary {
  id: string;
  total_runs: number;
  owner_handle: string | null;
  type: AgentType;
  harness: string;
  model: string;
  avatar_seed: string | null;
  last_seen_at: string | null;
  role: string | null;
  description: string | null;
}

export function useAgents(query: string, enabled: boolean) {
  const key = enabled
    ? `/agents?limit=20${query ? `&q=${encodeURIComponent(query)}` : ""}`
    : null;
  const { data, isLoading } = useSWR<{ agents: AgentSummary[] }>(key, apiFetch, {
    revalidateOnFocus: false,
    dedupingInterval: 5_000,
    keepPreviousData: true,
  });
  return { agents: data?.agents ?? [], loading: isLoading };
}

/** Agents who have participated in a specific task (messages or runs). */
export function useTaskAgents(taskPath: string) {
  const { data, isLoading } = useSWR<{ agents: AgentSummary[] }>(
    taskPath ? `/tasks/${taskPath}/agents` : null,
    apiFetch,
    { refreshInterval: 30_000, revalidateOnFocus: true },
  );
  return { agents: data?.agents ?? [], loading: isLoading };
}

/** Fetch user's workspaces as Channel-shaped items for the sidebar. */
export function useWorkspaceChannels() {
  const { data, isLoading, mutate } = useSWR<{ workspaces: Array<{ id: number; name: string; created_at: string }> }>(
    "/workspaces",
    apiFetch,
    { refreshInterval: POLL_MS, revalidateOnFocus: true },
  );
  const channels: Channel[] = (data?.workspaces ?? []).map((w) => ({
    id: w.id,
    task_id: 0,
    name: w.name,
    is_default: false,
    created_by: null,
    created_at: w.created_at,
  }));
  return {
    channels,
    loading: isLoading,
    refetch: () => mutate(),
    workspaces: data?.workspaces ?? [],
  };
}

/** @param taskPath - "owner/slug" identifier */
export function useChannels(taskPath: string) {
  const { data, isLoading, mutate } = useSWR<ChannelsResponse>(
    taskPath ? `/tasks/${taskPath}/channels` : null,
    apiFetch,
    { refreshInterval: POLL_MS, revalidateOnFocus: true },
  );
  return {
    channels: data?.channels ?? [],
    loading: isLoading,
    refetch: () => mutate(),
  };
}

/** Fetch messages for a workspace. */
export function useWorkspaceMessages(workspaceId: number | null) {
  const key = workspaceId != null ? `/workspaces/${workspaceId}/messages` : null;
  const { data, isLoading, mutate } = useSWR<MessagesResponse>(key, apiFetch, {
    refreshInterval: POLL_MS,
    revalidateOnFocus: true,
  });
  return {
    channel: data?.channel ?? null,
    messages: data?.messages ?? [],
    hasMore: data?.has_more ?? false,
    loading: isLoading,
    refetch: () => mutate(),
  };
}

/** Fetch agents in a workspace. */
export function useWorkspaceAgentsList(workspaceId: number | null) {
  const { data, isLoading, mutate } = useSWR<{ agents: AgentSummary[] }>(
    workspaceId != null ? `/workspaces/${workspaceId}/agents` : null,
    apiFetch,
    { refreshInterval: POLL_MS, revalidateOnFocus: true },
  );
  return {
    agents: data?.agents ?? [],
    loading: isLoading,
    refetch: () => mutate(),
  };
}

/** @param taskPath - "owner/slug" identifier */
export function useMessages(taskPath: string, channelName: string | null) {
  const key = taskPath && channelName ? `/tasks/${taskPath}/channels/${channelName}/messages` : null;
  const { data, isLoading, mutate } = useSWR<MessagesResponse>(key, apiFetch, {
    refreshInterval: POLL_MS,
    revalidateOnFocus: true,
  });
  return {
    channel: data?.channel ?? null,
    messages: data?.messages ?? [],
    hasMore: data?.has_more ?? false,
    loading: isLoading,
    refetch: () => mutate(),
  };
}

/** @param taskPath - "owner/slug" identifier */
export function useThread(taskPath: string, channelName: string | null, ts: string | null) {
  const key = taskPath && channelName && ts
    ? `/tasks/${taskPath}/channels/${channelName}/messages/${ts}/replies`
    : null;
  const { data, isLoading, mutate } = useSWR<RepliesResponse>(key, apiFetch, {
    refreshInterval: POLL_MS,
    revalidateOnFocus: true,
  });
  return {
    parent: data?.parent ?? null,
    replies: data?.replies ?? [],
    loading: isLoading,
    refetch: () => mutate(),
  };
}

export function useWorkspaceThread(workspaceId: number | null, ts: string | null) {
  const key = workspaceId != null && ts
    ? `/workspaces/${workspaceId}/messages/${ts}/replies`
    : null;
  const { data, isLoading, mutate } = useSWR<RepliesResponse>(key, apiFetch, {
    refreshInterval: POLL_MS,
    revalidateOnFocus: true,
  });
  return {
    parent: data?.parent ?? null,
    replies: data?.replies ?? [],
    loading: isLoading,
    refetch: () => mutate(),
  };
}
