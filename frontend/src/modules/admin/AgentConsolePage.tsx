import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Boxes,
  ClipboardList,
  PackageSearch,
  Receipt,
  Sparkles,
  Warehouse,
} from "lucide-react";
import { fetchAgentSettings, runAgentTool } from "../../shared/api/agent";
import { queryKeys } from "../../shared/api/queryKeys";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useAuthStore } from "../../shared/hooks/useAuth";
import { useI18n } from "../../shared/i18n";

type ToolItem = { key: string; risk: string };

type AgentSettings = {
  enabled: boolean;
  allowed_tools: string[];
  tool_catalog: ToolItem[];
  requires_human_confirmation_for_writes?: boolean;
  provider_label?: string | null;
  model_name?: string | null;
  validation_status?: string | null;
  validation_message?: string | null;
};

type ToolRunResponse = {
  tool_name: string;
  risk: string;
  scope: { tenant_id: string | null; role: string };
  result: any;
  audit_logged_at: string;
};

type ImportPreview = {
  headers: string[];
  required_fields: string[];
  optional_fields: string[];
  suggested_mapping: Record<string, string>;
  missing_required: string[];
  sample_rows: Record<string, string>[];
  mapped_preview: Record<string, string>[];
  total_rows: number;
};

type AnswerSection = {
  title: string;
  body: string;
};

type RenderedItemCard = {
  title: string;
  subtitle?: string;
  chips?: string[];
  note?: string;
  href?: string;
  ctaLabel?: string;
};

type BlueprintAreaSummary = {
  code?: string;
  name?: string;
  dimensions?: Record<string, unknown>;
  location_count?: number;
  abc_class?: string;
  levels?: number;
  racks?: number;
};

type BlueprintDockDoor = {
  code?: string;
  door_number?: string | number;
  wcs_mapping?: BlueprintWcsMappingDraft;
};

type BlueprintWcsMappingDraft = {
  location_barcode?: string | null;
  point_code?: string | null;
  point_type?: string | null;
  point_role?: string | null;
  buffer_code?: string | null;
  aisle_group?: string | null;
  virtual?: boolean;
};

type WarehouseBlueprintPreview = {
  ok?: boolean;
  target?: { id?: string | null; code?: string | null; name?: string | null; will_create?: boolean };
  summary?: {
    zone_count?: number;
    location_count?: number;
    dock_door_count?: number;
    wcs_point_mapping_draft_count?: number;
  };
  abc_floor_areas?: BlueprintAreaSummary[];
  rack_areas?: BlueprintAreaSummary[];
  dock_doors?: BlueprintDockDoor[];
  wcs_point_mapping_draft?: BlueprintWcsMappingDraft[];
  blocking_errors?: unknown[];
  next_action?: string;
};

type ToolGroup = {
  key: string;
  title: string;
  body: string;
  tools: ToolItem[];
};

type GuidedStep = {
  key: string;
  title: string;
  body: string;
  active: boolean;
  complete: boolean;
};

type PromptShortcut = {
  key: string;
  labelKey: string;
  labelFallback: string;
  helperKey: string;
  helperFallback: string;
  tool_name: string;
  args?: Record<string, unknown>;
  apply?: () => void;
};

type ImportKind = "inbound" | "outbound" | "inventory";
type RoutedAction = { tool_name: string; args: Record<string, unknown> } | null;
type MobileToolPolicy = "phone-primary" | "desktop-preferred";
type ToolGovernance = {
  risk: "low" | "medium" | "high";
  permission: string;
  confirmation: "none" | "standard" | "strong";
  mobilePolicy: MobileToolPolicy;
};

const TOOL_GOVERNANCE: Record<string, ToolGovernance> = {
  "setup.progress": { risk: "low", permission: "users.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "orders.inbound.list": { risk: "low", permission: "inbound_orders.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "orders.outbound.list": { risk: "low", permission: "outbound_orders.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "inventory.search": { risk: "low", permission: "master_data.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "inventory.explain": { risk: "low", permission: "master_data.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "clients.list": { risk: "low", permission: "master_data.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "clients.get": { risk: "low", permission: "master_data.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "skus.list": { risk: "low", permission: "master_data.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "warehouses.list": { risk: "low", permission: "master_data.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "billing.rate_cards.list": { risk: "low", permission: "billing.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "receiving.inbound.preview_import": { risk: "low", permission: "inbound_orders.import", confirmation: "none", mobilePolicy: "phone-primary" },
  "orders.outbound.preview_import": { risk: "low", permission: "outbound_orders.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "migration.inventory.preview": { risk: "low", permission: "master_data.manage", confirmation: "none", mobilePolicy: "phone-primary" },
  "warehouse.blueprint.preview": { risk: "medium", permission: "master_data.manage", confirmation: "standard", mobilePolicy: "desktop-preferred" },
  "receiving.inbound.import_with_mapping": { risk: "medium", permission: "inbound_orders.import", confirmation: "standard", mobilePolicy: "desktop-preferred" },
  "orders.outbound.import_with_mapping": { risk: "medium", permission: "outbound_orders.manage", confirmation: "standard", mobilePolicy: "desktop-preferred" },
  "migration.inventory.import": { risk: "high", permission: "master_data.manage", confirmation: "strong", mobilePolicy: "desktop-preferred" },
  "clients.create": { risk: "medium", permission: "master_data.manage", confirmation: "standard", mobilePolicy: "desktop-preferred" },
  "skus.create": { risk: "medium", permission: "master_data.manage", confirmation: "standard", mobilePolicy: "desktop-preferred" },
  "receiving.inbound.create": { risk: "medium", permission: "inbound_orders.manage", confirmation: "standard", mobilePolicy: "desktop-preferred" },
  "users.create": { risk: "high", permission: "users.manage", confirmation: "strong", mobilePolicy: "desktop-preferred" },
  "users.update_permissions": { risk: "high", permission: "users.manage", confirmation: "strong", mobilePolicy: "desktop-preferred" },
};

const STARTER_ACTIONS = [
  {
    tool_name: "setup.progress",
    icon: Sparkles,
    accent: "text-[#ffb84d]",
    args: {},
    titleKey: "agentConsole.actionSetupTitle",
    titleFallback: "What setup work is still missing?",
    bodyKey: "agentConsole.actionSetupBody",
    bodyFallback: "Show the checklist still blocking live warehouse execution.",
  },
  {
    tool_name: "orders.inbound.list",
    icon: ClipboardList,
    accent: "text-[#8d9bff]",
    args: { status: "expected", limit: 8 },
    titleKey: "agentConsole.actionInboundTitle",
    titleFallback: "Show expected inbound orders",
    bodyKey: "agentConsole.actionInboundBody",
    bodyFallback: "List the latest inbound orders still sitting in expected status.",
  },
  {
    tool_name: "inventory.search",
    icon: PackageSearch,
    accent: "text-[#55d6a0]",
    args: { query: "", limit: 8 },
    titleKey: "agentConsole.actionInventoryTitle",
    titleFallback: "Search inventory by SKU or client",
    bodyKey: "agentConsole.actionInventoryBody",
    bodyFallback: "Use the search box to inspect what is on hand before you ask the model to act.",
  },
  {
    tool_name: "billing.rate_cards.list",
    icon: Receipt,
    accent: "text-[#ff8f71]",
    args: { limit: 8 },
    titleKey: "agentConsole.actionBillingTitle",
    titleFallback: "Review active rate cards",
    bodyKey: "agentConsole.actionBillingBody",
    bodyFallback: "Verify which client billing rules are live before turning on billing tools.",
  },
  {
    tool_name: "warehouses.list",
    icon: Warehouse,
    accent: "text-[#79b8ff]",
    args: { limit: 8 },
    titleKey: "agentConsole.actionWarehouseTitle",
    titleFallback: "List warehouse contexts",
    bodyKey: "agentConsole.actionWarehouseBody",
    bodyFallback: "Confirm the warehouses the agent should reference when planning work.",
  },
  {
    tool_name: "skus.list",
    icon: Boxes,
    accent: "text-[#d28cff]",
    args: { limit: 8 },
    titleKey: "agentConsole.actionSkuTitle",
    titleFallback: "Inspect the SKU master list",
    bodyKey: "agentConsole.actionSkuBody",
    bodyFallback: "Check whether master data is complete enough for AI-assisted intake and planning.",
  },
];

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function sanitizeModelAnswer(answer: string) {
  return answer
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/^\s*#{1,6}\s*/gm, (match) => match)
    .trim();
}

function splitModelAnswer(answer: string, t: (key: string, fallback?: string, vars?: Record<string, string>) => string) {
  const cleaned = sanitizeModelAnswer(answer);
  if (!cleaned) return [] as AnswerSection[];

  const sections = cleaned
    .split(/\n(?=##\s+)/)
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .map((chunk) => {
      const headingMatch = chunk.match(/^##\s+(.+?)\n+([\s\S]*)$/);
      if (headingMatch) {
        return {
          title: headingMatch[1].trim(),
          body: headingMatch[2].trim(),
        };
      }
      return {
        title: t("agentConsole.modelAnswerFallbackHeading", "Takeaway"),
        body: chunk.replace(/^##\s+/gm, "").trim(),
      };
    })
    .filter((section) => section.body);

  return sections.length
    ? sections
    : [
        {
          title: t("agentConsole.modelAnswerFallbackHeading", "Takeaway"),
          body: cleaned,
        },
      ];
}

function boolLabel(
  value: boolean | null | undefined,
  t: (key: string, fallback?: string, vars?: Record<string, string>) => string,
  trueKey: string,
  trueFallback: string,
  falseKey: string,
  falseFallback: string,
) {
  return value ? t(trueKey, trueFallback) : t(falseKey, falseFallback);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function extractWarehouseBlueprintPreview(payload: unknown): WarehouseBlueprintPreview | null {
  if (!isRecord(payload)) return null;
  const hasBlueprintDraft =
    Array.isArray(payload.abc_floor_areas) ||
    Array.isArray(payload.rack_areas) ||
    Array.isArray(payload.dock_doors) ||
    Array.isArray(payload.wcs_point_mapping_draft);
  if (hasBlueprintDraft) return payload as WarehouseBlueprintPreview;

  for (const key of ["preview", "blueprint_preview", "warehouse_blueprint", "result"]) {
    const nested = extractWarehouseBlueprintPreview(payload[key]);
    if (nested) return nested;
  }
  return null;
}

function countByField<T extends Record<string, unknown>>(items: T[], field: keyof T) {
  return items.reduce<Record<string, number>>((counts, item) => {
    const key = String(item[field] || "unknown");
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
}

function compactCountMap(counts: Record<string, number>, maxItems = 4) {
  return Object.entries(counts)
    .sort(([left], [right]) => left.localeCompare(right))
    .slice(0, maxItems)
    .map(([key, count]) => `${key}: ${count}`)
    .join(" · ");
}

function dimensionSummary(dimensions?: Record<string, unknown>) {
  if (!dimensions) return "";
  const width = dimensions.width_ft ?? dimensions.width;
  const depth = dimensions.depth_ft ?? dimensions.depth;
  const height = dimensions.height_ft ?? dimensions.height;
  const pieces = [
    width != null && depth != null ? `${width} x ${depth} ft` : "",
    height != null ? `h ${height} ft` : "",
  ].filter(Boolean);
  return pieces.join(" · ");
}

function formatToolCards(
  result: ToolRunResponse | null,
  t: (key: string, fallback?: string, vars?: Record<string, string>) => string,
) {
  if (!result) return [] as RenderedItemCard[];
  const payload = result.result || {};

  if (result.tool_name === "setup.progress" && Array.isArray(payload.steps)) {
    const setupStepMeta: Record<string, { title: string; description: string; href: string }> = {
      warehouse: {
        title: t("agentConsole.setupWarehouseTitle", "Set up the warehouse"),
        description: t("agentConsole.setupWarehouseBody", "Confirm the warehouse name, address, and timezone."),
        href: "/warehouses",
      },
      locations: {
        title: t("agentConsole.setupLocationsTitle", "Create locations"),
        description: t("agentConsole.setupLocationsBody", "Lay out zones, racks, and the location skeleton."),
        href: "/warehouse-planner",
      },
      client: {
        title: t("agentConsole.setupClientTitle", "Create the first client"),
        description: t("agentConsole.setupClientBody", "Complete client master data and portal settings."),
        href: "/clients",
      },
      skus: {
        title: t("agentConsole.setupSkusTitle", "Create the SKU master list"),
        description: t("agentConsole.setupSkusBody", "Add product master data so receiving and inventory can go live."),
        href: "/skus",
      },
      billing: {
        title: t("agentConsole.setupBillingTitle", "Set up billing rules"),
        description: t("agentConsole.setupBillingBody", "Confirm rate cards, invoice details, and tax settings."),
        href: "/clients",
      },
      team: {
        title: t("agentConsole.setupTeamTitle", "Invite the team"),
        description: t("agentConsole.setupTeamBody", "Create users and assign the right permissions."),
        href: "/users",
      },
    };
    return payload.steps.map((step: any) => ({
      title: `${step.step}. ${setupStepMeta[step.name]?.title || step.title || step.name || t("agentConsole.unknownItem", "Untitled item")}`,
      subtitle: setupStepMeta[step.name]?.description || step.description || "",
      chips: [
        step.done
          ? t("agentConsole.stepDone", "Done")
          : t("agentConsole.stepPending", "Pending"),
      ],
      href: setupStepMeta[step.name]?.href || "/setup",
      ctaLabel: t("agentConsole.openSetupStep", "Open this step"),
    }));
  }

  if (Array.isArray(payload.items)) {
    if (result.tool_name === "orders.inbound.list") {
      return payload.items.map((item: any) => ({
        title: item.order_number || item.reference_number || t("agentConsole.unknownInbound", "Untitled inbound order"),
        subtitle: item.client_name || item.reference_number || "",
        chips: [
          item.status ? t("agentConsole.statusChip", "{value}", { value: item.status }) : "",
          item.reference_number ? t("agentConsole.referenceChip", "Reference: {value}", { value: item.reference_number }) : "",
        ].filter(Boolean),
        href: "/receiving",
        ctaLabel: t("agentConsole.openReceiving", "Open receiving"),
      }));
    }

    if (result.tool_name === "inventory.search") {
      return payload.items.map((item: any) => ({
        title: `${item.sku_code || ""} ${item.sku_name ? `· ${item.sku_name}` : ""}`.trim(),
        subtitle: item.client_name || "",
        chips: [
          t("agentConsole.onHandChip", "On hand {count}", { count: String(item.quantity_on_hand ?? 0) }),
          t("agentConsole.availableChip", "Available {count}", { count: String(item.quantity_available ?? 0) }),
          (item.quantity_allocated ?? 0) > 0
            ? t("agentConsole.allocatedChip", "Allocated {count}", { count: String(item.quantity_allocated ?? 0) })
            : "",
        ].filter(Boolean),
        href: "/inventory",
        ctaLabel: t("agentConsole.openInventory", "Open inventory"),
      }));
    }

    if (result.tool_name === "warehouses.list") {
      return payload.items.map((item: any) => ({
        title: item.name || t("agentConsole.unknownWarehouse", "Untitled warehouse"),
        subtitle: item.code || "",
        chips: [
          item.timezone ? t("agentConsole.timezoneChip", "Timezone {value}", { value: item.timezone }) : "",
          boolLabel(
            item.is_active,
            t,
            "agentConsole.activeChip",
            "Active",
            "agentConsole.inactiveChip",
            "Inactive",
          ),
        ].filter(Boolean),
        href: "/warehouses",
        ctaLabel: t("agentConsole.openWarehouses", "Open warehouses"),
      }));
    }

    if (result.tool_name === "skus.list") {
      return payload.items.map((item: any) => ({
        title: `${item.sku_code || ""} ${item.name ? `· ${item.name}` : ""}`.trim(),
        subtitle: item.client_name || "",
        chips: [
          item.weight_kg != null ? t("agentConsole.weightChip", "{count} kg", { count: String(item.weight_kg) }) : "",
          boolLabel(
            item.requires_lot,
            t,
            "agentConsole.lotTrackedChip",
            "Lot tracked",
            "agentConsole.noLotChip",
            "No lot",
          ),
          boolLabel(
            item.requires_expiry,
            t,
            "agentConsole.expiryTrackedChip",
            "Expiry tracked",
            "agentConsole.noExpiryChip",
            "No expiry",
          ),
        ].filter(Boolean),
        href: "/skus",
        ctaLabel: t("agentConsole.openSkus", "Open SKUs"),
      }));
    }

    if (result.tool_name === "billing.rate_cards.list") {
      return payload.items.map((item: any) => ({
        title: item.name || t("agentConsole.unknownRateCard", "Untitled rate card"),
        subtitle: item.client_name || "",
        chips: [
          item.effective_from
            ? t("agentConsole.effectiveFromChip", "Effective from {value}", { value: item.effective_from })
            : "",
          boolLabel(
            item.is_active,
            t,
            "agentConsole.activeChip",
            "Active",
            "agentConsole.inactiveChip",
            "Inactive",
          ),
        ].filter(Boolean),
        href: "/clients",
        ctaLabel: t("agentConsole.openClientProfiles", "Open client profiles"),
      }));
    }
  }

  return [] as RenderedItemCard[];
}

function emptyResultMessage(
  result: ToolRunResponse | null,
  t: (key: string, fallback?: string, vars?: Record<string, string>) => string,
) {
  if (!result) return "";
  const payload = result.result || {};
  if (!Array.isArray(payload.items) || payload.items.length) return "";

  if (result.tool_name === "orders.inbound.list") {
    return t("agentConsole.emptyInbound", "There are no inbound orders waiting to be received.");
  }
  if (result.tool_name === "inventory.search") {
    return t("agentConsole.emptyInventorySearch", "No inventory matched this search.");
  }
  if (result.tool_name === "warehouses.list") {
    return t("agentConsole.emptyWarehouses", "This tenant has no warehouse master data yet.");
  }
  if (result.tool_name === "skus.list") {
    return t("agentConsole.emptySkus", "There are no SKU master records yet.");
  }
  if (result.tool_name === "billing.rate_cards.list") {
    return t("agentConsole.emptyRateCards", "There are no active rate cards yet.");
  }
  return t("agentConsole.emptyGenericList", "There is nothing to display yet.");
}

function classifyToolGroup(toolKey: string) {
  if (toolKey.includes(".preview_") || toolKey.includes(".import") || toolKey.includes("migration.")) return "import";
  if (toolKey.includes(".create") || toolKey.includes(".update") || toolKey.includes(".delete")) return "write";
  return "read";
}

function mobileToolPolicy(tool: ToolItem) {
  return TOOL_GOVERNANCE[tool.key]?.mobilePolicy || (tool.risk === "low" ? "phone-primary" : "desktop-preferred");
}

function riskTone(risk: string) {
  if (risk === "high") return "bg-[#fff2ea] text-[#8f4b2c] border-[#e8c0ad]";
  if (risk === "medium") return "bg-[#fff8ea] text-[#8a6520] border-[#ead39a]";
  return "bg-[#eef8f3] text-[#2f6f54] border-[#b8ddc7]";
}

function toolLabel(toolName: string, t: (key: string, fallback?: string, vars?: Record<string, string>) => string) {
  const action = STARTER_ACTIONS.find((item) => item.tool_name === toolName);
  if (action) return t(action.titleKey, action.titleFallback);

  const labels: Record<string, [string, string]> = {
    "inventory.explain": ["agentConsole.toolInventoryExplain", "Explain current inventory"],
    "clients.list": ["agentConsole.toolClientsList", "List clients"],
    "clients.get": ["agentConsole.toolClientsGet", "Inspect one client"],
    "receiving.inbound.preview_import": ["agentConsole.toolInboundPreview", "Preview inbound import"],
    "receiving.inbound.import_with_mapping": ["agentConsole.toolInboundImport", "Import mapped inbound data"],
    "orders.outbound.preview_import": ["agentConsole.toolOutboundPreview", "Preview outbound import"],
    "orders.outbound.import_with_mapping": ["agentConsole.toolOutboundImport", "Import mapped outbound data"],
    "migration.inventory.preview": ["agentConsole.toolInventoryMigrationPreview", "Preview inventory import"],
    "migration.inventory.import": ["agentConsole.toolInventoryMigrationImport", "Import inventory data"],
    "warehouse.blueprint.preview": ["agentConsole.toolWarehouseBlueprintPreview", "Preview warehouse blueprint"],
    "clients.create": ["agentConsole.toolClientsCreate", "Create client"],
    "skus.create": ["agentConsole.toolSkusCreate", "Create SKU"],
    "receiving.inbound.create": ["agentConsole.toolInboundCreate", "Create inbound order"],
    "users.create": ["agentConsole.toolUsersCreate", "Create user"],
    "users.update_permissions": ["agentConsole.toolUsersPermissions", "Update user permissions"],
  };
  const pair = labels[toolName];
  if (pair) return t(pair[0], pair[1]);
  return toolName;
}

function detectImportKind(fileName: string, csvText: string): ImportKind | null {
  const lowerName = fileName.toLowerCase();
  if (/(inventory|stock|\u5eab\u5b58|\u5728\u5eab)/.test(lowerName)) return "inventory";
  if (/(outbound|shipping|shipment|ship|sales|\u51fa\u8ca8|\u53d1\u8d27|\u767c\u8ca8)/.test(lowerName)) return "outbound";
  if (/(inbound|receiving|receipt|asn|\u6536\u8ca8|\u6536\u8d27|\u5165\u5eab|\u5165\u5e93)/.test(lowerName)) return "inbound";

  const firstLine = csvText.split(/\r?\n/).find((line) => line.trim()) || "";
  const headers = firstLine
    .split(",")
    .map((header) => header.trim().toLowerCase())
    .filter(Boolean);

  if (headers.includes("location_barcode") || headers.includes("location") || headers.includes("bin")) {
    return "inventory";
  }
  if (headers.includes("carrier") || headers.includes("ship_via") || headers.includes("shipping_carrier")) {
    return "outbound";
  }
  if (headers.includes("supplier_name") || headers.includes("vendor") || headers.includes("asn")) {
    return "inbound";
  }
  if (headers.includes("lot_number") && headers.includes("location_barcode")) {
    return "inventory";
  }
  return null;
}

function normalizeInventoryQuery(rawQuery: string) {
  const trimmed = rawQuery.trim();
  if (!trimmed) return "";

  let normalized = trimmed;
  const cleanupPatterns = [
    /\u5e6b\u6211/gi,
    /\u5e2e\u6211/gi,
    /\u8acb/gi,
    /\u8bf7/gi,
    /\u770b\u4e00\u4e0b/gi,
    /\u770b\u4e0b/gi,
    /\u770b/gi,
    /\u67e5\u4e00\u4e0b/gi,
    /\u67e5\u4e0b/gi,
    /\u67e5\u8a62/gi,
    /\u67e5\u8be2/gi,
    /\u67e5/gi,
    /\u544a\u8a34\u6211/gi,
    /\u544a\u8bc9\u6211/gi,
    /\u73fe\u5728/gi,
    /\u73b0\u5728/gi,
    /\u7576\u524d/gi,
    /\u5f53\u524d/gi,
    /\u76ee\u524d/gi,
    /\u6709\u6c92\u6709/gi,
    /\u6709\u6ca1\u6709/gi,
    /\u60c5\u6cc1/gi,
    /\u60c5\u51b5/gi,
    /\u7e3d\u89bd/gi,
    /\u603b\u89c8/gi,
    /\u72c0\u6cc1/gi,
    /\u72b6\u51b5/gi,
    /\u5eab\u5b58/gi,
    /\u5e93\u5b58/gi,
    /\u73fe\u8ca8/gi,
    /\u73b0\u8d27/gi,
    /\bon[\s-]?hand\b/gi,
    /\bavailable\b/gi,
    /\binventory\b/gi,
    /\bstock\b/gi,
    /\boverview\b/gi,
    /\bstatus\b/gi,
    /\bshow me\b/gi,
    /\bcheck\b/gi,
    /\bfind\b/gi,
    /\bwhat'?s\b/gi,
    /\bwhat is\b/gi,
    /\bfor\b/gi,
    /\bthe\b/gi,
    /\bmy\b/gi,
    /\u7684/gi,
    /\u5462/gi,
    /\u55ce/gi,
    /\u5417/gi,
    /？/g,
    /\?/g,
    /：/g,
    /:/g,
    /，/g,
    /,/g,
  ];

  for (const pattern of cleanupPatterns) {
    normalized = normalized.replace(pattern, " ");
  }

  normalized = normalized.replace(/\s+/g, " ").trim();
  return normalized;
}

function matchesPromptIntent(rawQuery: string, patterns: RegExp[]) {
  return patterns.some((pattern) => pattern.test(rawQuery));
}

function routeUserPrompt(
  rawQuery: string,
  enabledTools: Set<string>,
  language: string,
): RoutedAction {
  const trimmed = rawQuery.trim();
  if (!trimmed) return null;

  const setupPatterns = [/setup/i, /\u8a2d\u5b9a/gi, /\u8bbe\u5b9a/gi, /\u7f3a\u54ea\u4e9b/gi, /\u9084\u7f3a/gi, /\u8fd8\u7f3a/gi, /\u7f3a\u53e3/gi];
  if (enabledTools.has("setup.progress") && matchesPromptIntent(trimmed, setupPatterns)) {
    return { tool_name: "setup.progress", args: {} };
  }

  const inboundPatterns = [/\u5f85\u5165\u5eab/gi, /\u5f85\u5165\u5e93/gi, /\u5f85\u6536\u8ca8/gi, /\u5f85\u6536\u8d27/gi, /\u6536\u8ca8/gi, /\u6536\u8d27/gi, /inbound/i, /receipt/i];
  if (enabledTools.has("orders.inbound.list") && matchesPromptIntent(trimmed, inboundPatterns)) {
    return { tool_name: "orders.inbound.list", args: { status: "expected", limit: 8 } };
  }

  const outboundPatterns = [
    /\u5f85\u51fa\u5eab/gi,
    /\u5f85\u51fa\u5e93/gi,
    /\u5f85\u767c\u8ca8/gi,
    /\u5f85\u53d1\u8d27/gi,
    /\u51fa\u8ca8/gi,
    /\u51fa\u8d27/gi,
    /\u767c\u8ca8/gi,
    /\u53d1\u8d27/gi,
    /outbound/i,
    /shipment/i,
    /shipping/i,
  ];
  if (enabledTools.has("orders.outbound.list") && matchesPromptIntent(trimmed, outboundPatterns)) {
    return { tool_name: "orders.outbound.list", args: { limit: 8 } };
  }

  const billingPatterns = [/\u8cbb\u7387/gi, /\u8d39\u7387/gi, /\u8a08\u8cbb/gi, /\u8ba1\u8d39/gi, /rate\s*card/i, /billing/i];
  if (enabledTools.has("billing.rate_cards.list") && matchesPromptIntent(trimmed, billingPatterns)) {
    return { tool_name: "billing.rate_cards.list", args: { limit: 8 } };
  }

  const clientPatterns = [/\u5ba2\u6236/gi, /\u5ba2\u6237/gi, /\u5ba2\u6236\u540d\u55ae/gi, /\u5ba2\u6237\u540d\u5355/gi, /\bclient\b/i, /\bcustomer\b/i];
  if (enabledTools.has("clients.list") && matchesPromptIntent(trimmed, clientPatterns)) {
    return { tool_name: "clients.list", args: { limit: 8 } };
  }

  const warehousePatterns = [/\u5009\u5eab/gi, /\u4ed3\u5e93/gi, /warehouse/i];
  if (enabledTools.has("warehouses.list") && matchesPromptIntent(trimmed, warehousePatterns)) {
    return { tool_name: "warehouses.list", args: { limit: 8 } };
  }

  const skuPatterns = [/\bsku\b/i, /\u54c1\u9805/gi, /\u54c1\u9879/gi, /\u5546\u54c1/gi];
  if (enabledTools.has("skus.list") && matchesPromptIntent(trimmed, skuPatterns)) {
    return { tool_name: "skus.list", args: { limit: 8 } };
  }

  const normalizedInventoryQuery = normalizeInventoryQuery(trimmed);
  if (enabledTools.has("inventory.explain")) {
    return {
      tool_name: "inventory.explain",
      args: { query: normalizedInventoryQuery, limit: 12, language },
    };
  }
  if (enabledTools.has("inventory.search")) {
    return {
      tool_name: "inventory.search",
      args: { query: normalizedInventoryQuery, limit: 12, language },
    };
  }

  return null;
}

function summarizeResult(
  result: ToolRunResponse | null,
  t: (key: string, fallback?: string, vars?: Record<string, string>) => string,
) {
  if (!result) return [];
  const payload = result.result || {};
  const lines: string[] = [];

  if (typeof payload.count === "number") {
    lines.push(t("agentConsole.summaryCount", "{count} records returned", { count: String(payload.count) }));
  }
  if (typeof payload.total_rows === "number" && Array.isArray(payload.missing_required)) {
    lines.push(
      t("agentConsole.summaryPreviewRows", "Previewing {rows} rows", { rows: String(payload.total_rows) }),
    );
    lines.push(
      t("agentConsole.summaryMissingMappings", "{count} required mappings still missing", {
        count: String(payload.missing_required.length),
      }),
    );
  }
  if (typeof payload.imported === "number") {
    lines.push(t("agentConsole.summaryImported", "{count} records imported", { count: String(payload.imported) }));
  }
  if (Array.isArray(payload.errors)) {
    lines.push(t("agentConsole.summaryErrors", "{count} errors returned", { count: String(payload.errors.length) }));
  }
  if (typeof payload.query === "string" && payload.query) {
    lines.push(t("agentConsole.summaryQuery", "Search query: {query}", { query: payload.query }));
  }
  if (typeof payload.answer === "string" && payload.answer.trim()) {
    const snippet = sanitizeModelAnswer(payload.answer).replace(/\s+/g, " ").slice(0, 120);
    lines.push(t("agentConsole.summaryAnswer", "Model takeaway: {answer}", { answer: snippet }));
  }

  return lines.slice(0, 4);
}

export default function AgentConsolePage() {
  const { t, language } = useI18n();
  const permissions = useAuthStore((s) => s.permissions);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [result, setResult] = useState<ToolRunResponse | null>(null);
  const [error, setError] = useState("");
  const [csvText, setCsvText] = useState("");
  const [attachedImportName, setAttachedImportName] = useState("");
  const [attachedImportKind, setAttachedImportKind] = useState<ImportKind | null>(null);
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [importError, setImportError] = useState("");
  const [needsImportConfirmation, setNeedsImportConfirmation] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState("");
  const hasAutoRunStatusRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const hasPermission = (permission: string) => permissions.includes("*") || permissions.includes(permission);
  const canUseConsole =
    hasPermission("users.manage") ||
    hasPermission("inbound_orders.manage") ||
    hasPermission("inbound_orders.import") ||
    hasPermission("receiving.execute") ||
    hasPermission("outbound_orders.manage") ||
    hasPermission("master_data.manage") ||
    hasPermission("billing.manage") ||
    hasPermission("planner.manage");

  const canRunTool = (toolName: string) => {
    const governance = TOOL_GOVERNANCE[toolName];
    if (governance) return hasPermission(governance.permission);
    return permissions.includes("*");
  };

  const visibleActions = STARTER_ACTIONS.filter((action) => canRunTool(action.tool_name));

  const settingsQuery = useQuery({
    queryKey: queryKeys.agent.settings(),
    queryFn: () => fetchAgentSettings<AgentSettings>(),
    enabled: canUseConsole,
  });
  const isEnabled = Boolean(settingsQuery.data?.enabled);
  const hasModelConfigured = Boolean(settingsQuery.data?.provider_label || settingsQuery.data?.model_name);
  const validationStatus = settingsQuery.data?.validation_status || null;
  const setupState = !hasModelConfigured
    ? "missing"
    : validationStatus === "valid"
      ? isEnabled
        ? "ready"
        : "disabled"
      : validationStatus === "unsupported"
        ? "invalid"
        : isEnabled
          ? "ready"
          : "disabled";
  const setupTone =
    setupState === "ready"
      ? "border-[#cbe3d5] bg-[#eef8f3] text-[#2f6f54]"
      : setupState === "invalid"
        ? "border-[#e5c7b8] bg-[#fff2ea] text-[#8f4b2c]"
        : "border-[#ead39a] bg-[#fff8ea] text-[#8a6520]";
  const setupTitle =
    setupState === "ready"
      ? t("agentConsole.setupReadyTitle", "AI setup is complete. You can start using the AI console.")
      : setupState === "invalid"
        ? t("agentConsole.setupInvalidTitle", "AI setup has not passed validation yet. Fix it in AI settings first.")
        : setupState === "disabled"
          ? t("agentConsole.setupDisabledTitle", "The model is connected, but the AI assistant is still turned off.")
          : t("agentConsole.setupMissingTitle", "Finish AI setup first, then come back to use the AI console.");
  const setupBody =
    setupState === "ready"
      ? t("agentConsole.setupReadyBody", "The model, tool boundaries, and assistant status are ready. Run the system check first, then test governed flows step by step.")
      : setupState === "invalid"
        ? settingsQuery.data?.validation_message ||
          t("agentConsole.setupInvalidBody", "The model or API key has not validated successfully yet. Fix it in AI settings before this page unlocks.")
        : setupState === "disabled"
          ? t("agentConsole.setupDisabledBody", "The model and key are saved, but the AI assistant is not enabled for this workspace yet. Turn it on in AI settings, then come back to start testing.")
          : t("agentConsole.setupMissingBody", "This workspace has not finished model and API key setup. Connect a model first, then come back for chat, explanations, and governed execution.");

  const enabledTools = useMemo(
    () => new Set(settingsQuery.data?.allowed_tools || []),
    [settingsQuery.data?.allowed_tools],
  );

  const visibleToolCatalog = useMemo(
    () => (settingsQuery.data?.tool_catalog || []).filter((tool) => canRunTool(tool.key)),
    [settingsQuery.data?.tool_catalog, permissions],
  );

  const toolRiskStats = useMemo(() => {
    const visibleKeys = new Set(visibleToolCatalog.map((tool) => tool.key));
    const allowedVisible = (settingsQuery.data?.allowed_tools || []).filter((key) => visibleKeys.has(key));
    return {
      low: allowedVisible.filter((key) => visibleToolCatalog.find((tool) => tool.key === key)?.risk === "low").length,
      medium: allowedVisible.filter((key) => visibleToolCatalog.find((tool) => tool.key === key)?.risk === "medium").length,
      high: allowedVisible.filter((key) => visibleToolCatalog.find((tool) => tool.key === key)?.risk === "high").length,
      allowedTotal: allowedVisible.length,
    };
  }, [settingsQuery.data?.allowed_tools, visibleToolCatalog]);

  const resultSummary = useMemo(() => summarizeResult(result, t), [result, t]);
  const resultCards = useMemo(() => formatToolCards(result, t), [result, t]);
  const resultEmptyText = useMemo(() => emptyResultMessage(result, t), [result, t]);
  const blueprintPreview = useMemo(
    () => extractWarehouseBlueprintPreview(result?.result),
    [result?.result],
  );
  const blueprintWcsRoleCounts = useMemo(
    () => countByField((blueprintPreview?.wcs_point_mapping_draft || []) as Record<string, unknown>[], "point_role"),
    [blueprintPreview?.wcs_point_mapping_draft],
  );
  const isSetupResult = result?.tool_name === "setup.progress";
  const setupResultStats = useMemo(() => {
    if (!isSetupResult || !Array.isArray(result?.result?.steps)) return null;
    const steps = result.result.steps as Array<{ done?: boolean }>;
    const completed = steps.filter((step) => step.done).length;
    return { total: steps.length, completed, pending: steps.length - completed };
  }, [isSetupResult, result?.result?.steps]);
  const groupedToolCatalog = useMemo(() => {
    const toolGroups: ToolGroup[] = [
      {
        key: "read",
        title: t("agentConsole.groupReadTitle", "Search and inspect"),
        body: t("agentConsole.groupReadBody", "Understand the current state, gaps, and master data before opening the next step."),
        tools: [],
      },
      {
        key: "import",
        title: t("agentConsole.groupImportTitle", "Import and preview"),
        body: t("agentConsole.groupImportBody", "Preview, map, and confirm. These flows are the best fit for the first stage of agent use."),
        tools: [],
      },
      {
        key: "write",
        title: t("agentConsole.groupWriteTitle", "Create and change"),
        body: t("agentConsole.groupWriteBody", "These actions change data and should pair with human confirmation and a clear audit trail."),
        tools: [],
      },
    ];

    for (const tool of visibleToolCatalog) {
      const group = toolGroups.find((item) => item.key === classifyToolGroup(tool.key));
      if (group) group.tools.push(tool);
    }
    return toolGroups.filter((group) => group.tools.length > 0);
  }, [t, visibleToolCatalog]);

  const groupedMobileToolCatalog = useMemo(() => {
    const mobileTools = visibleToolCatalog.filter((tool) => mobileToolPolicy(tool) === "phone-primary");
    const toolGroups: ToolGroup[] = [
      {
        key: "read",
        title: t("agentConsole.mobileReadGroupTitle", "Phone-safe read tools"),
        body: t("agentConsole.mobileReadGroupBody", "Use these on phone to inspect setup, orders, inventory, clients, SKUs, warehouses, and billing readiness without changing records."),
        tools: [],
      },
      {
        key: "import",
        title: t("agentConsole.mobilePreviewGroupTitle", "Phone-safe preview tools"),
        body: t("agentConsole.mobilePreviewGroupBody", "Preview and mapping checks can be reviewed on phone; the final import stays desktop-preferred."),
        tools: [],
      },
    ];

    for (const tool of mobileTools) {
      const group = toolGroups.find((item) => item.key === classifyToolGroup(tool.key));
      if (group) group.tools.push(tool);
    }
    return toolGroups.filter((group) => group.tools.length > 0);
  }, [t, visibleToolCatalog]);
  const answerSections = useMemo(() => {
    if (typeof result?.result?.answer !== "string") return [] as AnswerSection[];
    return splitModelAnswer(result.result.answer, t);
  }, [result?.result?.answer, t]);
  const hasModelAnswer = answerSections.length > 0;

  const promptShortcuts = useMemo<PromptShortcut[]>(
    () =>
      [
        {
          key: "setup",
          labelKey: "agentConsole.promptSetup",
          labelFallback: "Show me what setup is still missing",
          helperKey: "agentConsole.promptSetupBody",
          helperFallback: "Check setup gaps first. Best for your first visit.",
          tool_name: "setup.progress",
          args: {},
        },
        {
          key: "inbound",
          labelKey: "agentConsole.promptInbound",
          labelFallback: "Show me today's expected inbound orders",
          helperKey: "agentConsole.promptInboundBody",
          helperFallback: "Review pending receiving work without switching to the receiving page.",
          tool_name: "orders.inbound.list",
          args: { status: "expected", limit: 8 },
        },
        {
          key: "inventory",
          labelKey: "agentConsole.promptInventory",
          labelFallback: "Look up inventory for this SKU or client",
          helperKey: "agentConsole.promptInventoryBody",
          helperFallback: "Type your search terms below, then let the AI look them up and explain.",
          tool_name: "inventory.search",
          args: { query: normalizeInventoryQuery(searchQuery), limit: 12, language },
        },
        {
          key: "billing",
          labelKey: "agentConsole.promptBilling",
          labelFallback: "Check which client rate cards are active",
          helperKey: "agentConsole.promptBillingBody",
          helperFallback: "Useful for confirming which rules are in effect before billing.",
          tool_name: "billing.rate_cards.list",
          args: { limit: 8 },
        },
      ].filter((item) => canRunTool(item.tool_name)),
    [canRunTool, language, searchQuery],
  );

  const routedPromptAction = useMemo(
    () => routeUserPrompt(searchQuery, enabledTools, language),
    [enabledTools, language, searchQuery],
  );

  const handleCopy = async (value: string, successMessage: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopyFeedback(successMessage);
      window.setTimeout(() => setCopyFeedback(""), 2400);
    } catch {
      setCopyFeedback(t("agentConsole.copyFailed", "Could not copy text."));
      window.setTimeout(() => setCopyFeedback(""), 2400);
    }
  };

  const runMutation = useMutation({
    mutationFn: async ({ tool_name, args }: { tool_name: string; args: Record<string, unknown> }) =>
      runAgentTool<ToolRunResponse>({ tool_name, args }),
    onSuccess: (data) => {
      setResult(data);
      setError("");
    },
    onError: (err: any) => {
      setResult(null);
      setError(getApiErrorMessage(err, t("agentConsole.runError", "The agent tool could not complete that request.")));
    },
  });

  const runAction = (toolName: string, args: Record<string, unknown>) => {
    setSelectedTool(toolName);
    runMutation.mutate({ tool_name: toolName, args });
  };

  const submitPrompt = () => {
    if (csvText.trim()) {
      previewMutation.mutate();
      return;
    }
    if (!routedPromptAction) return;
    runAction(routedPromptAction.tool_name, routedPromptAction.args);
  };

  const importMeta = useMemo(() => {
    const base = {
      inbound: {
        previewTool: "receiving.inbound.preview_import",
        importTool: "receiving.inbound.import_with_mapping",
        kindLabel: t("agentConsole.importKindInbound", "Receiving / inbound"),
        attachLabel: t("agentConsole.attachInbound", "Attach receiving file"),
      },
      inventory: {
        previewTool: "migration.inventory.preview",
        importTool: "migration.inventory.import",
        kindLabel: t("agentConsole.importKindInventory", "Inventory"),
        attachLabel: t("agentConsole.attachInventory", "Attach inventory file"),
      },
      outbound: {
        previewTool: "orders.outbound.preview_import",
        importTool: "orders.outbound.import_with_mapping",
        kindLabel: t("agentConsole.importKindOutbound", "Shipping / outbound"),
        attachLabel: t("agentConsole.attachOutbound", "Attach shipping file"),
      },
    } as const;
    return attachedImportKind ? base[attachedImportKind] : null;
  }, [attachedImportKind, t]);

  const clearAttachment = () => {
    setCsvText("");
    setAttachedImportName("");
    setAttachedImportKind(null);
    setImportPreview(null);
    setMapping({});
    setImportError("");
    setNeedsImportConfirmation(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAttachedFile = async (file: File | null) => {
    if (!file) return;
    const text = await file.text();
    const inferredKind = detectImportKind(file.name, text);
    setCsvText(text);
    setAttachedImportName(file.name);
    setAttachedImportKind(inferredKind);
    setImportPreview(null);
    setMapping({});
    setImportError(
      inferredKind
        ? ""
        : t("agentConsole.importKindUnknown", "Could not tell whether this file is inventory, receiving, or shipping data. Check the file name or column headers."),
    );
    setNeedsImportConfirmation(false);
  };

  useEffect(() => {
    if (!canUseConsole || setupState !== "ready") return;
    if (!canRunTool("setup.progress")) return;
    if (hasAutoRunStatusRef.current) return;
    hasAutoRunStatusRef.current = true;
    setSelectedTool("setup.progress");
    runMutation.mutate({ tool_name: "setup.progress", args: {} });
  }, [canRunTool, canUseConsole, runMutation, setupState]);

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!importMeta) {
        throw new Error(t("agentConsole.importKindUnknown", "Could not tell whether this file is inventory, receiving, or shipping data. Check the file name or column headers."));
      }
      return runAgentTool<ToolRunResponse>({
        tool_name: importMeta.previewTool,
        args: { csv_text: csvText, file_name: attachedImportName || "agent-inline.csv" },
      });
    },
    onMutate: () => {
      setSelectedTool(importMeta?.previewTool || null);
    },
    onSuccess: (data) => {
      const preview = data.result as ImportPreview;
      setImportPreview(preview);
      setMapping(preview.suggested_mapping || {});
      setImportError("");
      setNeedsImportConfirmation(false);
      setResult(data);
    },
    onError: (err: any) => {
      setImportError(getApiErrorMessage(err, t("agentConsole.previewError", "Could not preview this file.")));
    },
  });

  const importMutation = useMutation({
    mutationFn: async (confirmed: boolean) =>
      !importMeta
        ? Promise.reject(new Error(t("agentConsole.importKindUnknown", "Could not tell whether this file is inventory, receiving, or shipping data. Check the file name or column headers.")))
        : runAgentTool<ToolRunResponse>({
            tool_name: importMeta.importTool,
            args: {
              csv_text: csvText,
              file_name: attachedImportName || "agent-inline.csv",
              mapping,
              confirmed,
            },
          }),
    onMutate: () => {
      setSelectedTool(importMeta?.importTool || null);
    },
    onSuccess: (data) => {
      setResult(data);
      setImportError("");
      setNeedsImportConfirmation(false);
      clearAttachment();
    },
    onError: (err: any) => {
      const message = getApiErrorMessage(err, t("agentConsole.importError", "Could not import this file."));
      if ((err?.response?.status || 0) === 409) {
        setNeedsImportConfirmation(true);
      }
      setImportError(message);
    },
  });

  const importStage = useMemo(() => {
    if (importMutation.isPending) return "confirm";
    if (importPreview) return needsImportConfirmation ? "confirm" : "map";
    if (csvText.trim()) return "draft";
    return "draft";
  }, [csvText, importPreview, importMutation.isPending, needsImportConfirmation]);

  const guidedImportSteps = useMemo<GuidedStep[]>(
    () => [
      {
        key: "draft",
        title: t("agentConsole.importStepDraftTitleGeneric", "1. Attach the file"),
        body: t("agentConsole.importStepDraftBodyGeneric", "Drop the file in first, then let the AI run the first pass of detection and checks."),
        active: importStage === "draft",
        complete: Boolean(csvText.trim() && importPreview),
      },
      {
        key: "map",
        title: t("agentConsole.importStepMapTitle", "2. Review the mapping"),
        body: t("agentConsole.importStepMapBody", "Confirm every required field is mapped correctly before deciding to write the data."),
        active: importStage === "map",
        complete: Boolean(importPreview),
      },
      {
        key: "confirm",
        title: t("agentConsole.importStepConfirmTitle", "3. Confirm the import"),
        body: t("agentConsole.importStepConfirmBody", "Data is only written into the system after you confirm, and an audit trail is kept."),
        active: importStage === "confirm",
        complete: Boolean(
          importMeta?.importTool && result?.tool_name === importMeta.importTool && !importMutation.isPending,
        ),
      },
    ],
    [csvText, importMeta?.importTool, importPreview, importMutation.isPending, importStage, result?.tool_name, t],
  );

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {canUseConsole && setupState !== "ready" ? (
        <section className={`rounded-[1.2rem] border p-5 shadow-[0_10px_24px_rgba(19,33,44,0.05)] ${setupTone}`}>
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold">{setupTitle}</p>
              <p className="mt-2 text-sm leading-6">{setupBody}</p>
              {hasModelConfigured ? (
                <p className="mt-3 text-sm font-medium">
                  {t("agentConsole.providerLine", "Current model: {label}", {
                    label: settingsQuery.data?.provider_label || settingsQuery.data?.model_name || "—",
                  })}
                </p>
              ) : null}
            </div>
            <Link
              to="/agent-settings"
              className="inline-flex items-center justify-center rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold text-[#f4efe8] transition hover:bg-[#1b2d39]"
            >
              {t("agentConsole.openSettings", "Open AI assistant settings")}
            </Link>
          </div>
        </section>
      ) : null}

      {!canUseConsole ? (
        <section className="rounded-[1.2rem] border border-[#e5c7b8] bg-[#fff2ea] p-5 text-[#8f4b2c] shadow-[0_10px_24px_rgba(143,75,44,0.06)]">
          <p className="text-sm font-semibold">{t("agentConsole.accessTitle", "Agent console access is role-based")}</p>
          <p className="mt-2 text-sm leading-6">
            {t(
              "agentConsole.accessBody",
              "This console only appears for roles that can safely use at least one approved agent tool. Ask your tenant admin to grant the right operational permissions for inbound, outbound, master data, billing, planning, or user setup.",
            )}
          </p>
        </section>
      ) : null}

      {canUseConsole && setupState === "ready" ? (
        <section
          className="rounded-[1.1rem] border border-[#13212c]/10 bg-white/84 px-4 py-3 text-sm leading-6 text-[#51606b] md:hidden"
          data-testid="agent-console-mobile-governance"
          data-admin-mobile-contract="read-tools-first"
        >
          <p className="font-semibold text-[#13212c]">
            {t("agentConsole.mobileGovernanceTitle", "Agent Console is governed on phone")}
          </p>
          <p className="mt-1">
            {t(
              "agentConsole.mobileGovernanceBody",
              "Phone use is for low-risk read tools and import previews. File imports, billing or permission changes, and high-risk confirmations should be completed on iPad or desktop.",
            )}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full border border-[#13212c]/8 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#425461]">
              {t("agentConsole.mobileReadTools", "Read tools first")}
            </span>
            <span className="rounded-full border border-[#13212c]/8 bg-[#f7f4ee] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#425461]">
              {t("agentConsole.mobileWritesConfirm", "Writes require approval")}
            </span>
          </div>
        </section>
      ) : null}

      {setupState === "ready" ? (
      <div className="space-y-4">
        <section className="flex h-[calc(100vh-13rem)] max-h-[calc(100vh-13rem)] flex-col overflow-hidden rounded-[1.4rem] border border-[#13212c]/8 bg-white shadow-[0_10px_24px_rgba(19,33,44,0.05)]">
          <div className="flex-1 overflow-y-auto px-6 py-6">
            {result ? (
              <div className="space-y-4">
                {isSetupResult && setupResultStats && !hasModelAnswer ? (
                  <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">
                          {t("agentConsole.systemCheck", "System status check")}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-[#5e6d79]">
                          {setupResultStats.pending > 0
                            ? t(
                                "agentConsole.setupSummaryPending",
                                "{completed}/{total} steps are done, with {pending} still to finish.",
                                {
                                  completed: String(setupResultStats.completed),
                                  total: String(setupResultStats.total),
                                  pending: String(setupResultStats.pending),
                                },
                              )
                            : t(
                                "agentConsole.setupSummaryDone",
                                "All {total} setup steps are complete. You can continue with the AI chat.",
                                { total: String(setupResultStats.total) },
                              )}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-full border border-[#d8e0e6] bg-[#f7f4ee] px-3 py-1.5 text-xs font-medium text-[#425461]">
                          {t("agentConsole.setupSummaryCompleted", "Done {count}", {
                            count: String(setupResultStats.completed),
                          })}
                        </span>
                        {setupResultStats.pending > 0 ? (
                          <span className="rounded-full border border-[#ead39a] bg-[#fff8ea] px-3 py-1.5 text-xs font-medium text-[#8a6520]">
                            {t("agentConsole.setupSummaryPendingChip", "Pending {count}", {
                              count: String(setupResultStats.pending),
                            })}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <details className="mt-4 rounded-[1rem] border border-[#13212c]/10 bg-[#f9f6f0] p-4">
                      <summary className="cursor-pointer text-sm font-semibold text-[#13212c]">
                        {t("agentConsole.setupSummaryDetails", "View setup details")}
                      </summary>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        {resultCards.map((card) => (
                          <div
                            key={`${card.title}-${card.subtitle || ""}`}
                            className="rounded-[1rem] border border-[#13212c]/10 bg-white p-3"
                          >
                            <p className="text-sm font-semibold text-[#13212c]">{card.title}</p>
                            {card.subtitle ? (
                              <p className="mt-1 text-sm leading-6 text-[#5e6d79]">{card.subtitle}</p>
                            ) : null}
                            {card.chips?.length ? (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {card.chips.map((chip) => (
                                  <span
                                    key={chip}
                                    className="rounded-full border border-[#d8e0e6] bg-[#f7f4ee] px-3 py-1.5 text-xs font-medium text-[#425461]"
                                  >
                                    {chip}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                            {card.href && card.ctaLabel ? (
                              <div className="mt-3">
                                <Link
                                  to={card.href}
                                  className="inline-flex items-center rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-xs font-semibold text-[#13212c] transition hover:bg-[#fffdfa]"
                                >
                                  {card.ctaLabel}
                                </Link>
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </details>
                  </div>
                ) : null}
                {blueprintPreview ? (
                  <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">
                          {t("agentConsole.blueprintSummaryTitle", "Warehouse blueprint preview")}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-[#5e6d79]">
                          {t(
                            "agentConsole.blueprintSummaryBody",
                            "Review the layout first. WCS point mappings stay as a draft until the warehouse layout is confirmed, then validated and imported from Warehouse Planner.",
                          )}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span className={`rounded-full border px-3 py-1.5 text-xs font-medium ${blueprintPreview.ok === false ? "border-[#e5c7b8] bg-[#fff2ea] text-[#8f4b2c]" : "border-[#cbe3d5] bg-[#eef8f3] text-[#2f6f54]"}`}>
                          {blueprintPreview.ok === false
                            ? t("agentConsole.blueprintNeedsFix", "Needs layout fixes")
                            : t("agentConsole.blueprintReady", "Ready for layout review")}
                        </span>
                        {blueprintPreview.target?.code ? (
                          <span className="rounded-full border border-[#d8e0e6] bg-[#f7f4ee] px-3 py-1.5 text-xs font-medium text-[#425461]">
                            {blueprintPreview.target.code}
                          </span>
                        ) : null}
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-4">
                      <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f9f6f0] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7e8d98]">
                          {t("agentConsole.blueprintAbcAreas", "ABC floor areas")}
                        </p>
                        <p className="mt-2 text-2xl font-semibold text-[#13212c]">
                          {blueprintPreview.abc_floor_areas?.length || 0}
                        </p>
                        <p className="mt-1 text-xs leading-5 text-[#61717d]">
                          {t("agentConsole.blueprintAbcAreaDetail", "{count} floor-storage locations", {
                            count: String(
                              (blueprintPreview.abc_floor_areas || []).reduce((sum, area) => sum + (area.location_count || 0), 0),
                            ),
                          })}
                        </p>
                      </div>
                      <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f9f6f0] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7e8d98]">
                          {t("agentConsole.blueprintRackAreas", "Rack areas")}
                        </p>
                        <p className="mt-2 text-2xl font-semibold text-[#13212c]">
                          {blueprintPreview.rack_areas?.length || 0}
                        </p>
                        <p className="mt-1 text-xs leading-5 text-[#61717d]">
                          {t("agentConsole.blueprintRackAreaDetail", "{count} rack locations", {
                            count: String(
                              (blueprintPreview.rack_areas || []).reduce((sum, area) => sum + (area.location_count || 0), 0),
                            ),
                          })}
                        </p>
                      </div>
                      <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f9f6f0] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7e8d98]">
                          {t("agentConsole.blueprintDockDoors", "Dock doors")}
                        </p>
                        <p className="mt-2 text-2xl font-semibold text-[#13212c]">
                          {blueprintPreview.dock_doors?.length || 0}
                        </p>
                        <p className="mt-1 text-xs leading-5 text-[#8a6520]">
                          {t("agentConsole.blueprintDockDoorExternal", "External point / not storage location")}
                        </p>
                      </div>
                      <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f9f6f0] p-4">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#7e8d98]">
                          {t("agentConsole.blueprintWcsDraft", "WCS draft")}
                        </p>
                        <p className="mt-2 text-2xl font-semibold text-[#13212c]">
                          {blueprintPreview.wcs_point_mapping_draft?.length || 0}
                        </p>
                        <p className="mt-1 text-xs leading-5 text-[#61717d]">
                          {compactCountMap(blueprintWcsRoleCounts) ||
                            t("agentConsole.blueprintNoWcsRoles", "No point roles yet")}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 lg:grid-cols-3">
                      <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">
                          {t("agentConsole.blueprintAbcAreaList", "ABC floor areas")}
                        </p>
                        <div className="mt-3 space-y-2">
                          {(blueprintPreview.abc_floor_areas || []).slice(0, 5).map((area) => (
                            <div key={`abc-${area.code || area.name}`} className="rounded-[0.85rem] border border-[#13212c]/8 bg-white px-3 py-2">
                              <p className="text-sm font-semibold text-[#13212c]">{area.code || area.name || "—"}</p>
                              <p className="mt-1 text-xs leading-5 text-[#61717d]">
                                {[
                                  area.abc_class ? t("agentConsole.blueprintAbcClass", "ABC {value}", { value: area.abc_class }) : "",
                                  t("agentConsole.blueprintLocationCount", "{count} locations", { count: String(area.location_count || 0) }),
                                  dimensionSummary(area.dimensions),
                                ].filter(Boolean).join(" · ")}
                              </p>
                            </div>
                          ))}
                          {!(blueprintPreview.abc_floor_areas || []).length ? (
                            <p className="text-sm leading-6 text-[#61717d]">
                              {t("agentConsole.blueprintNoAbcAreas", "No ABC floor areas in this preview.")}
                            </p>
                          ) : null}
                        </div>
                      </div>

                      <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">
                          {t("agentConsole.blueprintRackAreaList", "Rack areas")}
                        </p>
                        <div className="mt-3 space-y-2">
                          {(blueprintPreview.rack_areas || []).slice(0, 5).map((area) => (
                            <div key={`rack-${area.code || area.name}`} className="rounded-[0.85rem] border border-[#13212c]/8 bg-white px-3 py-2">
                              <p className="text-sm font-semibold text-[#13212c]">{area.code || area.name || "—"}</p>
                              <p className="mt-1 text-xs leading-5 text-[#61717d]">
                                {[
                                  area.racks != null ? t("agentConsole.blueprintRacks", "{count} racks", { count: String(area.racks) }) : "",
                                  area.levels != null ? t("agentConsole.blueprintLevels", "{count} levels", { count: String(area.levels) }) : "",
                                  t("agentConsole.blueprintLocationCount", "{count} locations", { count: String(area.location_count || 0) }),
                                ].filter(Boolean).join(" · ")}
                              </p>
                            </div>
                          ))}
                          {!(blueprintPreview.rack_areas || []).length ? (
                            <p className="text-sm leading-6 text-[#61717d]">
                              {t("agentConsole.blueprintNoRackAreas", "No rack areas in this preview.")}
                            </p>
                          ) : null}
                        </div>
                      </div>

                      <div className="rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">
                          {t("agentConsole.blueprintDockDoorList", "Dock doors")}
                        </p>
                        <div className="mt-3 space-y-2">
                          {(blueprintPreview.dock_doors || []).slice(0, 6).map((door) => (
                            <div key={`dock-${door.code || door.door_number}`} className="rounded-[0.85rem] border border-[#ead39a] bg-white px-3 py-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-semibold text-[#13212c]">{door.code || door.door_number || "—"}</p>
                                <span className="rounded-full border border-[#ead39a] bg-[#fff8ea] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8a6520]">
                                  {t("agentConsole.blueprintDockDoorBadge", "External point")}
                                </span>
                              </div>
                              <p className="mt-1 text-xs leading-5 text-[#61717d]">
                                {t("agentConsole.blueprintDockDoorNotStorage", "Not a WMS storage location. WCS point: {point}", {
                                  point: door.wcs_mapping?.point_code || "—",
                                })}
                              </p>
                            </div>
                          ))}
                          {!(blueprintPreview.dock_doors || []).length ? (
                            <p className="text-sm leading-6 text-[#61717d]">
                              {t("agentConsole.blueprintNoDockDoors", "No dock doors in this preview.")}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 rounded-[1rem] border border-[#13212c]/10 bg-[#f9f6f0] p-4">
                      <p className="text-sm font-semibold text-[#13212c]">
                        {t("agentConsole.blueprintWcsNextTitle", "Next: confirm layout before WCS import")}
                      </p>
                      <div className="mt-3 grid gap-2 md:grid-cols-3">
                        {[
                          t("agentConsole.blueprintStepReview", "1. Confirm zones, racks, ABC floor areas, and dock-door placement."),
                          t("agentConsole.blueprintStepWriteLayout", "2. Apply the warehouse layout only after preview errors are resolved."),
                          t("agentConsole.blueprintStepValidateWcs", "3. Open Warehouse Planner to check mappings, then validate/import WCS points."),
                        ].map((step) => (
                          <p key={step} className="rounded-[0.85rem] border border-[#13212c]/8 bg-white px-3 py-2 text-xs leading-5 text-[#425461]">
                            {step}
                          </p>
                        ))}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-3">
                        <Link
                          to="/warehouse-planner"
                          className="inline-flex items-center rounded-full bg-[#13212c] px-4 py-2 text-sm font-semibold text-[#f4efe8] transition hover:bg-[#1a2d39]"
                        >
                          {t("agentConsole.openWarehousePlannerForWcs", "Open Warehouse Planner")}
                        </Link>
                        <span className="inline-flex items-center rounded-full border border-[#13212c]/10 bg-white px-4 py-2 text-sm font-semibold text-[#13212c]">
                          {t("agentConsole.blueprintValidateBeforeImport", "Validate before import")}
                        </span>
                      </div>
                    </div>

                    <details className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] px-4 py-3">
                      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">
                        {t("agentConsole.blueprintWcsDraftDetails", "WCS point mapping draft")}
                      </summary>
                      <pre className="mt-3 max-h-[260px] overflow-auto rounded-[1rem] bg-[#13212c] p-4 text-xs leading-6 text-[#dce7ee]">
                        {prettyJson(blueprintPreview.wcs_point_mapping_draft || [])}
                      </pre>
                    </details>
                  </div>
                ) : null}
                {resultCards.length && !hasModelAnswer && !isSetupResult ? (
                  <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white p-4">
                    <div className="space-y-3">
                      {resultCards.map((card) => (
                        <div
                          key={`${card.title}-${card.subtitle || ""}`}
                          className="rounded-[1rem] border border-[#13212c]/10 bg-[#f9f6f0] p-4"
                        >
                          <p className="text-sm font-semibold text-[#13212c]">{card.title}</p>
                          {card.subtitle ? (
                            <p className="mt-1 text-sm leading-6 text-[#5e6d79]">{card.subtitle}</p>
                          ) : null}
                          {card.chips?.length ? (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {card.chips.map((chip) => (
                                <span
                                  key={chip}
                                  className="rounded-full border border-[#d8e0e6] bg-white px-3 py-1.5 text-xs font-medium text-[#425461]"
                                >
                                  {chip}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          {card.note ? (
                            <p className="mt-2 text-sm leading-6 text-[#5e6d79]">{card.note}</p>
                          ) : null}
                          {card.href && card.ctaLabel ? (
                            <div className="mt-3">
                              <Link
                                to={card.href}
                                className="inline-flex items-center rounded-full border border-[#13212c]/10 bg-white px-3 py-2 text-xs font-semibold text-[#13212c] transition hover:bg-[#fffdfa]"
                              >
                                {card.ctaLabel}
                              </Link>
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                {!resultCards.length && resultEmptyText && !hasModelAnswer ? (
                  <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-[#f9f6f0] p-4">
                    <p className="text-sm leading-6 text-[#5e6d79]">{resultEmptyText}</p>
                  </div>
                ) : null}
                {importPreview ? (
                  <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">
                          {t("agentConsole.importReviewTitle", "File import review")}
                        </p>
                        <p className="mt-1 text-sm leading-6 text-[#5e6d79]">
                          {importMeta
                            ? t("agentConsole.importReviewBody", "This {kind} file passed the first detection pass. Review the field mapping before deciding to import it.", {
                                kind: importMeta.kindLabel,
                              })
                            : t("agentConsole.importReviewBodyFallback", "This file passed the first detection pass. Review the field mapping before deciding to import it.")}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {attachedImportName ? (
                          <span className="rounded-full border border-[#d8e0e6] bg-[#f7f4ee] px-3 py-1.5 text-xs font-medium text-[#425461]">
                            {attachedImportName}
                          </span>
                        ) : null}
                        {importMeta ? (
                          <span className="rounded-full border border-[#d8e0e6] bg-[#f7f4ee] px-3 py-1.5 text-xs font-medium text-[#425461]">
                            {importMeta.kindLabel}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {guidedImportSteps.map((step) => (
                        <span
                          key={step.key}
                          className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                            step.active
                              ? "border border-[#13212c]/15 bg-[#13212c] text-[#f4efe8]"
                              : step.complete
                                ? "border border-[#cbe3d5] bg-[#eef8f3] text-[#2f6f54]"
                                : "border border-[#d7dfe5] bg-[#fcfaf6] text-[#6b7a86]"
                          }`}
                        >
                          {step.title}
                        </span>
                      ))}
                    </div>
                    <div className="mt-4 rounded-[1rem] border border-[#13212c]/10 bg-[#f9f6f0] p-4 text-sm text-[#5e6d79]">
                      <p className="font-semibold text-[#13212c]">
                        {t("agentConsole.previewSummaryGeneric", "Previewing {rows} rows, with {missing} required fields still unmapped.", {
                          rows: String(importPreview.total_rows),
                          missing: String(importPreview.missing_required.length),
                        })}
                      </p>
                      {importPreview.missing_required.length === 0 ? (
                        <p className="mt-2 text-[#2f6f54]">
                          {t("agentConsole.mappingReady", "All required fields are mapped. You can move on to confirm the import.")}
                        </p>
                      ) : null}
                      {needsImportConfirmation ? (
                        <p className="mt-2 text-[#8f4b2c]">
                          {t("agentConsole.confirmationNeeded", "This workspace requires confirmation for changes. Review the preview, then press Confirm import.")}
                        </p>
                      ) : null}
                    </div>
                    <details className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] px-4 py-3">
                      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">
                        {t("agentConsole.mappingDetails", "Field mapping")}
                      </summary>
                      <div className="mt-4 grid gap-4 md:grid-cols-2">
                        {importPreview.required_fields.concat(importPreview.optional_fields).map((field) => (
                          <label key={field} className="text-sm text-[#485864]">
                            <span className="mb-1 block font-medium text-[#13212c]">{field}</span>
                            <select
                              value={mapping[field] || ""}
                              onChange={(e) => setMapping((prev) => ({ ...prev, [field]: e.target.value }))}
                              className="w-full rounded-[1rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm text-[#13212c]"
                            >
                              <option value="">{t("agentConsole.chooseHeader", "Choose a column")}</option>
                              {importPreview.headers.map((header) => (
                                <option key={header} value={header}>
                                  {header}
                                </option>
                              ))}
                            </select>
                          </label>
                        ))}
                      </div>
                    </details>
                    {importError ? (
                      <p className="mt-3 rounded-2xl border border-[#e5c7b8] bg-[#fff2ea] px-4 py-3 text-sm text-[#8f4b2c]">
                        {importError}
                      </p>
                    ) : null}
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={() => previewMutation.mutate()}
                        disabled={!settingsQuery.data?.enabled || !importMeta || !enabledTools.has(importMeta.previewTool) || !csvText.trim() || previewMutation.isPending}
                        className="rounded-full border border-[#13212c]/10 bg-white px-5 py-3 text-sm font-semibold text-[#13212c] transition hover:bg-[#fffdfa] disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        {previewMutation.isPending
                          ? t("agentConsole.previewing", "Previewing...")
                          : t("agentConsole.previewAgain", "Preview again")}
                      </button>
                      <button
                        type="button"
                        onClick={() => importMutation.mutate(needsImportConfirmation)}
                        disabled={!settingsQuery.data?.enabled || !importMeta || !enabledTools.has(importMeta.importTool) || !importPreview || importMutation.isPending}
                        className="rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        {importMutation.isPending
                          ? t("agentConsole.importing", "Importing...")
                          : needsImportConfirmation
                            ? t("agentConsole.confirmImport", "Confirm import")
                          : t("agentConsole.importMappedGeneric", "Start import")}
                      </button>
                      <button
                        type="button"
                        onClick={clearAttachment}
                        className="rounded-full border border-[#13212c]/10 bg-[#f7f4ee] px-5 py-3 text-sm font-semibold text-[#13212c] transition hover:bg-[#efebe3]"
                      >
                        {t("agentConsole.clearImportDraft", "Clear this file")}
                      </button>
                    </div>
                    <details className="mt-4 rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] px-4 py-3">
                      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">
                        {t("agentConsole.previewData", "Preview data")}
                      </summary>
                      <pre className="mt-3 max-h-[260px] overflow-auto rounded-[1rem] bg-[#13212c] p-4 text-xs leading-6 text-[#dce7ee]">
                        {prettyJson(importPreview.mapped_preview)}
                      </pre>
                    </details>
                  </div>
                ) : null}
                {typeof result.result?.answer === "string" && result.result.answer.trim() ? (
                  <div className="rounded-[1.2rem] border border-[#13212c]/10 bg-white p-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">
                          {t("agentConsole.modelAnswer", "Model answer")}
                        </p>
                        <p className="mt-1 text-xs leading-6 text-[#6b7a86]">
                          {resultSummary[0] ||
                            t(
                              "agentConsole.modelAnswerBody",
                              "The model has already converted the result into a short operating readout. You can copy the summary or the full explanation.",
                            )}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            handleCopy(
                              resultSummary.join("\n"),
                              t("agentConsole.copySummarySuccess", "Summary copied."),
                            )
                          }
                          className="rounded-full border border-[#13212c]/10 bg-[#fcfaf6] px-3 py-1.5 text-xs font-medium text-[#425461] transition hover:bg-white"
                        >
                          {t("agentConsole.copySummary", "Copy summary")}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            handleCopy(
                              answerSections.map((section) => `${section.title}\n${section.body}`).join("\n\n"),
                              t("agentConsole.copyAnswerSuccess", "Full explanation copied."),
                            )
                          }
                          className="rounded-full border border-[#13212c]/10 bg-[#fcfaf6] px-3 py-1.5 text-xs font-medium text-[#425461] transition hover:bg-white"
                        >
                          {t("agentConsole.copyAnswer", "Copy full answer")}
                        </button>
                      </div>
                    </div>
                    {copyFeedback ? (
                      <p className="mt-2 rounded-[1rem] border border-[#d7dfe5] bg-[#f9f6f0] px-4 py-3 text-sm text-[#425461]">
                        {copyFeedback}
                      </p>
                    ) : null}
                    <div className="mt-3 space-y-2.5">
                      {answerSections[0] ? (
                        <div className="rounded-[1rem] bg-[#f9f6f0] px-4 py-3">
                          <p className="text-sm font-semibold text-[#13212c]">{answerSections[0].title}</p>
                          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[#425461]">{answerSections[0].body}</p>
                        </div>
                      ) : null}
                      {answerSections.slice(1).length ? (
                        <div className="space-y-2">
                          {answerSections.slice(1).map((section) => (
                            <div
                              key={`${section.title}-${section.body.slice(0, 20)}`}
                              className="rounded-[1rem] border border-[#13212c]/8 bg-white px-4 py-3"
                            >
                              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">{section.title}</p>
                              <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-[#425461]">{section.body}</p>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                <details className="rounded-[1rem] border border-[#13212c]/8 bg-[#fcfaf6] px-4 py-2.5 text-[#425461]">
                  <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.14em] text-[#7b8995]">
                    {t("agentConsole.responseDetails", "View technical details")}
                  </summary>
                  <div className="mt-3 space-y-3">
                    <p className="text-xs text-[#6b7a86]">
                      {t("agentConsole.auditLine", "Logged at {time}", { time: result.audit_logged_at })}
                    </p>
                    <pre className="max-h-[320px] overflow-auto rounded-[0.9rem] bg-[#13212c] p-4 text-xs leading-6 text-[#dce7ee]">
                      {prettyJson(result.result)}
                    </pre>
                  </div>
                </details>
              </div>
            ) : (
              <div className="flex min-h-full items-center justify-center py-16">
                <div className="max-w-xl text-center">
                  <p className="text-lg font-semibold text-[#13212c]">
                    {error
                      ? t("agentConsole.chatErrorTitle", "That request did not come back")
                      : t("agentConsole.chatEmptyTitle", "Start by asking the AI")}
                  </p>
                  <p className="mt-3 text-sm leading-7 text-[#5e6d79]">
                    {error ||
                      t(
                        "agentConsole.chatEmptyBody",
                        "Type a question, or attach a CSV for the AI to preview.",
                      )}
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="shrink-0 border-t border-[#13212c]/8 bg-[#f7f4ee] px-5 py-4">
            <div className="rounded-[1.1rem] border border-[#13212c]/10 bg-white p-3 shadow-[0_6px_18px_rgba(19,33,44,0.04)]">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => void handleAttachedFile(e.target.files?.[0] || null)}
              />
              <textarea
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                rows={4}
                placeholder={t("agentConsole.inventorySearchPlaceholder", "Type a question, or attach an inventory / receiving / shipping CSV for the AI to preview")}
                className="min-h-[7.5rem] w-full resize-none rounded-[0.9rem] border border-[#d7dfe5] bg-white px-4 py-3 text-sm leading-7 text-[#13212c] outline-none"
              />
              {attachedImportName ? (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-[#d8e0e6] bg-[#f7f4ee] px-3 py-1.5 text-xs font-medium text-[#425461]">
                    {attachedImportName}
                  </span>
                  <span className="rounded-full border border-[#d8e0e6] bg-[#f7f4ee] px-3 py-1.5 text-xs font-medium text-[#425461]">
                    {importMeta?.kindLabel || t("agentConsole.importKindUnknownShort", "Not detected yet")}
                  </span>
                  <button
                    type="button"
                    onClick={clearAttachment}
                    className="rounded-full border border-[#13212c]/10 bg-white px-3 py-1.5 text-xs font-semibold text-[#13212c] transition hover:bg-[#fffdfa]"
                  >
                    {t("agentConsole.removeAttachment", "Remove file")}
                  </button>
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={runMutation.isPending || previewMutation.isPending || importMutation.isPending}
                  className="hidden rounded-full border border-[#13212c]/10 bg-white px-3.5 py-2 text-sm font-medium text-[#425461] transition hover:bg-[#fffdfa] disabled:cursor-not-allowed disabled:opacity-45 md:inline-flex"
                  data-testid="agent-console-desktop-attach-csv"
                >
                  {t("agentConsole.attachCsv", "Attach CSV")}
                </button>
                <button
                  type="button"
                  onClick={() => runAction("setup.progress", {})}
                  disabled={!settingsQuery.data?.enabled || !enabledTools.has("setup.progress") || runMutation.isPending}
                  className="rounded-full border border-[#13212c]/10 bg-[#fcfaf6] px-3.5 py-2 text-sm font-medium text-[#425461] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {runMutation.isPending && selectedTool === "setup.progress"
                    ? t("agentConsole.running", "Running...")
                    : t("agentConsole.systemCheck", "System status check")}
                </button>
                <button
                  type="button"
                  onClick={submitPrompt}
                  disabled={
                    !settingsQuery.data?.enabled ||
                    (csvText.trim()
                      ? !importMeta || !enabledTools.has(importMeta.previewTool) || previewMutation.isPending
                      : !routedPromptAction || runMutation.isPending)
                  }
                  className="ml-auto rounded-full bg-[#13212c] px-4 py-2 text-sm font-semibold text-[#f4efe8] transition hover:bg-[#1a2d39] disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {csvText.trim()
                    ? previewMutation.isPending
                      ? t("agentConsole.previewing", "Previewing...")
                      : t("agentConsole.sendFileForPreview", "Send file to AI")
                    : runMutation.isPending &&
                        (selectedTool === "inventory.search" || selectedTool === "inventory.explain")
                      ? t("agentConsole.running", "Running...")
                      : t("agentConsole.sendPrompt", "Send to AI")}
                </button>
              </div>
              <p
                className="mt-2 rounded-[0.9rem] border border-[#13212c]/8 bg-[#fcfaf6] px-3 py-2 text-xs leading-5 text-[#61717d] md:hidden"
                data-testid="agent-console-mobile-import-boundary"
              >
                {t(
                  "agentConsole.mobileImportBoundary",
                  "CSV upload and final import are desktop-preferred. On phone, use read tools and review previews from already prepared work.",
                )}
              </p>
            </div>

            {runMutation.isPending && selectedTool === "inventory.explain" ? (
              <p className="mt-2 text-sm leading-6 text-[#5e6d79]">
                {t(
                  "agentConsole.explainPendingHint",
                  "The model is reviewing the current inventory picture. This explanation usually returns in 10-20 seconds.",
                )}
              </p>
            ) : null}
            {csvText.trim() && !importPreview ? (
              <p className="mt-2 text-sm leading-6 text-[#5e6d79]">
                {importMeta
                  ? t("agentConsole.fileReadyHint", "This {kind} file is ready. Press Send file to AI to run the preview and field detection.", {
                      kind: importMeta.kindLabel,
                    })
                  : t("agentConsole.fileUnknownHint", "The file is attached, but its type could not be detected yet. Check the file name or column headers.")}
              </p>
            ) : null}

            <div className="mt-2.5">
              <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.16em] text-[#8a98a4]">
                {t("agentConsole.promptSuggestions", "Try these prompts")}
              </p>
              <div className="flex flex-wrap gap-2">
                {promptShortcuts.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    disabled={!enabledTools.has(item.tool_name) || runMutation.isPending}
                    onClick={() => {
                      if (item.tool_name === "inventory.search" && !normalizeInventoryQuery(searchQuery)) return;
                      runAction(item.tool_name, item.args || {});
                    }}
                    className="rounded-full border border-[#13212c]/10 bg-[#fcfaf6] px-3 py-1.5 text-xs font-medium text-[#425461] transition hover:border-[#13212c]/20 hover:bg-white disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    {t(item.labelKey, item.labelFallback)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        <details
          className="rounded-[1rem] border border-[#13212c]/8 bg-white px-5 py-4 shadow-[0_10px_24px_rgba(19,33,44,0.05)] md:hidden"
          data-testid="agent-console-mobile-tool-policy"
        >
          <summary className="cursor-pointer list-none">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("agentConsole.mobileToolPolicyTitle", "Phone tool boundary")}</p>
                <p className="mt-1 text-sm text-[#61717d]">
                  {t("agentConsole.mobileToolPolicySummary", "Only low-risk read and preview tools belong in the phone path. Writes and permission/billing changes stay desktop-preferred.")}
                </p>
              </div>
              <span className="rounded-full border border-[#d7dfe5] bg-[#f7f4ee] px-3 py-1 text-xs font-semibold text-[#425461]">
                {t("agentConsole.expandHint", "Expand")}
              </span>
            </div>
          </summary>
          <div className="mt-4 space-y-3">
            {groupedMobileToolCatalog.map((group) => (
              <div key={group.key} className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-[#13212c]">{group.title}</p>
                    <p className="mt-1 text-sm leading-6 text-[#5e6d79]">{group.body}</p>
                  </div>
                  <span className="rounded-full border border-[#d8e0e6] bg-white px-2.5 py-1 text-xs font-semibold text-[#425461]">
                    {t("agentConsole.groupCount", "{count} tools", { count: String(group.tools.length) })}
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  {group.tools.map((tool) => (
                    <div
                      key={tool.key}
                      className="rounded-[0.9rem] border border-[#13212c]/8 bg-white px-3 py-3"
                      data-mobile-tool-policy={mobileToolPolicy(tool)}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 text-sm font-medium text-[#13212c]">{toolLabel(tool.key, t)}</p>
                          <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${riskTone(tool.risk)}`}>
                            {tool.risk}
                          </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>

        <details
          className="hidden rounded-[1rem] border border-[#13212c]/8 bg-white px-5 py-4 shadow-[0_10px_24px_rgba(19,33,44,0.05)] md:block"
          data-testid="agent-console-desktop-tool-catalog"
        >
          <summary className="cursor-pointer list-none">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-[#13212c]">{t("agentConsole.moreTitle", "More capabilities and boundaries")}</p>
                <p className="mt-1 text-sm text-[#61717d]">
                  {t("agentConsole.moreSummary", "Expand when needed to see covered modules, available tools, and the governed import flow.")}
                </p>
              </div>
              <span className="rounded-full border border-[#d7dfe5] bg-[#f7f4ee] px-3 py-1 text-xs font-semibold text-[#425461]">
                {t("agentConsole.expandHint", "Expand")}
              </span>
            </div>
          </summary>
          <div className="mt-4 space-y-5">
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">
                {t("agentConsole.coverageTitle", "Modules this AI console can connect")}
              </p>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                  <p className="text-sm font-semibold text-[#13212c]">{t("agentConsole.coverageOps", "Operations: 7 modules")}</p>
                  <p className="mt-2 text-sm leading-6 text-[#5e6d79]">
                    {t("agentConsole.coverageOpsBody", "Dashboard, receiving, putaway, inventory, picking, shipping, and billing.")}
                  </p>
                </div>
                <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                  <p className="text-sm font-semibold text-[#13212c]">{t("agentConsole.coverageMaster", "Master data: 5 modules")}</p>
                  <p className="mt-2 text-sm leading-6 text-[#5e6d79]">
                    {t("agentConsole.coverageMasterBody", "Warehouses, clients, SKUs, users, and billing / AI settings.")}
                  </p>
                </div>
                <div className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                  <p className="text-sm font-semibold text-[#13212c]">{t("agentConsole.coveragePlanning", "Planning and imports: 2 modules")}</p>
                  <p className="mt-2 text-sm leading-6 text-[#5e6d79]">
                    {t("agentConsole.coveragePlanningBody", "Warehouse planner and the document import center.")}
                  </p>
                </div>
              </div>
            </div>

            {visibleActions.length ? (
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">
                  {t("agentConsole.starterTitle", "Run the first batch of safe tools")}
                </p>
                <div className="grid gap-2 lg:grid-cols-2">
                  {visibleActions.map((action) => {
                    const allowed = enabledTools.has(action.tool_name);
                    return (
                      <button
                        key={action.tool_name}
                        type="button"
                        disabled={!allowed || runMutation.isPending}
                        onClick={() =>
                          runAction(action.tool_name, {
                            ...action.args,
                            ...(action.tool_name === "inventory.search"
                              ? { query: normalizeInventoryQuery(searchQuery) }
                              : {}),
                            ...(action.tool_name === "inventory.search" || action.tool_name === "inventory.explain"
                              ? { language }
                              : {}),
                          })
                        }
                        className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f7f4ee] px-4 py-3 text-left transition hover:border-[#13212c]/20 hover:bg-[#fffdfa] disabled:cursor-not-allowed disabled:opacity-45"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-semibold text-[#13212c]">
                            {t(action.titleKey, action.titleFallback)}
                          </p>
                          <span className="rounded-full border border-[#13212c]/10 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-[#6d7d88]">
                            {allowed
                              ? t("agentConsole.allowed", "Allowed")
                              : t("agentConsole.notAllowed", "Not enabled")}
                          </span>
                        </div>
                        <p className="mt-1 text-sm leading-6 text-[#5e6d79]">
                          {t(action.bodyKey, action.bodyFallback)}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            <div className="space-y-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7e8d98]">
                  {t("agentConsole.guardrailTitle", "Keep the AI assistant inside clear, auditable boundaries")}
                </p>
                <p className="mt-1 text-sm text-[#61717d]">
                  {t("agentConsole.guardrailSummary", "Currently {low} low-risk, {medium} medium-risk, and {high} high-risk tools are allowed.", {
                    low: String(toolRiskStats.low),
                    medium: String(toolRiskStats.medium),
                    high: String(toolRiskStats.high),
                  })}
                </p>
              </div>
              <div className="grid gap-3">
                {groupedToolCatalog.map((group) => (
                  <div key={group.key} className="rounded-[0.95rem] border border-[#13212c]/8 bg-[#f7f4ee] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[#13212c]">{group.title}</p>
                        <p className="mt-1 text-sm leading-6 text-[#5e6d79]">{group.body}</p>
                      </div>
                      <span className="rounded-full border border-[#d8e0e6] bg-white px-2.5 py-1 text-xs font-semibold text-[#425461]">
                        {t("agentConsole.groupCount", "{count} tools", { count: String(group.tools.length) })}
                      </span>
                    </div>
                    <div className="mt-4 space-y-3">
                      {group.tools.map((tool) => (
                        <div
                          key={tool.key}
                          className="flex items-center justify-between gap-3 rounded-[0.9rem] border border-[#13212c]/8 bg-white px-4 py-3"
                        >
                          <div>
                            <p className="text-sm font-medium text-[#13212c]">{toolLabel(tool.key, t)}</p>
                            <p className="mt-1 text-xs uppercase tracking-[0.12em] text-[#7b8995]">
                              {TOOL_GOVERNANCE[tool.key]?.confirmation === "none"
                                ? t("agentConsole.confirmationNone", "No confirmation")
                                : TOOL_GOVERNANCE[tool.key]?.confirmation === "strong"
                                  ? t("agentConsole.confirmationStrong", "Strong confirmation")
                                  : t("agentConsole.confirmationStandard", "Confirmation required")}
                            </p>
                            <details className="mt-1">
                              <summary className="cursor-pointer text-xs text-[#6b7a86]">
                                {t("agent.toolTechnical", "View technical key")}
                              </summary>
                              <p className="mt-1 text-xs text-[#6b7a86]">{tool.key}</p>
                            </details>
                          </div>
                          <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${riskTone(tool.risk)}`}>
                            {tool.risk}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </details>
      </div>
      ) : null}
    </div>
  );
}
