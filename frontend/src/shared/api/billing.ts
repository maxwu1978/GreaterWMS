/**
 * Typed API module for billing: rate cards, invoices, and tenant billing profile.
 */

import api from "./client";

export function fetchRateCards(): Promise<any> {
  return api.get("/billing/rate-cards").then((r) => r.data);
}

export function createRateCard(payload: Record<string, unknown>): Promise<any> {
  return api.post("/billing/rate-cards", payload).then((r) => r.data);
}

/** GET /billing/invoices?<query> — caller builds the query string (URLSearchParams). */
export function fetchBillingInvoices(query: string): Promise<any> {
  return api.get(`/billing/invoices?${query}`).then((r) => r.data);
}

export function calculateBilling(payload: Record<string, unknown>): Promise<any> {
  return api.post("/billing/calculate", payload).then((r) => r.data);
}

export function createBillingInvoice(payload: Record<string, unknown>): Promise<any> {
  return api.post("/billing/invoice", payload).then((r) => r.data);
}

export function updateBillingInvoiceStatus(invoiceId: string, status: string): Promise<any> {
  return api.patch(`/billing/invoice/${invoiceId}/status`, { status }).then((r) => r.data);
}

/** Invoice PDF as a binary blob (full axios response). */
export function fetchBillingInvoicePdf(invoiceId: string) {
  return api.get(`/billing/invoice/${invoiceId}/pdf`, { responseType: "blob" });
}

export function fetchCurrentTenant(): Promise<any> {
  return api.get("/tenants/current").then((r) => r.data);
}

export function updateTenantSettings(payload: Record<string, unknown>) {
  return api.patch("/tenants/current/settings", payload);
}
