/**
 * Typed API module for warehouse structure: warehouses, zones, locations,
 * racks, aisles, planner rules, and WCS point mappings.
 */

import api from "./client";

// --- warehouses -------------------------------------------------------------

/** GET /warehouses/?limit=200 — page object with `items`. */
export function fetchWarehousesPage(): Promise<any> {
  return api.get("/warehouses/?limit=200").then((r) => r.data);
}

/** GET /warehouses/ with explicit params (raw response body). */
export function fetchWarehouses(params?: { offset?: number; limit?: number }): Promise<any> {
  if (!params) {
    return api.get("/warehouses/").then((r) => r.data);
  }
  return api.get("/warehouses/", { params }).then((r) => r.data);
}

export function createWarehouse(payload: Record<string, unknown>) {
  return api.post("/warehouses/", payload);
}

export function updateWarehouse(warehouseId: string, payload: Record<string, unknown>) {
  return api.put(`/warehouses/${warehouseId}`, payload);
}

// --- zones ------------------------------------------------------------------

export function fetchWarehouseZones(warehouseId: string): Promise<any> {
  return api.get(`/warehouses/${warehouseId}/zones`).then((r) => r.data);
}

export function createWarehouseZone(warehouseId: string, payload: Record<string, unknown>): Promise<any> {
  return api.post(`/warehouses/${warehouseId}/zones`, payload);
}

export function updateWarehouseZone(warehouseId: string, zoneId: string | null, payload: Record<string, unknown>) {
  return api.put(`/warehouses/${warehouseId}/zones/${zoneId}`, payload);
}

export function deleteWarehouseZone(warehouseId: string, zoneId: string | null) {
  return api.delete(`/warehouses/${warehouseId}/zones/${zoneId}`);
}

// --- locations --------------------------------------------------------------

/** GET /warehouses/{id}/locations (optionally filtered by zone). Raw body. */
export function fetchWarehouseLocations(warehouseId: string, params?: { zone_id?: string | null }): Promise<any> {
  if (!params) {
    return api.get(`/warehouses/${warehouseId}/locations`).then((r) => r.data);
  }
  return api.get(`/warehouses/${warehouseId}/locations`, { params }).then((r) => r.data);
}

export function createWarehouseLocation(warehouseId: string, payload: Record<string, unknown>) {
  return api.post(`/warehouses/${warehouseId}/locations`, payload);
}

export function updateWarehouseLocation(warehouseId: string, locationId: string | null, payload: Record<string, unknown>) {
  return api.put(`/warehouses/${warehouseId}/locations/${locationId}`, payload);
}

export function deleteWarehouseLocation(warehouseId: string, locationId: string | null) {
  return api.delete(`/warehouses/${warehouseId}/locations/${locationId}`);
}

// --- racks / aisles ---------------------------------------------------------

export function configureRack(warehouseId: string, payload: Record<string, unknown>) {
  return api.put(`/warehouses/${warehouseId}/racks/configure`, payload);
}

export function createRack(warehouseId: string, payload: Record<string, unknown>) {
  return api.post(`/warehouses/${warehouseId}/racks`, payload);
}

export function deleteRack(warehouseId: string, payload: Record<string, unknown>) {
  return api.delete(`/warehouses/${warehouseId}/racks`, { data: payload });
}

export function configureAisle(warehouseId: string, payload: Record<string, unknown>) {
  return api.put(`/warehouses/${warehouseId}/aisles/configure`, payload);
}

export function createAisle(warehouseId: string, payload: Record<string, unknown>) {
  return api.post(`/warehouses/${warehouseId}/aisles`, payload);
}

export function deleteAisle(warehouseId: string, payload: Record<string, unknown>) {
  return api.delete(`/warehouses/${warehouseId}/aisles`, { data: payload });
}

// --- planner rules ----------------------------------------------------------

export function fetchPlannerRules(warehouseId: string): Promise<any> {
  return api.get(`/warehouses/${warehouseId}/planner-rules`).then((r) => r.data);
}

export function updatePlannerRules(warehouseId: string, rules: Record<string, unknown>) {
  return api.put(`/warehouses/${warehouseId}/planner-rules`, rules);
}

// --- WCS point mappings -----------------------------------------------------

export function fetchWcsPointMappings(params: { warehouse_id: string; include_unmapped: boolean }): Promise<any> {
  return api.get("/integrations/wcs/point-mappings", { params }).then((r) => r.data);
}

export function validateWcsPointMappings(payload: Record<string, unknown>) {
  return api.post("/integrations/wcs/point-mappings/validate", payload);
}

export function saveWcsPointMappings(payload: Record<string, unknown>) {
  return api.post("/integrations/wcs/point-mappings", payload);
}
