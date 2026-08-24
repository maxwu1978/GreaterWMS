/**
 * Typed API module for the data-migration / intake page: CSV imports and
 * manual order/inventory creation.
 *
 * NOTE: some list URLs here intentionally omit the trailing slash
 * ("/clients?limit=500", "/skus?...") to stay byte-identical with the
 * previous inline calls.
 */

import api from "./client";

// --- directories used by the intake forms ----------------------------------

export function fetchMigrationClients(): Promise<any> {
  return api.get("/clients?limit=500").then((r) => r.data);
}

export function fetchClientSkus(clientId: string): Promise<any> {
  return api.get(`/skus?client_id=${clientId}&limit=500`).then((r) => r.data);
}

// --- CSV imports ------------------------------------------------------------

const MULTIPART = { headers: { "Content-Type": "multipart/form-data" } } as const;

export function importInventoryCsv(warehouseId: string, form: FormData): Promise<any> {
  return api.post(`/data/inventory/csv?warehouse_id=${warehouseId}`, form, MULTIPART).then((r) => r.data);
}

export function previewInboundCsv(formData: FormData): Promise<any> {
  return api.post("/receiving/inbound/import-csv/preview", formData, MULTIPART).then((r) => r.data);
}

/** Returns the full axios response (caller destructures `{ data }` in onSuccess). */
export function importInboundCsv(formData: FormData) {
  return api.post("/receiving/inbound/import-csv", formData, MULTIPART);
}

export function previewOutboundCsv(formData: FormData): Promise<any> {
  return api.post("/orders/outbound/import-csv/preview", formData, MULTIPART).then((r) => r.data);
}

export function importOutboundCsv(formData: FormData): Promise<any> {
  return api.post("/orders/outbound/import-csv", formData, MULTIPART).then((r) => r.data);
}

// --- manual creation --------------------------------------------------------

export function createManualInboundOrder(payload: Record<string, unknown>): Promise<any> {
  return api.post("/receiving/inbound", payload).then((r) => r.data);
}

export function createManualInventory(payload: Record<string, unknown>): Promise<any> {
  return api.post("/data/inventory/manual", payload).then((r) => r.data);
}
