type TranslateFn = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>
) => string;

export function shortId(value?: string | null) {
  if (!value) return "—";
  return value.length > 12 ? value.slice(0, 12) : value;
}

export function getInboundOrderTag(orderNumber: string | undefined, t: TranslateFn) {
  if (!orderNumber) return "";
  if (orderNumber.startsWith("INB-PUT-")) {
    return t("putaway.demoInboundTag", "Demo inbound order");
  }
  if (orderNumber.startsWith("INB-")) {
    return t("putaway.inboundOrderTag", "Inbound order");
  }
  return "";
}

export function toItems<T>(payload: any): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object" && Array.isArray(payload.items)) return payload.items as T[];
  return [];
}

export function getSuggestionReasonLabel(reason: string | undefined, t: TranslateFn) {
  if (!reason) return t("putaway.reason.emptyAvailable", "Open storage slot");
  if (reason.startsWith("zone_rule:")) {
    return t("putaway.reason.zoneRule", "Fits zone rule: {zone}", { zone: reason.split(":")[1] || "—" });
  }

  const lookup: Record<string, { key: string; fallback: string }> = {
    consolidate: { key: "putaway.reason.consolidate", fallback: "Consolidate with existing SKU" },
    consolidate_with_existing_sku: { key: "putaway.reason.consolidate", fallback: "Consolidate with existing SKU" },
    empty_available: { key: "putaway.reason.emptyAvailable", fallback: "Open storage slot" },
    heavy_item_low_level: { key: "putaway.reason.heavyLow", fallback: "Heavy item low level" },
    slow_mover_deeper_storage: { key: "putaway.reason.slowDeep", fallback: "Slow mover deeper storage" },
    fast_mover_front_of_flow: { key: "putaway.reason.fastFront", fallback: "Fast mover front of flow" },
  };

  const match = lookup[reason];
  return match ? t(match.key, match.fallback) : reason.replace(/_/g, " ");
}

export function describeLocationBarcode(barcode: string | undefined, t: TranslateFn) {
  if (!barcode) return "";
  if (barcode.startsWith("DOCK-")) {
    return t("putaway.locationDockFormat", "Dock / staging position {dock}", {
      dock: barcode.replace("DOCK-", ""),
    });
  }

  const match = /^([A-Z]+)-(\d+)-(\d+)-(\d+)-(\d+)$/i.exec(barcode);
  if (!match) return t("putaway.locationUnknownFormat", "Storage location code");

  const [, zone, aisle, rack, level, position] = match;
  return t(
    "putaway.locationFormat",
    "Zone {zone} / Aisle {aisle} / Rack {rack} / Level {level} / Position {position}",
    { zone, aisle, rack, level, position }
  );
}

export function parseStorageBarcode(barcode?: string | null) {
  if (!barcode) return null;
  const match = /^([A-Z]+)-(\d+)-(\d+)-(\d+)-(\d+)$/i.exec(barcode);
  if (!match) return null;
  const [, zone, aisle, rack, level, position] = match;
  return { zone, aisle, rack, level, position };
}

function formatApiErrorValue(value: unknown): string | null {
  if (!value) return null;
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
      .map((item) => formatApiErrorValue(item))
      .filter(Boolean)
      .join("; ");
  }
  if (typeof value === "object") {
    const detail = value as { msg?: unknown; message?: unknown; error?: unknown; detail?: unknown };
    return (
      formatApiErrorValue(detail.msg) ||
      formatApiErrorValue(detail.message) ||
      formatApiErrorValue(detail.error) ||
      formatApiErrorValue(detail.detail)
    );
  }
  return null;
}

export function getApiErrorMessage(error: unknown, fallback: string) {
  const responseData = (error as { response?: { data?: unknown } } | null)?.response?.data;
  const responseMessage = formatApiErrorValue(responseData);
  if (responseMessage) return responseMessage;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function getApiErrorCodeFromValue(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const detail = value as { code?: unknown; error_code?: unknown; detail?: unknown };
  if (typeof detail.error_code === "string") return detail.error_code;
  if (typeof detail.code === "string") return detail.code;
  return getApiErrorCodeFromValue(detail.detail);
}

export function getApiErrorCode(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const record = error as { errorCode?: unknown; response?: { data?: unknown } };
  if (typeof record.errorCode === "string") return record.errorCode;
  return getApiErrorCodeFromValue(record.response?.data);
}

export function getSuggestionStrength(rank?: number | null) {
  if (!rank) return "manual";
  if (rank === 1) return "primary";
  if (rank === 2) return "secondary";
  return "tertiary";
}

export function getExecutionModeLabel(mode: string | undefined, t: TranslateFn) {
  if (mode === "agv") return t("putaway.executionMode.agv", "AGV");
  if (mode === "hybrid") return t("putaway.executionMode.hybrid", "Hybrid");
  return t("putaway.executionMode.human", "Worker");
}

export function getExecutionReasonLabel(reason: string | undefined, t: TranslateFn) {
  if (reason === "agv_ready_from_staging") {
    return t("putaway.executionReason.agvReady", "AGV-ready from staging");
  }
  if (reason === "human_to_agv_handoff_required") {
    return t("putaway.executionReason.hybridHandoff", "Human handoff before AGV");
  }
  if (reason === "unit_exceeds_agv_payload") {
    return t("putaway.executionReason.overweight", "Too heavy for AGV");
  }
  if (reason === "no_agv_storage_available") {
    return t("putaway.executionReason.noAgvStorage", "No AGV-ready storage path");
  }
  return t("putaway.executionReason.manualDefault", "Handled through the normal worker flow");
}

export function getTaskExternalCodeSummary(task: any) {
  return [
    task.external_tracking_number ? `TRK ${task.external_tracking_number}` : null,
    task.external_carton_mark ? `CTN ${task.external_carton_mark}` : null,
    task.external_customer_barcode ? `CUS ${task.external_customer_barcode}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function getTaskSearchText(task: any) {
  return [
    task.handling_unit_code,
    task.inbound_order_number,
    task.reference_number,
    task.reference_id,
    task.sku_label,
    task.source_barcode,
    task.external_tracking_number,
    task.external_carton_mark,
    task.external_customer_barcode,
    task.execution_mode,
    task.execution_reason,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function getTaskOrderKey(task: any) {
  return String(task?.reference_id || task?.inbound_order_number || "unknown-order");
}

export function keepTaskIdsInOneOrder(
  taskIds: string[],
  taskMap: Map<string, any>,
  preferredOrderKey?: string | null
) {
  const orderKey = preferredOrderKey || getTaskOrderKey(taskMap.get(taskIds[0]));
  return taskIds.filter((taskId) => getTaskOrderKey(taskMap.get(taskId)) === orderKey);
}

export function getTaskCreatedAt(task: any) {
  const value = task?.created_at;
  const timestamp = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(timestamp) ? Number.MAX_SAFE_INTEGER : timestamp;
}

export function getTaskAgeLabel(task: any, t: TranslateFn) {
  const createdAt = getTaskCreatedAt(task);
  if (createdAt === Number.MAX_SAFE_INTEGER) return t("putaway.taskAgeUnknown", "Waiting time unknown");

  const diffMinutes = Math.max(0, Math.round((Date.now() - createdAt) / 60000));
  if (diffMinutes < 60) {
    return t("putaway.taskAgeMinutes", "{count} min waiting", { count: diffMinutes });
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return t("putaway.taskAgeHours", "{count} hr waiting", { count: diffHours });
  }

  const diffDays = Math.round(diffHours / 24);
  return t("putaway.taskAgeDays", "{count} d waiting", { count: diffDays });
}

export function getHandlingUnitStatusLabel(status: string | undefined, t: TranslateFn) {
  if (status === "stored") return t("putaway.handlingUnitStatus.stored", "Stored");
  if (status === "putaway_pending") return t("putaway.handlingUnitStatus.putawayPending", "Putaway pending");
  if (status === "staged") return t("putaway.handlingUnitStatus.staged", "Staged");
  if (status === "received") return t("putaway.handlingUnitStatus.received", "Received");
  return t("putaway.handlingUnitStatus.expected", "Expected");
}

export function getExecutionModeTone(mode: string | undefined, selected = false) {
  if (selected) {
    return "border-[#d19009]/28 bg-[#fff7e8] text-[#8a6511]";
  }
  if (mode === "agv") {
    return "border-[#8db6ff]/30 bg-[#eff5ff] text-[#4977c8]";
  }
  if (mode === "hybrid") {
    return "border-[#87c6a1]/28 bg-[#eef9f1] text-[#356b4c]";
  }
  return "border-[#13212c]/10 bg-white text-[#61717d]";
}

export function getSlotTone(strength: string, selected: boolean) {
  if (selected) {
    return {
      shell: "border-[#13212c] bg-[#13212c] text-[#f4efe8] shadow-[0_18px_40px_rgba(19,33,44,0.16)]",
      subtext: "text-[#d0dbe2]",
      meta: "text-[#d0dbe2]",
      badge: "bg-[#f7bf45]/18 text-[#f7d472] border-[#f7bf45]/28",
    };
  }

  if (strength === "primary") {
    return {
      shell: "border-[#d19009]/32 bg-[#fff7e8] text-[#13212c] shadow-[0_12px_32px_rgba(209,144,9,0.10)]",
      subtext: "text-[#61717d]",
      meta: "text-[#8a6511]",
      badge: "bg-[#f7bf45]/16 text-[#8a6511] border-[#f7bf45]/28",
    };
  }

  if (strength === "secondary") {
    return {
      shell: "border-[#7da9ff]/28 bg-[#eff5ff] text-[#13212c] shadow-[0_12px_32px_rgba(125,169,255,0.10)]",
      subtext: "text-[#61717d]",
      meta: "text-[#4977c8]",
      badge: "bg-[#8db6ff]/16 text-[#4977c8] border-[#8db6ff]/30",
    };
  }

  if (strength === "tertiary") {
    return {
      shell: "border-[#87c6a1]/30 bg-[#eef9f1] text-[#13212c] shadow-[0_12px_32px_rgba(135,198,161,0.10)]",
      subtext: "text-[#61717d]",
      meta: "text-[#356b4c]",
      badge: "bg-[#87c6a1]/16 text-[#356b4c] border-[#87c6a1]/28",
    };
  }

  return {
    shell: "border-[#13212c]/8 bg-white text-[#13212c]",
    subtext: "text-[#61717d]",
    meta: "text-[#a0acb6]",
    badge: "bg-[#f4efe8] text-[#61717d] border-[#13212c]/10",
  };
}

export function occupancyTone(units: number) {
  if (units >= 200) return "bg-[#d19009]";
  if (units >= 80) return "bg-[#4977c8]";
  if (units > 0) return "bg-[#356b4c]";
  return "bg-[#d7dee5]";
}
