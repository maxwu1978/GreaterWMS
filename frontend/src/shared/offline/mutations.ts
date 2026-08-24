import type { AxiosResponse } from "axios";
import api from "../api/client";
import {
  createIdempotencyKey,
  enqueueOutboxMutation,
  isNetworkError,
  OfflineMutationQueuedError,
  replayOutbox,
  type OutboxMutationMethod,
} from "./outbox";

interface OfflineMutationRequest {
  method?: OutboxMutationMethod;
  url: string;
  data?: unknown;
  params?: Record<string, unknown>;
  scope: string;
  description: string;
}

const RECENT_ACTION_KEY_TTL_MS = 15 * 60 * 1000;
const recentActionKeys = new Map<string, { key: string; expiresAt: number }>();

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((entry) => stableStringify(entry)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify((value as Record<string, unknown>)[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

function getIdempotencyKeyForAction(request: OfflineMutationRequest & { method: OutboxMutationMethod }) {
  const now = Date.now();
  for (const [fingerprint, entry] of recentActionKeys.entries()) {
    if (entry.expiresAt <= now) recentActionKeys.delete(fingerprint);
  }

  const fingerprint = stableStringify({
    method: request.method,
    url: request.url,
    params: request.params,
    data: request.data,
    scope: request.scope,
  });
  const existing = recentActionKeys.get(fingerprint);
  if (existing) return existing.key;

  const key = createIdempotencyKey(request.scope);
  recentActionKeys.set(fingerprint, {
    key,
    expiresAt: now + RECENT_ACTION_KEY_TTL_MS,
  });
  return key;
}

export async function requestWithOutbox<T = unknown>({
  method = "POST",
  url,
  data,
  params,
  scope,
  description,
}: OfflineMutationRequest): Promise<AxiosResponse<T>> {
  const idempotencyKey = getIdempotencyKeyForAction({ method, url, data, params, scope, description });

  const enqueue = async () => {
    const record = await enqueueOutboxMutation({
      method,
      url,
      data,
      params,
      idempotencyKey,
      description,
    });
    throw new OfflineMutationQueuedError(record.id);
  };

  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return enqueue();
  }

  try {
    const response = await api.request<T>({
      method,
      url,
      data,
      params,
      headers: { "X-Idempotency-Key": idempotencyKey },
    });
    void replayOutbox();
    return response;
  } catch (error) {
    if (isNetworkError(error)) {
      return enqueue();
    }
    throw error;
  }
}
