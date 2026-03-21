import { useCallback, useEffect, useState } from "react";
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

/** Fetch all runs via /graph endpoint and map to Run-compatible objects for charts. */
export function useGraph(taskId: string) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchGraph = useCallback(() => {
    setLoading(true);
    apiFetch<GraphResponse>(`/tasks/${taskId}/graph?max_nodes=1000`)
      .then((data) => {
        const mapped: Run[] = data.nodes.map((n) => ({
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
        setRuns(mapped);
      })
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
  }, [taskId]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  return { runs, loading };
}
