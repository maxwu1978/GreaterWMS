/**
 * Typed API module for inbound orders (list snapshots + lifecycle actions).
 * Paged/infinite lists live in ./orderLists.ts; receiving-workflow endpoints
 * live in ./receiving.ts.
 */

import api from "./client";

export type InboundOrderQueryParams = {
  include_archived?: boolean;
  offset?: number;
  limit?: number;
  status?: string;
  statuses?: string;
};

/** Plain (non-paged) GET /orders/inbound. Response is the raw order array. */
export function fetchInboundOrders(params?: InboundOrderQueryParams): Promise<any> {
  if (!params) {
    return api.get("/orders/inbound").then((r) => r.data);
  }
  return api.get("/orders/inbound", { params }).then((r) => r.data);
}

export function archiveInboundOrder(orderId: string, archived: boolean) {
  return api.post(`/orders/inbound/${orderId}/archive`, { archived });
}

export function voidInboundOrder(orderId: string) {
  return api.post(`/orders/inbound/${orderId}/void`);
}

export function deleteInboundOrder(orderId: string) {
  return api.delete(`/orders/inbound/${orderId}`);
}
