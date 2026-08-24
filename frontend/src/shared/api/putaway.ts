/**
 * Typed API module for putaway suggestions.
 */

import api from "./client";

export type PutawaySuggestionRequest = {
  warehouse_id: string;
  sku_id: string;
  quantity: number;
  source_location_id?: string | null;
};

/** POST /fulfillment/putaway/suggest-location — raw response body. */
export function suggestPutawayLocation(payload: PutawaySuggestionRequest): Promise<any> {
  return api.post("/fulfillment/putaway/suggest-location", payload).then((r) => r.data);
}
