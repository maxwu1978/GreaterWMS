/**
 * Typed API module for SKU master data.
 * The workbench directory variant ("/skus" without trailing slash) lives in
 * ./directories.ts; the intake variant lives in ./migration.ts.
 */

import api from "./client";

/** GET /skus/?limit=500 — page object with `items`. */
export function fetchSkusPage(): Promise<any> {
  return api.get("/skus/?limit=500").then((r) => r.data);
}

export function createSku(payload: Record<string, unknown>) {
  return api.post("/skus/", payload);
}
