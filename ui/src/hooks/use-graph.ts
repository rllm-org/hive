import useSWR from "swr";
import { Run } from "@/types/api";
import { apiFetch } from "@/lib/api";

interface GraphNode {
  sha: string;
  agent_id: string;
  score: number | null;
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

function mapNodes(data: GraphResponse, taskId: string): Run[] {
  return data.nodes.map((n) => ({
    id: n.sha,
    task_id: taskId,
    agent_id: n.agent_id,
    branch: "",
    parent_id: n.parent,
    tldr: n.tldr,
    message: "",
    score: n.score,
    verified: false,
    valid: n.valid !== false,
    created_at: n.created_at,
  }));
}

export function useGraph(taskId: string) {
  const { data, isLoading } = useSWR<GraphResponse>(
    taskId ? `/tasks/${taskId}/graph?max_nodes=1000` : null,
    apiFetch,
    { revalidateOnFocus: false, dedupingInterval: 10000 },
  );

  return { runs: data ? mapNodes(data, taskId) : [], loading: isLoading };
}
