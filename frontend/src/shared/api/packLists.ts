import api from "./client";

export type PackListImportPayload = {
  source_text: string;
  file_name: string;
  mapping?: Record<string, string> | null;
  order_number?: string | null;
  client_code?: string | null;
  warehouse_code?: string | null;
  source_type?: string;
  note?: string | null;
  create_inbound_if_missing?: boolean;
};

export type PackListImportPreview = {
  ok: boolean;
  summary?: {
    rows?: number;
    valid_rows?: number;
    error?: number;
    warning?: number;
    packages?: number;
    quantity?: number;
    serial_numbers?: number;
  };
  document?: {
    order_number?: string | null;
    client_id?: string | null;
    warehouse_id?: string | null;
    container_tracking?: string | null;
    eta?: string | null;
    arrival_status?: string | null;
  };
  rows?: Array<Record<string, unknown>>;
  warnings?: Array<Record<string, unknown>>;
  errors?: Array<Record<string, unknown>>;
  confirmation_payload?: {
    confirmation_token?: string;
    evidence_id?: string;
  };
  evidence_id?: string;
  next_action?: string;
  [key: string]: unknown;
};

export function previewPackList(payload: PackListImportPayload): Promise<PackListImportPreview> {
  return api.post("/agent/packlists/preview", payload).then((response) => response.data);
}

export function confirmPackList(
  payload: PackListImportPayload & { confirmation_token: string },
  idempotencyKey: string,
): Promise<Record<string, unknown>> {
  return api
    .post("/agent/packlists/agent", payload, { headers: { "X-Idempotency-Key": idempotencyKey } })
    .then((response) => response.data);
}
