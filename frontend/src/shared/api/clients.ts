/**
 * Typed API module for client (customer) directory lookups.
 * The intake page's no-trailing-slash variant lives in ./migration.ts.
 */

import api from "./client";

/** GET /clients/ — raw body (page object with `items` on this endpoint). */
export function fetchClients(params?: { limit?: number; offset?: number }): Promise<any> {
  if (!params) {
    return api.get("/clients/").then((r) => r.data);
  }
  return api.get("/clients/", { params }).then((r) => r.data);
}

export function createClient(payload: Record<string, unknown>) {
  return api.post("/clients/", payload);
}

export function updateClient(clientId: string, payload: Record<string, unknown>) {
  return api.patch(`/clients/${clientId}`, payload);
}
