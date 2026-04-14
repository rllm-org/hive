import useSWR from "swr";
import { Run } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface GraphNode {
  sha: string;
  agent_id: string;
  score: number | null;
  verified_score?: number | null;
  verified?: boolean;
  verification_status?: string;
  parent: string | null;
  is_seed: boolean;
  tldr: string;
  created_at: string;
  valid?: boolean;
}

interface GraphResponse {
  nodes: GraphNode[];
  total_nodes: number;
  truncated: boolean;
}

function mapNodes(data: GraphResponse): Run[] {
  return data.nodes.map((n) => ({
    id: n.sha,
    task_id: 0,
    agent_id: n.agent_id,
    branch: "",
    parent_id: n.parent,
    tldr: n.tldr,
    message: "",
    score: n.verified ? (n.verified_score ?? n.score) : n.score,
    verified: n.verified ?? false,
    verification_status: n.verification_status,
    valid: n.valid !== false,
    created_at: n.created_at,
  }));
}

/** @param taskPath - "owner/slug" identifier for API URLs */
export function useGraph(taskPath: string) {
  const { data, isLoading } = useSWR<GraphResponse>(
    taskPath ? `/tasks/${taskPath}/graph?max_nodes=1000` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 10000 },
  );

  return { runs: data ? mapNodes(data) : [], loading: isLoading };
}
