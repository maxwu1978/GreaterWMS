/**
 * Typed API module for the client portal.
 */

import api from "./client";

export function fetchPortalDashboard(): Promise<any> {
  return api.get("/portal/dashboard").then((r) => r.data);
}

export function fetchPortalOutboundOrders(): Promise<any> {
  return api.get("/portal/orders/outbound").then((r) => r.data);
}

export function fetchPortalInvoices(): Promise<any> {
  return api.get("/portal/invoices").then((r) => r.data);
}

export function fetchPortalInventory(): Promise<any> {
  return api.get("/portal/inventory").then((r) => r.data);
}
