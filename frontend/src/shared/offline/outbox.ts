import api from "../api/client";

export type OutboxMutationStatus = "pending" | "synced" | "failed";
export type OutboxMutationMethod = "POST" | "PUT" | "PATCH" | "DELETE";

export interface OutboxMutationRecord {
  id: string;
  method: OutboxMutationMethod;
  url: string;
  data?: unknown;
  params?: Record<string, unknown>;
  idempotencyKey: string;
  tenantId: string | null;
  userId: string | null;
  description: string;
  status: OutboxMutationStatus;
  attempts: number;
  createdAt: string;
  updatedAt: string;
  lastError?: string;
}

export interface OutboxSummary {
  pending: number;
  synced: number;
  failed: number;
}

const DB_NAME = "wms-offline-outbox";
const DB_VERSION = 1;
const STORE_NAME = "mutations";
const OUTBOX_CHANGED_EVENT = "wms:outbox-changed";
const OUTBOX_SYNCED_EVENT = "wms:outbox-synced";
const MAX_NETWORK_ATTEMPTS = 5;
const REPLAY_RECORD_DELAY_MS = 150;

let dbPromise: Promise<IDBDatabase> | null = null;
let replayInFlight: Promise<void> | null = null;

export class OfflineMutationQueuedError extends Error {
  entryId: string;

  constructor(entryId: string) {
    super("Mutation saved to offline outbox.");
    this.name = "OfflineMutationQueuedError";
    this.entryId = entryId;
  }
}

export function isOfflineMutationQueuedError(error: unknown): error is OfflineMutationQueuedError {
  return error instanceof OfflineMutationQueuedError || (error as any)?.name === "OfflineMutationQueuedError";
}

export function isNetworkError(error: unknown) {
  const maybeError = error as any;
  if (maybeError?.response) return false;
  if (typeof navigator !== "undefined" && navigator.onLine === false) return true;
  return Boolean(maybeError?.request || maybeError?.code === "ERR_NETWORK" || maybeError?.message === "Network Error");
}

export function createIdempotencyKey(scope: string) {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${scope}:${random}`;
}

function decodeTokenSubject(token: string | null) {
  if (!token) return null;

  try {
    const payload = token.split(".")[1];
    if (!payload) return null;

    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const parsed = JSON.parse(atob(padded));
    return typeof parsed.sub === "string" && parsed.sub ? parsed.sub : null;
  } catch {
    return null;
  }
}

function currentOutboxAuthContext() {
  if (typeof localStorage === "undefined") {
    return { tenantId: null, userId: null };
  }

  return {
    tenantId: localStorage.getItem("wms_tenant_id"),
    userId: decodeTokenSubject(localStorage.getItem("wms_token")),
  };
}

function recordMatchesCurrentAuth(record: Pick<OutboxMutationRecord, "tenantId" | "userId">) {
  const current = currentOutboxAuthContext();
  return record.tenantId === current.tenantId && record.userId === current.userId;
}

export function notifyOutboxChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(OUTBOX_CHANGED_EVENT));
}

function notifyOutboxSynced(record: OutboxMutationRecord) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(OUTBOX_SYNCED_EVENT, { detail: record }));
}

export function subscribeOutboxChanges(callback: () => void) {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(OUTBOX_CHANGED_EVENT, callback);
  return () => window.removeEventListener(OUTBOX_CHANGED_EVENT, callback);
}

export function subscribeOutboxSynced(callback: (record: OutboxMutationRecord) => void) {
  if (typeof window === "undefined") return () => undefined;
  const handler = (event: Event) => callback((event as CustomEvent<OutboxMutationRecord>).detail);
  window.addEventListener(OUTBOX_SYNCED_EVENT, handler);
  return () => window.removeEventListener(OUTBOX_SYNCED_EVENT, handler);
}

function openOutboxDb() {
  if (typeof indexedDB === "undefined") {
    return Promise.reject(new Error("IndexedDB is not available in this browser."));
  }
  if (dbPromise) return dbPromise;

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error || new Error("Could not open offline outbox."));
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = () => {
      const db = request.result;
      const store = db.objectStoreNames.contains(STORE_NAME)
        ? request.transaction?.objectStore(STORE_NAME)
        : db.createObjectStore(STORE_NAME, { keyPath: "id" });
      if (!store) return;
      if (!store.indexNames.contains("status")) store.createIndex("status", "status", { unique: false });
      if (!store.indexNames.contains("createdAt")) store.createIndex("createdAt", "createdAt", { unique: false });
    };
  });

  return dbPromise;
}

function withStore<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T> | void) {
  return openOutboxDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, mode);
        const store = transaction.objectStore(STORE_NAME);
        let request: IDBRequest<T> | void;
        transaction.onerror = () => reject(transaction.error || new Error("Offline outbox transaction failed."));
        transaction.oncomplete = () => resolve(request ? request.result : (undefined as T));
        request = action(store);
        if (request) {
          request.onerror = () => reject(request.error || new Error("Offline outbox request failed."));
        }
      }),
  );
}

type NewOutboxMutationRecord = Omit<
  OutboxMutationRecord,
  "id" | "tenantId" | "userId" | "status" | "attempts" | "createdAt" | "updatedAt"
>;

export async function enqueueOutboxMutation(entry: NewOutboxMutationRecord) {
  const now = new Date().toISOString();
  const authContext = currentOutboxAuthContext();
  const existing = (await getOutboxRecords(["pending", "failed"], { currentAuthOnly: false })).find(
    (record) =>
      record.idempotencyKey === entry.idempotencyKey &&
      record.tenantId === authContext.tenantId &&
      record.userId === authContext.userId,
  );
  if (existing) return existing;

  const record: OutboxMutationRecord = {
    ...entry,
    tenantId: authContext.tenantId,
    userId: authContext.userId,
    id: createIdempotencyKey("outbox"),
    status: "pending",
    attempts: 0,
    createdAt: now,
    updatedAt: now,
  };
  await withStore("readwrite", (store) => store.add(record));
  notifyOutboxChanged();
  return record;
}

export async function getOutboxRecords(
  statuses: OutboxMutationStatus[] = ["pending"],
  options: { currentAuthOnly?: boolean } = {},
) {
  const currentAuthOnly = options.currentAuthOnly ?? true;
  const records = await withStore<OutboxMutationRecord[]>("readonly", (store) => store.getAll());
  return records
    .filter((record) => statuses.includes(record.status))
    .filter((record) => !currentAuthOnly || recordMatchesCurrentAuth(record))
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function getOutboxSummary(): Promise<OutboxSummary> {
  const records = await withStore<OutboxMutationRecord[]>("readonly", (store) => store.getAll()).catch(() => []);
  return records.filter(recordMatchesCurrentAuth).reduce<OutboxSummary>(
    (summary, record) => ({
      ...summary,
      [record.status]: summary[record.status] + 1,
    }),
    { pending: 0, synced: 0, failed: 0 },
  );
}

async function updateOutboxRecord(id: string, patch: Partial<OutboxMutationRecord>) {
  const records = await getOutboxRecords(["pending", "synced", "failed"]);
  const record = records.find((candidate) => candidate.id === id);
  if (!record) return;
  await withStore("readwrite", (store) =>
    store.put({
      ...record,
      ...patch,
      updatedAt: new Date().toISOString(),
    }),
  );
  notifyOutboxChanged();
}

function errorText(error: unknown) {
  const maybeError = error as any;
  const detail = maybeError?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (typeof maybeError?.message === "string") return maybeError.message;
  return "Replay failed.";
}

function businessFailureMessage(data: any) {
  if (!data || typeof data !== "object") return "";
  if (data.success === false) {
    return data.error || data.message || "The server rejected this queued action.";
  }
  if (data.verified === false) {
    if (Array.isArray(data.errors) && data.errors.length > 0) return data.errors.join(" · ");
    return data.error || data.message || "The server could not verify this queued action.";
  }
  return "";
}

function sleep(ms: number) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

async function replayRecord(record: OutboxMutationRecord) {
  if (!recordMatchesCurrentAuth(record)) return;

  try {
    const response = await api.request({
      method: record.method,
      url: record.url,
      data: record.data,
      params: record.params,
      headers: { "X-Idempotency-Key": record.idempotencyKey },
    });
    const failure = businessFailureMessage(response.data);
    if (failure) {
      await updateOutboxRecord(record.id, { status: "failed", lastError: failure });
      return;
    }
    await updateOutboxRecord(record.id, { status: "synced", lastError: undefined });
    notifyOutboxSynced(record);
  } catch (error) {
    const nextAttempts = record.attempts + 1;
    if (isNetworkError(error) && nextAttempts < MAX_NETWORK_ATTEMPTS) {
      await updateOutboxRecord(record.id, {
        attempts: nextAttempts,
        lastError: errorText(error),
      });
      return;
    }
    await updateOutboxRecord(record.id, {
      attempts: nextAttempts,
      status: "failed",
      lastError: errorText(error),
    });
  }
}

export function replayOutbox(includeFailed = false) {
  if (replayInFlight) return replayInFlight;
  if (typeof navigator !== "undefined" && navigator.onLine === false) return Promise.resolve();

  replayInFlight = (async () => {
    const records = await getOutboxRecords(includeFailed ? ["pending", "failed"] : ["pending"]);
    for (const [index, record] of records.entries()) {
      await replayRecord(record);
      if (index < records.length - 1) {
        await sleep(REPLAY_RECORD_DELAY_MS);
      }
    }
  })()
    .catch(() => undefined)
    .finally(() => {
      replayInFlight = null;
      notifyOutboxChanged();
    });

  return replayInFlight;
}

if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    void replayOutbox();
    notifyOutboxChanged();
  });
  window.addEventListener("offline", notifyOutboxChanged);
  window.setTimeout(() => void replayOutbox(), 1000);
}
