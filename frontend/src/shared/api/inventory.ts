/**
 * Typed API module for inventory queries and stock operations.
 */

import api from "./client";

export type InventoryListResult = {
  items: any[];
  total: number;
  has_more: boolean;
  total_is_estimate?: boolean;
};

/** GET /inventory/ with raw response body (array or page object, backend-dependent). */
export function fetchInventoryRaw(params: Record<string, unknown>): Promise<any> {
  return api.get("/inventory/", { params }).then((r) => r.data);
}

/** GET /inventory/ normalized to `{ items, total, has_more }`. */
export function fetchInventoryList(params: Record<string, unknown>): Promise<InventoryListResult> {
  return api.get("/inventory/", { params }).then((r) => {
    const d = r.data;
    if (d && typeof d === "object" && "items" in d) return d;
    if (Array.isArray(d)) return { items: d, total: d.length, has_more: false };
    return { items: [], total: 0, has_more: false };
  });
}

export function adjustInventory(payload: { inventory_id: string; new_quantity: number; reason: string }) {
  return api.post("/inventory/ops/adjust", payload);
}

export function generateCycleCount(payload: { warehouse_id: string; location_ids: string[] }) {
  return api.post("/cycle-count/generate", payload);
}

export function recordCycleCount(payload: Record<string, unknown>) {
  return api.post("/cycle-count/record", payload);
}

/** GET /reports/activity?days=N — raw body. */
export function fetchActivityReport(days: number): Promise<any> {
  return api.get(`/reports/activity?days=${days}`).then((r) => r.data);
}
