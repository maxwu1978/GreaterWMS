/**
 * Typed API module for lightweight SKU/client directory lookups used by the
 * workbench pages (inventory, putaway).
 *
 * NOTE: these endpoints are intentionally called without a trailing slash
 * ("/skus", "/clients") to stay byte-identical with the previous inline calls.
 */

import api from "./client";

export type DirectoryParams = { offset?: number; limit?: number };

/** GET /skus — raw body. */
export function fetchSkuDirectory(params: DirectoryParams): Promise<any> {
  return api.get("/skus", { params }).then((r) => r.data);
}

/** GET /clients — raw body. */
export function fetchClientDirectory(params: DirectoryParams): Promise<any> {
  return api.get("/clients", { params }).then((r) => r.data);
}
