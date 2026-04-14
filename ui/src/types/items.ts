export type ItemStatus = "backlog" | "in_progress" | "review" | "archived";
export type ItemPriority = "none" | "low" | "medium" | "high" | "urgent";

export interface Item {
  id: string;
  task_id: number;
  seq: number;
  title: string;
  description?: string | null;
  status: ItemStatus;
  priority: ItemPriority;
  assignee_id?: string | null;
  assigned_at?: string | null;
  parent_id?: string | null;
  labels: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
  comment_count: number;
}

export interface ItemActivity {
  type: "run" | "post" | "feed_comment" | "skill" | "item_comment";
  id: string;
  agent_id: string;
  content: string;
  score: number | null;
  created_at: string;
}

export interface ItemsResponse {
  items: Item[];
  page: number;
  per_page: number;
  has_next: boolean;
}

export interface ItemActivityResponse {
  activities: ItemActivity[];
  page: number;
  per_page: number;
  has_next: boolean;
}
