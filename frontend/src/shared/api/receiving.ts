/**
 * Typed API module for the receiving domain.
 *
 * URLs and payloads are byte-identical to the previous inline calls in
 * ReceivingFlow / ReceivingPage / the receiving settings pages — this module
 * only centralizes them behind typed functions.
 */

import api from "./client";

// ---------------------------------------------------------------------------
// Shared response types (moved here from modules/receiving/receivingFlowUtils
// so both the pages and this module can use them; receivingFlowUtils
// re-exports them for backwards compatibility).
// ---------------------------------------------------------------------------

export interface InboundReceivableOrder {
  id: string;
  warehouse_id: string;
  order_number: string;
  status: string;
  reference_number?: string | null;
}

export interface ObservedReceivingCode {
  id: string;
  code_value: string;
  code_type: string;
  source: string;
  is_primary: boolean;
  is_confirmed: boolean;
}

export interface ScannedReceivingLabel {
  matched_by?: string;
  opened_directly?: boolean;
  scanned_code?: string;
  label_code: string;
  label_type: string;
  status: string;
  package_id?: string;
  package_number?: number | null;
  package_status?: string;
  expected_qty: number;
  received_qty: number;
  remaining_qty: number;
  sku_id: string;
  line_id: string;
  lot_number?: string | null;
  expiry_date?: string | null;
  external_tracking_number?: string | null;
  external_carton_mark?: string | null;
  external_customer_barcode?: string | null;
  captured_codes?: ObservedReceivingCode[];
}

export interface ReceivingLabelSummary {
  id: string;
  label_code: string;
  label_type: string;
  package_id?: string | null;
  package_number?: number | null;
  package_type?: string | null;
  sku_code?: string | null;
  sku_name?: string | null;
  reference_number?: string | null;
  external_tracking_number?: string | null;
  external_carton_mark?: string | null;
  external_customer_barcode?: string | null;
  expected_qty: number;
  received_qty: number;
  status: string;
  lot_number?: string | null;
  printed_at?: string | null;
  print_count?: number;
  package_count?: number | null;
  pallet_count?: number | null;
  rent_free_days?: number | null;
  measured_weight_kg?: number | null;
  measured_length_cm?: number | null;
  measured_width_cm?: number | null;
  measured_height_cm?: number | null;
  receiving_note?: string | null;
}

export interface ReceivingLabelTemplateSettings {
  fields: string[];
  show_field_labels: boolean;
  /** Present on the settings endpoint; optional elsewhere. */
  available_fields?: string[];
}

export interface ReceivingCodeRules {
  prefix: string;
  separator: string;
  include_order_number: boolean;
  sequence_padding: number;
  uppercase: boolean;
  sample_code: string;
}

export interface InboundPackageSummary {
  id: string;
  order_line_id: string;
  line_number?: number | null;
  sku_id?: string | null;
  sku_code?: string | null;
  sku_name?: string | null;
  package_number: number;
  label_sequence?: number | null;
  package_type: string;
  package_origin?: string | null;
  status: string;
  expected_qty: number;
  received_qty: number;
  damaged_qty: number;
  staging_location_id?: string | null;
  lot_number?: string | null;
  expiry_date?: string | null;
  external_tracking_number?: string | null;
  external_carton_mark?: string | null;
  external_customer_barcode?: string | null;
  package_count?: number | null;
  pallet_count?: number | null;
  rent_free_days?: number | null;
  measured_weight_kg?: number | null;
  measured_length_cm?: number | null;
  measured_width_cm?: number | null;
  measured_height_cm?: number | null;
  receiving_note?: string | null;
  confirmed_at?: string | null;
}

export interface InboundDetailLineSummary {
  line_id: string;
  line_number?: number | null;
  sku_id?: string | null;
  sku_code?: string | null;
  sku_name?: string | null;
  sku_weight_kg?: number | null;
  sku_length_cm?: number | null;
  sku_width_cm?: number | null;
  sku_height_cm?: number | null;
  requires_lot?: boolean;
  requires_expiry?: boolean;
  quantity_expected: number;
  quantity_received: number;
  lot_number?: string | null;
  expiry_date?: string | null;
  measured_weight_kg?: number | null;
  measured_length_cm?: number | null;
  measured_width_cm?: number | null;
  measured_height_cm?: number | null;
  receiving_note?: string | null;
  packages?: Partial<InboundPackageSummary>[];
}

export interface InboundDetailSummary {
  lines: InboundDetailLineSummary[];
  /** Aggregate package counters shown on the inbound order detail page. */
  package_summary?: Record<string, any>;
  /** Lifecycle timeline events shown on the inbound order detail page. */
  timeline?: any[];
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/** Orders currently receivable at the dock ("expected" + "receiving"), deduped. */
export async function fetchReceivableInboundOrders(): Promise<InboundReceivableOrder[]> {
  const [expected, receiving] = await Promise.all([
    api.get("/orders/inbound?status=expected").then((r) => r.data),
    api.get("/orders/inbound?status=receiving").then((r) => r.data),
  ]);

  const merged = [...expected, ...receiving] as InboundReceivableOrder[];
  const seen = new Set<string>();

  return merged.filter((order) => {
    if (seen.has(order.id)) {
      return false;
    }
    seen.add(order.id);
    return true;
  });
}

export function fetchInboundOrderDetail(orderId: string): Promise<InboundDetailSummary> {
  return api.get(`/order-details/inbound/${orderId}`).then((r) => r.data as InboundDetailSummary);
}

export function fetchReceivingLabels(orderId: string): Promise<ReceivingLabelSummary[]> {
  return api.get(`/receiving/inbound/${orderId}/labels`).then((r) => r.data);
}

export function fetchReceivingPackages(orderId: string): Promise<InboundPackageSummary[]> {
  return api.get(`/receiving/inbound/${orderId}/packages`).then((r) => r.data);
}

export function fetchObservedReceivingCodes(
  orderId: string,
  params: { package_id: string } | { label_code: string | undefined },
): Promise<ObservedReceivingCode[]> {
  return api
    .get(`/receiving/inbound/${orderId}/captured-codes`, { params })
    .then((r) => r.data as ObservedReceivingCode[]);
}

/** Staging/dock/quality locations for the receiving flow. */
export function fetchReceivingStagingLocations(warehouseId: string): Promise<any[]> {
  return api
    .get(`/warehouses/${warehouseId}/locations?location_type=staging,dock,quality`)
    .then((r) => r.data);
}

export function fetchReceivingLabelTemplate(): Promise<ReceivingLabelTemplateSettings> {
  return api
    .get("/tenants/current/receiving-label-template")
    .then((r) => r.data as ReceivingLabelTemplateSettings);
}

export function updateReceivingLabelTemplate(payload: {
  fields: string[];
  show_field_labels: boolean;
}): Promise<ReceivingLabelTemplateSettings> {
  return api
    .patch("/tenants/current/receiving-label-template", payload)
    .then((r) => r.data as ReceivingLabelTemplateSettings);
}

export function fetchReceivingCodeRules(): Promise<ReceivingCodeRules> {
  return api.get("/tenants/current/receiving-code-rules").then((r) => r.data as ReceivingCodeRules);
}

export function updateReceivingCodeRules(payload: {
  prefix: string;
  separator: string;
  include_order_number: boolean;
  sequence_padding: number;
  uppercase: boolean;
}): Promise<ReceivingCodeRules> {
  return api
    .patch("/tenants/current/receiving-code-rules", payload)
    .then((r) => r.data as ReceivingCodeRules);
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function startReceiving(orderId: string) {
  return api.post(`/receiving/inbound/${orderId}/start-receiving`);
}

export function scanReceivingLabel(orderId: string, payload: { label_code: string; source: string }) {
  return api.post(`/receiving/inbound/${orderId}/scan-label`, payload);
}

export function openReceivingPackage(orderId: string, packageId: string) {
  return api.post(`/receiving/inbound/${orderId}/packages/${packageId}/open`);
}

export function deleteCapturedReceivingCode(orderId: string, codeId: string) {
  return api.delete(`/receiving/inbound/${orderId}/captured-codes/${codeId}`);
}

export function addCapturedReceivingCode(
  orderId: string,
  payload: Record<string, unknown>,
): Promise<ObservedReceivingCode> {
  return api
    .post(`/receiving/inbound/${orderId}/captured-codes`, payload)
    .then((r) => r.data as ObservedReceivingCode);
}

export function updateCapturedReceivingCode(
  orderId: string,
  codeId: string,
  payload: Record<string, unknown>,
): Promise<ObservedReceivingCode> {
  return api
    .patch(`/receiving/inbound/${orderId}/captured-codes/${codeId}`, payload)
    .then((r) => r.data as ObservedReceivingCode);
}

export function createReceivingPackage(orderId: string, payload: Record<string, unknown>): Promise<{ id: string }> {
  return api.post(`/receiving/inbound/${orderId}/packages`, payload).then((r) => r.data as { id: string });
}

export function updateReceivingPackage(orderId: string, packageId: string, payload: Record<string, unknown>) {
  return api.patch(`/receiving/inbound/${orderId}/packages/${packageId}`, payload);
}

export function correctReceivingPackage(orderId: string, packageId: string, payload: Record<string, unknown>) {
  return api.post(`/receiving/inbound/${orderId}/packages/${packageId}/correct`, payload);
}

export function deleteReceivingPackage(orderId: string, packageId: string) {
  return api.delete(`/receiving/inbound/${orderId}/packages/${packageId}`);
}

export function markReceivingLabelsPrinted(orderId: string, payload: Record<string, unknown>) {
  return api.post(`/receiving/inbound/${orderId}/labels/mark-printed`, payload);
}
