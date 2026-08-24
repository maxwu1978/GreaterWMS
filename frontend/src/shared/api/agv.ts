/**
 * Typed API module for AGV readiness and WCS bindings.
 */

import api from "./client";

export function fetchAgvPendingTasks(params: { warehouse_id: string; limit: number }): Promise<any> {
  return api.get("/agv/tasks/pending", { params }).then((r) => r.data);
}

export function fetchAgvLocationValidation(warehouseId: string): Promise<any> {
  return api.get(`/agv/locations/${warehouseId}/validate`).then((r) => r.data);
}

export function fetchWcsBindings(params: { warehouse_id: string; limit: number }): Promise<any> {
  return api.get("/integrations/wcs/bindings", { params }).then((r) => r.data);
}
