import api from "./client";

export const ORDER_LIST_BATCH_SIZE = 100;

export type OrderListPage<T = any> = {
  items: T[];
  offset: number;
  limit: number;
  returnedCount: number;
  hasMore: boolean;
  nextOffset?: number;
};

type OrderListParams = {
  offset?: number;
  limit?: number;
  status?: string;
  statuses?: string[] | string;
  warehouseId?: string;
  lifecycle?: string;
  operation?: string;
  recentHours?: number;
  sortBy?: string;
  sortDirection?: string;
};

type InboundOrderListParams = OrderListParams & {
  includeArchived?: boolean;
};

function headerValue(headers: Record<string, any>, key: string) {
  if (typeof headers?.get === "function") {
    return headers.get(key) ?? headers.get(key.toLowerCase());
  }
  return headers[key] ?? headers[key.toLowerCase()];
}

function numberHeader(headers: Record<string, any>, key: string, fallback: number) {
  const value = headerValue(headers, key);
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function booleanHeader(headers: Record<string, any>, key: string) {
  const value = String(headerValue(headers, key) ?? "").toLowerCase();
  return value === "true";
}

function buildPage<T>(items: T[], headers: Record<string, any>, fallbackOffset: number, fallbackLimit: number): OrderListPage<T> {
  const offset = numberHeader(headers, "x-offset", fallbackOffset);
  const limit = numberHeader(headers, "x-limit", fallbackLimit);
  const returnedCount = numberHeader(headers, "x-returned-count", items.length);
  const hasMore = booleanHeader(headers, "x-has-more");
  return {
    items,
    offset,
    limit,
    returnedCount,
    hasMore,
    nextOffset: hasMore ? offset + limit : undefined,
  };
}

export async function fetchInboundOrderListPage({
  includeArchived = false,
  offset = 0,
  limit = ORDER_LIST_BATCH_SIZE,
  status,
  statuses,
  warehouseId,
  lifecycle,
  operation,
  recentHours,
  sortBy,
  sortDirection,
}: InboundOrderListParams = {}): Promise<OrderListPage<any>> {
  const joinedStatuses = Array.isArray(statuses) ? statuses.join(",") : statuses;
  const response = await api.get("/orders/inbound", {
    params: {
      include_archived: includeArchived,
      offset,
      limit,
      status,
      statuses: joinedStatuses,
      warehouse_id: warehouseId,
      lifecycle,
      operation,
      recent_hours: recentHours,
      sort_by: sortBy,
      sort_direction: sortDirection,
    },
  });
  return buildPage<any>(response.data || [], response.headers, offset, limit);
}

export async function fetchOutboundOrderListPage({
  offset = 0,
  limit = ORDER_LIST_BATCH_SIZE,
  status,
  statuses,
  warehouseId,
  sortBy,
  sortDirection,
}: OrderListParams = {}): Promise<OrderListPage<any>> {
  const joinedStatuses = Array.isArray(statuses) ? statuses.join(",") : statuses;
  const response = await api.get("/orders/outbound", {
    params: {
      offset,
      limit,
      status,
      statuses: joinedStatuses,
      warehouse_id: warehouseId,
      sort_by: sortBy,
      sort_direction: sortDirection,
    },
  });
  return buildPage<any>(response.data || [], response.headers, offset, limit);
}
