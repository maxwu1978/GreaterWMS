/**
 * Typed API module for outbound orders (detail + shipping documents).
 * Paged lists live in ./orderLists.ts; CSV import lives in ./migration.ts.
 */

import api from "./client";

export function fetchOutboundOrderDetail(orderId: string): Promise<any> {
  return api.get(`/order-details/outbound/${orderId}`).then((r) => r.data);
}

export function createOutboundOrder(payload: Record<string, unknown>): Promise<any> {
  return api.post("/orders/outbound", payload).then((r) => r.data);
}

/** Packing slip PDF as a binary blob. */
export function fetchPackingSlipPdf(orderDetailId: string) {
  return api.get(`/shipping/packing-slip/${orderDetailId}/pdf`, {
    responseType: "blob",
  });
}
