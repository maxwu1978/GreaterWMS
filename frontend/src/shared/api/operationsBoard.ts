import api from "./client";

export type OperationsBoardLane = "now" | "next" | "delayed" | "blocked";

export type OperationsBoardItem = {
  id: string;
  category: string;
  operation: string;
  lane: OperationsBoardLane;
  source_status: string;
  reference_type: string;
  reference_id: string;
  reference_number: string;
  client_id?: string | null;
  client_name?: string | null;
  priority: number;
  due_at?: string | null;
  created_at?: string | null;
  quantity: number;
  quantity_progress?: number | null;
  location_label?: string | null;
  assigned_type?: string | null;
  assigned_to?: string | null;
  action_key: string;
  action_route: string;
  blocker_code?: string | null;
};

export type OperationsBoardResponse = {
  generated_at: string;
  warehouse_id?: string | null;
  items: OperationsBoardItem[];
  counts: {
    total: number;
    now: number;
    next: number;
    delayed: number;
    blocked: number;
    by_operation: Record<string, number>;
  };
};

export function fetchOperationsBoard(): Promise<OperationsBoardResponse> {
  return api.get("/operations/board").then((response) => response.data);
}
