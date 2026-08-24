import api from "./client";

export type ReceivingWorkbenchSummary = {
  total_orders: number;
  active_orders: number;
  archived_orders: number;
  voided_orders: number;
  completed_orders: number;
  by_status: Record<string, number>;
  packages_open: number;
  packages_putaway_pending: number;
  packages_stored: number;
  internal_labels_print_pending: number;
};

export type PutawayWorkbenchSummary = {
  total_tasks: number;
  pending_tasks: number;
  assigned_tasks: number;
  in_progress_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  pending_units: number;
  by_status: Record<string, number>;
  by_assigned_type: Record<string, number>;
};

export type PickingWorkbenchSummary = {
  total_orders: number;
  by_status: Record<string, number>;
  total_ordered_units: number;
  total_allocated_units: number;
  total_picked_units: number;
  pending_pick_tasks: number;
  active_pick_tasks: number;
};

export type InventoryWorkbenchSummary = {
  inventory_rows: number;
  client_count: number;
  sku_count: number;
  location_count: number;
  on_hand_units: number;
  allocated_units: number;
  damaged_units: number;
  available_units: number;
};

export const workbenchSummaryKeys = {
  receiving: ["workbench-summary", "receiving"] as const,
  putaway: ["workbench-summary", "putaway"] as const,
  picking: ["workbench-summary", "picking"] as const,
  inventory: ["workbench-summary", "inventory"] as const,
};

export function fetchReceivingWorkbenchSummary() {
  return api
    .get<ReceivingWorkbenchSummary>("/workbench-summaries/receiving")
    .then((response) => response.data);
}

export function fetchPutawayWorkbenchSummary() {
  return api
    .get<PutawayWorkbenchSummary>("/workbench-summaries/putaway")
    .then((response) => response.data);
}

export function fetchPickingWorkbenchSummary() {
  return api
    .get<PickingWorkbenchSummary>("/workbench-summaries/picking")
    .then((response) => response.data);
}

export function fetchInventoryWorkbenchSummary() {
  return api
    .get<InventoryWorkbenchSummary>("/workbench-summaries/inventory")
    .then((response) => response.data);
}
