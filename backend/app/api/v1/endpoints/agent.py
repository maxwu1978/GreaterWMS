"""Tenant-scoped BYO model agent settings and first-pass tool execution."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.orders import (
    OPTIONAL_OUTBOUND_FIELDS,
    OUTBOUND_IMPORT_ALIASES,
    REQUIRED_OUTBOUND_FIELDS,
    _create_outbound_order,
)
from app.api.v1.endpoints.receiving import (
    INBOUND_IMPORT_ALIASES,
    OPTIONAL_INBOUND_FIELDS,
    REQUIRED_INBOUND_FIELDS,
    _build_inbound_import_payloads,
)
from app.core.database import get_db_session
from app.core.deps import get_current_user, require_permission
from app.core.security import (
    TokenPayload,
    UserPermission,
    UserRole,
    has_permission,
    normalize_permissions,
)
from app.models.agent_evidence import AgentEvidence
from app.models.billing import RateCard
from app.models.client import Client
from app.models.inventory import SKU, Inventory
from app.models.order import InboundOrder, OutboundOrder
from app.models.tenant import Tenant, User
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.agent_evidence_service import AgentEvidenceService
from app.services.agent_model_service import AgentModelService
from app.services.agent_team_service import AgentTeamService
from app.services.csv_import import load_csv_rows, parse_mapping, suggest_mapping
from app.services.idempotency_service import IdempotencyService
from app.services.pack_list_service import PackListService
from app.services.receiving_service import ReceivingService
from app.services.setup_wizard_service import SetupWizardService
from app.services.warehouse_blueprint_service import (
    AGV_PLANNING_STANDARD_DOC,
    _agent_planner_zone_modes_from_address,
    _blueprint_agv_planning,
    _blueprint_agv_planning_validation,
    _blueprint_area_summaries,
    _blueprint_dock_doors,
    _blueprint_station_wcs_mapping,
    _blueprint_string,
    _blueprint_validation,
    _blueprint_wcs_mapping_draft,
    _blueprint_wcs_point_mapping,
    _decimal_or_none,
    _generate_blueprint_locations,
    _location_blueprint_metadata,
    _normalize_blueprint_zone,
    _zone_blueprint_metadata,
)

router = APIRouter()


TOOL_CATALOG = [
    {"key": "settings.agent.get", "risk": "low"},
    {"key": "settings.receiving_codes.get", "risk": "low"},
    {"key": "settings.receiving_labels.get", "risk": "low"},
    {"key": "settings.users.list", "risk": "low"},
    {"key": "settings.users.get", "risk": "low"},
    {"key": "settings.permissions.explain", "risk": "low"},
    {"key": "settings.client_profile.get", "risk": "low"},
    {"key": "settings.billing.explain", "risk": "low"},
    {"key": "settings.warehouse_locations.list", "risk": "low"},
    {"key": "settings.warehouse.get", "risk": "low"},
    {"key": "settings.rate_card.get", "risk": "low"},
    {"key": "settings.receiving_codes.preview", "risk": "medium"},
    {"key": "settings.receiving_labels.preview", "risk": "medium"},
    {"key": "settings.client_profile.preview", "risk": "medium"},
    {"key": "settings.sku.preview", "risk": "medium"},
    {"key": "settings.warehouse_location.preview", "risk": "medium"},
    {"key": "warehouse.blueprint.preview", "risk": "medium"},
    {"key": "settings.billing_rate_card.preview", "risk": "medium"},
    {"key": "inventory.search", "risk": "low"},
    {"key": "inventory.explain", "risk": "low"},
    {"key": "clients.list", "risk": "low"},
    {"key": "clients.get", "risk": "low"},
    {"key": "skus.list", "risk": "low"},
    {"key": "warehouses.list", "risk": "low"},
    {"key": "orders.inbound.list", "risk": "low"},
    {"key": "orders.outbound.list", "risk": "low"},
    {"key": "setup.progress", "risk": "low"},
    {"key": "billing.rate_cards.list", "risk": "low"},
    {"key": "receiving.inbound.preview_import", "risk": "medium"},
    {"key": "receiving.inbound.import_with_mapping", "risk": "medium"},
    {"key": "receiving.inbound.preview_pack_list", "risk": "medium"},
    {"key": "receiving.inbound.import_pack_list", "risk": "medium"},
    {"key": "orders.outbound.preview_import", "risk": "medium"},
    {"key": "orders.outbound.import_with_mapping", "risk": "medium"},
    {"key": "migration.inventory.preview", "risk": "medium"},
    {"key": "migration.inventory.import", "risk": "medium"},
    {"key": "clients.create", "risk": "medium"},
    {"key": "skus.create", "risk": "medium"},
    {"key": "receiving.inbound.create", "risk": "medium"},
    {"key": "users.create", "risk": "high"},
    {"key": "users.update_permissions", "risk": "high"},
]

DEFAULT_ALLOWED_TOOLS = [
    "settings.agent.get",
    "settings.receiving_codes.get",
    "settings.receiving_labels.get",
    "settings.users.list",
    "settings.users.get",
    "settings.permissions.explain",
    "settings.client_profile.get",
    "settings.billing.explain",
    "settings.warehouse_locations.list",
    "settings.warehouse.get",
    "settings.rate_card.get",
    "settings.receiving_codes.preview",
    "settings.receiving_labels.preview",
    "settings.client_profile.preview",
    "settings.sku.preview",
    "settings.warehouse_location.preview",
    "warehouse.blueprint.preview",
    "settings.billing_rate_card.preview",
    "inventory.search",
    "inventory.explain",
    "clients.list",
    "clients.get",
    "skus.list",
    "warehouses.list",
    "orders.inbound.list",
    "orders.outbound.list",
    "setup.progress",
    "billing.rate_cards.list",
    "receiving.inbound.preview_import",
    "receiving.inbound.preview_pack_list",
    "orders.outbound.preview_import",
    "migration.inventory.preview",
]

DIRECT_IMPORT_WRITE_TOOLS = {
    "receiving.inbound.import_with_mapping",
    "receiving.inbound.import_pack_list",
    "orders.outbound.import_with_mapping",
    "migration.inventory.import",
}

IMPORT_WRITE_CONFIG = {
    "inbound": {
        "preview_tool": "receiving.inbound.preview_import",
        "action": "receiving.inbound.import_with_mapping",
        "entity_type": "inbound_import",
        "token_prefix": "imp-inbound",
        "permission": UserPermission.INBOUND_ORDERS_IMPORT.value,
        "preview_endpoint": "POST /api/v1/agent/imports/inbound/preview",
        "agent_endpoint": "POST /api/v1/agent/imports/inbound/agent",
    },
    "pack-list": {
        "preview_tool": "receiving.inbound.preview_pack_list",
        "action": "receiving.inbound.import_pack_list",
        "entity_type": "pack_list_import",
        "token_prefix": "imp-pack-list",
        "permission": UserPermission.INBOUND_ORDERS_IMPORT.value,
        "preview_endpoint": "POST /api/v1/agent/packlists/preview",
        "agent_endpoint": "POST /api/v1/agent/packlists/agent",
    },
    "outbound": {
        "preview_tool": "orders.outbound.preview_import",
        "action": "orders.outbound.import_with_mapping",
        "entity_type": "outbound_import",
        "token_prefix": "imp-outbound",
        "permission": UserPermission.OUTBOUND_ORDERS_MANAGE.value,
        "preview_endpoint": "POST /api/v1/agent/imports/outbound/preview",
        "agent_endpoint": "POST /api/v1/agent/imports/outbound/agent",
    },
    "inventory": {
        "preview_tool": "migration.inventory.preview",
        "action": "migration.inventory.import",
        "entity_type": "inventory_import",
        "token_prefix": "imp-inventory",
        "permission": UserPermission.MASTER_DATA_MANAGE.value,
        "preview_endpoint": "POST /api/v1/agent/imports/inventory/preview",
        "agent_endpoint": "POST /api/v1/agent/imports/inventory/agent",
    },
}

INVENTORY_REQUIRED_FIELDS = ["sku_code", "location_barcode", "quantity"]
INVENTORY_OPTIONAL_FIELDS = ["client_id", "lot_number"]
INVENTORY_IMPORT_ALIASES = {
    "sku_code": ["sku_code", "sku", "item", "item_code", "product_code"],
    "location_barcode": ["location_barcode", "location", "bin", "bin_code", "slot", "barcode"],
    "quantity": ["quantity", "qty", "on_hand", "stock_qty", "count"],
    "client_id": ["client_id", "client", "client_code", "customer_code"],
    "lot_number": ["lot_number", "lot", "batch", "batch_number"],
}

RECEIVING_CODE_DEFAULTS = {
    "prefix": "RCV",
    "separator": "-",
    "include_order_number": True,
    "sequence_padding": 3,
    "uppercase": True,
}

RECEIVING_LABEL_DEFAULTS = {
    "fields": ["order_number", "sku_code", "expected_qty", "tracking_number"],
    "show_field_labels": True,
}

RECEIVING_LABEL_FIELDS = [
    "order_number",
    "package_number",
    "package_type",
    "reference_number",
    "sku_code",
    "sku_name",
    "expected_qty",
    "received_qty",
    "tracking_number",
    "carton_mark",
    "customer_barcode",
    "package_count",
    "pallet_count",
    "weight",
    "dimensions",
    "rent_free_days",
    "receiving_note",
]

SENSITIVE_SETTING_TERMS = ("api_key", "key", "password", "secret", "token", "webhook")

CLIENT_PROFILE_WRITE_FIELDS = {
    "name",
    "code",
    "contact_email",
    "contact_phone",
    "billing_enabled",
    "portal_access",
    "is_active",
    "address",
    "notes",
}
SKU_WRITE_FIELDS = {
    "sku_code",
    "barcode",
    "name",
    "description",
    "weight_kg",
    "length_cm",
    "width_cm",
    "height_cm",
    "requires_lot",
    "requires_expiry",
    "is_hazmat",
    "units_per_case",
    "cases_per_pallet",
}
WAREHOUSE_LOCATION_WRITE_FIELDS = {
    "barcode",
    "aisle",
    "rack",
    "level",
    "position",
    "location_type",
    "current_status",
    "max_weight_kg",
    "max_volume_m3",
    "pick_sequence",
    "is_agv_accessible",
    "dimensions",
    "layout_metadata",
    "drawing_source",
    "wcs_point_metadata",
}
WAREHOUSE_BLUEPRINT_ACTION = "warehouse.blueprint.import"
WAREHOUSE_BLUEPRINT_PERMISSION = UserPermission.MASTER_DATA_MANAGE.value

SETTINGS_WRITE_CONFIG = {
    "receiving-codes": {
        "preview_tool": "settings.receiving_codes.preview",
        "action": "settings.receiving_codes.update",
        "entity_type": "receiving_code_settings",
        "entity_id_arg": None,
        "token_prefix": "set-rcv-code",
        "permission": UserPermission.USERS_MANAGE.value,
    },
    "receiving-labels": {
        "preview_tool": "settings.receiving_labels.preview",
        "action": "settings.receiving_labels.update",
        "entity_type": "receiving_label_settings",
        "entity_id_arg": None,
        "token_prefix": "set-rcv-label",
        "permission": UserPermission.USERS_MANAGE.value,
    },
    "client-profile": {
        "preview_tool": "settings.client_profile.preview",
        "action": "settings.client_profile.update",
        "entity_type": "client",
        "entity_id_arg": "client_id",
        "token_prefix": "set-client",
        "permission": UserPermission.MASTER_DATA_MANAGE.value,
    },
    "sku": {
        "preview_tool": "settings.sku.preview",
        "action": "settings.sku.update",
        "entity_type": "sku",
        "entity_id_arg": "sku_id",
        "token_prefix": "set-sku",
        "permission": UserPermission.MASTER_DATA_MANAGE.value,
    },
    "warehouse-location": {
        "preview_tool": "settings.warehouse_location.preview",
        "action": "settings.warehouse_location.update",
        "entity_type": "location",
        "entity_id_arg": "location_id",
        "token_prefix": "set-location",
        "permission": UserPermission.MASTER_DATA_MANAGE.value,
    },
}


class AgentSettingsUpdate(BaseModel):
    enabled: bool = False
    provider_type: str | None = None
    provider_label: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    region: str | None = None
    api_key: str | None = None
    allow_data_logging: bool = False
    allow_model_training: bool = False
    requires_human_confirmation_for_writes: bool = True
    allowed_tools: list[str] = []


class AgentSettingsResponse(BaseModel):
    enabled: bool
    provider_type: str | None
    provider_label: str | None
    base_url: str | None
    model_name: str | None
    region: str | None
    has_api_key: bool
    allow_data_logging: bool
    allow_model_training: bool
    requires_human_confirmation_for_writes: bool
    allowed_tools: list[str]
    tool_catalog: list[dict]
    validation_status: str | None = None
    validation_message: str | None = None
    validation_checked_at: datetime | None = None


class AgentToolRunRequest(BaseModel):
    tool_name: str
    args: dict | None = None


class InventoryImportPreviewRequest(BaseModel):
    csv_text: str
    file_name: str = "agent-inventory.csv"
    mapping: dict[str, str] | None = None


class ImportPreviewRequest(InventoryImportPreviewRequest):
    pass


class ImportAgentRequest(ImportPreviewRequest):
    confirmation_token: str


class PackListImportPreviewRequest(BaseModel):
    source_text: str
    file_name: str = "pack-list.csv"
    mapping: dict[str, str] | None = None
    order_number: str | None = None
    client_code: str | None = None
    warehouse_code: str | None = None
    source_type: str = "customer_pack_list"
    note: str | None = None
    create_inbound_if_missing: bool = False


class PackListImportAgentRequest(PackListImportPreviewRequest):
    confirmation_token: str


class WarehouseBlueprintPreviewRequest(BaseModel):
    warehouse: dict | None = None
    warehouse_id: str | None = None
    zones: list[dict] = []
    layout: dict | None = None
    route_policy: dict | None = None
    route_nodes: list[dict] | None = None
    agv_paths: list[dict] | None = None
    stations: list[dict] | None = None
    safety_zones: list[dict] | None = None
    planning_standard: dict | None = None
    source_image_name: str | None = None
    notes: str | None = None


class WarehouseBlueprintAgentRequest(WarehouseBlueprintPreviewRequest):
    confirmation_token: str


class SettingsPreviewRequest(BaseModel):
    settings: dict | None = None
    changes: dict | None = None
    client_id: str | None = None
    sku_id: str | None = None
    location_id: str | None = None


class SettingsAgentRequest(SettingsPreviewRequest):
    confirmation_token: str


class AgentToolRunResponse(BaseModel):
    tool_name: str
    risk: str
    scope: dict
    result: dict | list
    audit_logged_at: datetime


class AgentTeamRunRequest(BaseModel):
    mode: str = "compare"
    task: str
    context: str | None = None
    agents: list[str] | None = None


class AgentTeamRunResponse(BaseModel):
    mode: str
    task: str
    agents: list[str]
    responses: list[dict]
    synthesis: str


def _normalize_allowed_tools(values: list[str] | None) -> list[str]:
    allowed = {item["key"] for item in TOOL_CATALOG}
    deduped: list[str] = []
    for value in values or DEFAULT_ALLOWED_TOOLS:
        if value in allowed and value not in deduped:
            deduped.append(value)
    return deduped


def _raw_agent_settings(tenant: Tenant) -> dict:
    settings = dict(tenant.settings or {})
    payload = dict(settings.get("agent_console") or {})
    payload.setdefault("enabled", False)
    payload.setdefault("provider_type", None)
    payload.setdefault("provider_label", None)
    payload.setdefault("base_url", None)
    payload.setdefault("model_name", None)
    payload.setdefault("region", None)
    payload.setdefault("allow_data_logging", False)
    payload.setdefault("allow_model_training", False)
    payload.setdefault("requires_human_confirmation_for_writes", True)
    payload["allowed_tools"] = _normalize_allowed_tools(payload.get("allowed_tools"))
    return payload


def _settings_payload(tenant: Tenant) -> dict:
    payload = dict(_raw_agent_settings(tenant))
    payload["has_api_key"] = bool(payload.get("api_key"))
    payload.pop("api_key", None)
    payload.setdefault("validation_status", None)
    payload.setdefault("validation_message", None)
    payload.setdefault("validation_checked_at", None)
    return payload


def _redact_settings(value):
    if isinstance(value, dict):
        return {
            key: "[redacted]" if any(term in key.lower() for term in SENSITIVE_SETTING_TERMS)
            else _redact_settings(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_settings(item) for item in value]
    return value


def _parse_mapping(mapping_json: str | dict[str, str] | None, headers: list[str]) -> dict[str, str]:
    return parse_mapping(
        mapping_json,
        headers,
        aliases=INBOUND_IMPORT_ALIASES,
        required_fields=REQUIRED_INBOUND_FIELDS,
        optional_fields=OPTIONAL_INBOUND_FIELDS,
    )


def _suggest_outbound_mapping(headers: list[str]) -> dict[str, str]:
    return suggest_mapping(headers, OUTBOUND_IMPORT_ALIASES)


def _parse_outbound_mapping(
    mapping_json: str | dict[str, str] | None, headers: list[str]
) -> dict[str, str]:
    return parse_mapping(
        mapping_json,
        headers,
        aliases=OUTBOUND_IMPORT_ALIASES,
        required_fields=REQUIRED_OUTBOUND_FIELDS,
        optional_fields=OPTIONAL_OUTBOUND_FIELDS,
    )


def _suggest_inventory_mapping(headers: list[str]) -> dict[str, str]:
    # Inventory import historically matched headers by simple lowercasing (no
    # punctuation normalization), so keep that normalizer.
    return suggest_mapping(
        headers, INVENTORY_IMPORT_ALIASES, normalize=lambda value: value.strip().lower()
    )


def _parse_inventory_mapping(
    mapping_json: dict[str, str] | None, headers: list[str]
) -> dict[str, str]:
    allowed_headers = set(headers)
    mapping = _suggest_inventory_mapping(headers)
    if mapping_json:
        mapping = {
            target_field: header_name
            for target_field, header_name in mapping_json.items()
            if isinstance(target_field, str)
            and isinstance(header_name, str)
            and header_name in allowed_headers
        }
    return mapping


async def _load_target_tenant(
    db: AsyncSession, current_user: TokenPayload, tenant_id: str | None = None
) -> Tenant:
    target_tenant_id = current_user.tenant_id
    if current_user.role == UserRole.PLATFORM_ADMIN and tenant_id:
        target_tenant_id = tenant_id
    if not target_tenant_id:
        raise HTTPException(status_code=400, detail="No tenant scope available")
    result = await db.execute(select(Tenant).where(Tenant.id == target_tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _tool_meta(tool_name: str) -> dict:
    for item in TOOL_CATALOG:
        if item["key"] == tool_name:
            return item
    raise HTTPException(status_code=404, detail=f"Unknown agent tool '{tool_name}'")


def _tool_permission(tool_name: str) -> str | None:
    mapping = {
        "settings.agent.get": UserPermission.USERS_MANAGE.value,
        "settings.receiving_codes.get": UserPermission.USERS_MANAGE.value,
        "settings.receiving_labels.get": UserPermission.USERS_MANAGE.value,
        "settings.users.list": UserPermission.USERS_MANAGE.value,
        "settings.users.get": UserPermission.USERS_MANAGE.value,
        "settings.permissions.explain": UserPermission.USERS_MANAGE.value,
        "settings.client_profile.get": UserPermission.MASTER_DATA_MANAGE.value,
        "settings.billing.explain": UserPermission.BILLING_MANAGE.value,
        "settings.warehouse_locations.list": UserPermission.MASTER_DATA_MANAGE.value,
        "settings.warehouse.get": UserPermission.MASTER_DATA_MANAGE.value,
        "settings.rate_card.get": UserPermission.BILLING_MANAGE.value,
        "settings.receiving_codes.preview": UserPermission.USERS_MANAGE.value,
        "settings.receiving_labels.preview": UserPermission.USERS_MANAGE.value,
        "settings.client_profile.preview": UserPermission.MASTER_DATA_MANAGE.value,
        "settings.sku.preview": UserPermission.MASTER_DATA_MANAGE.value,
        "settings.warehouse_location.preview": UserPermission.MASTER_DATA_MANAGE.value,
        "warehouse.blueprint.preview": UserPermission.MASTER_DATA_MANAGE.value,
        "settings.billing_rate_card.preview": UserPermission.BILLING_MANAGE.value,
        "inventory.search": UserPermission.MASTER_DATA_MANAGE.value,
        "inventory.explain": UserPermission.MASTER_DATA_MANAGE.value,
        "clients.list": UserPermission.MASTER_DATA_MANAGE.value,
        "clients.get": UserPermission.MASTER_DATA_MANAGE.value,
        "skus.list": UserPermission.MASTER_DATA_MANAGE.value,
        "warehouses.list": UserPermission.MASTER_DATA_MANAGE.value,
        "orders.inbound.list": UserPermission.INBOUND_ORDERS_MANAGE.value,
        "orders.outbound.list": UserPermission.OUTBOUND_ORDERS_MANAGE.value,
        "setup.progress": UserPermission.USERS_MANAGE.value,
        "billing.rate_cards.list": UserPermission.BILLING_MANAGE.value,
        "receiving.inbound.preview_import": UserPermission.INBOUND_ORDERS_IMPORT.value,
        "receiving.inbound.import_with_mapping": UserPermission.INBOUND_ORDERS_IMPORT.value,
        "receiving.inbound.preview_pack_list": UserPermission.INBOUND_ORDERS_IMPORT.value,
        "receiving.inbound.import_pack_list": UserPermission.INBOUND_ORDERS_IMPORT.value,
        "orders.outbound.preview_import": UserPermission.OUTBOUND_ORDERS_MANAGE.value,
        "orders.outbound.import_with_mapping": UserPermission.OUTBOUND_ORDERS_MANAGE.value,
        "migration.inventory.preview": UserPermission.MASTER_DATA_MANAGE.value,
        "migration.inventory.import": UserPermission.MASTER_DATA_MANAGE.value,
    }
    return mapping.get(tool_name)


def _ensure_agent_tool_access(tenant: Tenant, current_user: TokenPayload, tool_name: str) -> dict:
    tool = _tool_meta(tool_name)
    settings = _raw_agent_settings(tenant)
    if not settings.get("enabled"):
        raise HTTPException(status_code=400, detail="Agent console is disabled for this tenant")
    if tool_name not in settings.get("allowed_tools", []):
        raise HTTPException(
            status_code=403, detail=f"Tool '{tool_name}' is not enabled for this tenant"
        )

    required_permission = _tool_permission(tool_name)
    if required_permission and not has_permission(
        current_user.role, current_user.permissions, required_permission
    ):
        raise HTTPException(
            status_code=403, detail=f"You do not have permission to run '{tool_name}'"
        )
    return tool


def _can_access_agent_console(current_user: TokenPayload) -> bool:
    if current_user.role == UserRole.PLATFORM_ADMIN:
        return True
    relevant_permissions = [
        UserPermission.INBOUND_ORDERS_MANAGE.value,
        UserPermission.INBOUND_ORDERS_IMPORT.value,
        UserPermission.RECEIVING_EXECUTE.value,
        UserPermission.OUTBOUND_ORDERS_MANAGE.value,
        UserPermission.MASTER_DATA_MANAGE.value,
        UserPermission.BILLING_MANAGE.value,
        UserPermission.PLANNER_MANAGE.value,
        UserPermission.USERS_MANAGE.value,
    ]
    return any(
        has_permission(current_user.role, current_user.permissions, permission)
        for permission in relevant_permissions
    )


def _can_access_agent_team(current_user: TokenPayload) -> bool:
    return current_user.role == UserRole.PLATFORM_ADMIN


async def _tool_setup_progress(db: AsyncSession, current_user: TokenPayload) -> dict:
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.get_progress()


async def _tool_agent_settings_get(tenant: Tenant) -> dict:
    payload = _settings_payload(tenant)
    return {
        "enabled": payload.get("enabled", False),
        "provider_type": payload.get("provider_type"),
        "provider_label": payload.get("provider_label"),
        "base_url": payload.get("base_url"),
        "model_name": payload.get("model_name"),
        "region": payload.get("region"),
        "has_api_key": payload.get("has_api_key", False),
        "allow_data_logging": payload.get("allow_data_logging", False),
        "allow_model_training": payload.get("allow_model_training", False),
        "requires_human_confirmation_for_writes": payload.get(
            "requires_human_confirmation_for_writes", True
        ),
        "allowed_tools": payload.get("allowed_tools", []),
        "tool_catalog": TOOL_CATALOG,
        "validation_status": payload.get("validation_status"),
        "validation_message": payload.get("validation_message"),
        "validation_checked_at": payload.get("validation_checked_at"),
    }


def _compose_receiving_code_sample(settings_payload: dict) -> str:
    prefix = str(settings_payload.get("prefix") or "RCV").strip() or "RCV"
    separator = str(settings_payload.get("separator") if settings_payload.get("separator") is not None else "-")
    try:
        raw_padding = int(settings_payload.get("sequence_padding", 3))
    except (TypeError, ValueError):
        raw_padding = 3
    sequence_padding = max(1, min(raw_padding, 8))
    uppercase = bool(settings_payload.get("uppercase", True))
    order_number = "INB-20260416"
    cleaned_order = "".join(ch if ch.isalnum() else "-" for ch in order_number).strip("-")
    parts = [prefix, cleaned_order, f"{1:0{sequence_padding}d}"]
    if not bool(settings_payload.get("include_order_number", True)):
        parts = [prefix, f"{1:0{sequence_padding}d}"]
    code = separator.join(part for part in parts if part)
    return code.upper() if uppercase else code


async def _tool_receiving_codes_get(tenant: Tenant) -> dict:
    payload = {
        **RECEIVING_CODE_DEFAULTS,
        **dict((tenant.settings or {}).get("receiving_code_rules") or {}),
    }
    return {
        **payload,
        "sample_code": _compose_receiving_code_sample(payload),
    }


async def _tool_receiving_labels_get(tenant: Tenant) -> dict:
    payload = {
        **RECEIVING_LABEL_DEFAULTS,
        **dict((tenant.settings or {}).get("receiving_label_template") or {}),
    }
    allowed = set(RECEIVING_LABEL_FIELDS)
    fields = [field for field in payload.get("fields", []) if field in allowed]
    return {
        "fields": fields or RECEIVING_LABEL_DEFAULTS["fields"],
        "show_field_labels": bool(payload.get("show_field_labels", True)),
        "available_fields": RECEIVING_LABEL_FIELDS,
    }


async def _tool_users_list(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit", 20)), 50))
    query = (
        select(User, Tenant.name.label("tenant_name"))
        .outerjoin(Tenant, Tenant.id == User.tenant_id)
        .order_by(User.tenant_id, User.full_name, User.email)
        .limit(limit)
    )
    count_query = select(func.count(User.id))
    if current_user.role != UserRole.PLATFORM_ADMIN:
        query = query.where(User.tenant_id == current_user.tenant_id)
        count_query = count_query.where(User.tenant_id == current_user.tenant_id)
    rows = (await db.execute(query)).all()
    total = int((await db.execute(count_query)).scalar() or 0)
    items = [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "job_title": user.job_title,
            "permissions": normalize_permissions(user.role, user.permissions),
            "client_id": user.client_id,
            "tenant_id": user.tenant_id,
            "tenant_name": tenant_name,
            "is_active": user.is_active,
        }
        for user, tenant_name in rows
    ]
    return {"count": len(items), "total": total, "has_more": total > len(items), "items": items}


async def _tool_permissions_explain(current_user: TokenPayload) -> dict:
    role_defaults = {
        role.value: [
            permission.value
            for permission in UserPermission
            if has_permission(role, [], permission.value)
        ]
        for role in UserRole
    }
    return {
        "current_user": {
            "role": current_user.role.value,
            "permissions": current_user.permissions,
            "tenant_id": current_user.tenant_id,
            "client_id": current_user.client_id,
        },
        "available_permissions": [permission.value for permission in UserPermission],
        "role_defaults": role_defaults,
        "notes": [
            "Tenant admins can manage operational, master-data, billing, planner, and user settings.",
            "Operators are limited to floor execution permissions.",
            "Client viewers only receive portal.view and are scoped to a client.",
        ],
    }


async def _tool_client_profile_get(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit", 10)), 30))
    client_id = str(args.get("client_id", "") or "").strip()
    query_text = str(args.get("query", "") or "").strip()
    query = select(Client).where(Client.tenant_id == current_user.tenant_id).limit(limit)
    if client_id:
        query = query.where(Client.id == client_id)
    elif query_text:
        like = f"%{query_text}%"
        query = query.where(or_(Client.name.ilike(like), Client.code.ilike(like)))
    rows = (await db.execute(query.order_by(Client.name, Client.code))).scalars()
    items = [
        {
            "id": client.id,
            "name": client.name,
            "code": client.code,
            "contact_email": client.contact_email,
            "contact_phone": client.contact_phone,
            "billing_enabled": client.billing_enabled,
            "portal_access": client.portal_access,
            "is_active": client.is_active,
            "address": client.address,
            "notes": client.notes,
            "settings": _redact_settings(client.settings or {}),
        }
        for client in rows
    ]
    return {"count": len(items), "items": items}


async def _tool_billing_explain(db: AsyncSession, tenant: Tenant, current_user: TokenPayload) -> dict:
    rows = (
        await db.execute(
            select(Client, func.count(RateCard.id))
            .outerjoin(
                RateCard,
                (RateCard.client_id == Client.id)
                & (RateCard.tenant_id == current_user.tenant_id)
                & (RateCard.is_active == True),  # noqa: E712
            )
            .where(Client.tenant_id == current_user.tenant_id)
            .group_by(Client.id)
            .order_by(Client.name)
            .limit(50)
        )
    ).all()
    settings = tenant.settings or {}
    return {
        "business_mode": settings.get("business_mode", "3pl"),
        "tenant_billing_profile": _redact_settings(settings.get("billing_profile") or {}),
        "clients": [
            {
                "id": client.id,
                "name": client.name,
                "code": client.code,
                "billing_enabled": client.billing_enabled,
                "active_rate_cards": int(rate_count or 0),
                "billing_profile": _redact_settings(
                    dict((client.settings or {}).get("billing_profile") or {})
                ),
            }
            for client, rate_count in rows
        ],
        "notes": [
            "Formal invoices use tenant billing_profile as issuer data.",
            "Client billing_profile overrides bill-to and tax fields when present.",
            "Rate cards define storage, receiving, pick, shipping, and surcharge rules per client.",
        ],
    }


async def _tool_warehouse_locations_list(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    limit = max(1, min(int(args.get("limit", 25)), 500))
    warehouse_id = str(args.get("warehouse_id", "") or "").strip()
    query = (
        select(Location, Warehouse.code, Warehouse.name, Warehouse.address, Zone.code, Zone.name)
        .join(Warehouse, Warehouse.id == Location.warehouse_id)
        .join(Zone, Zone.id == Location.zone_id)
        .where(Location.tenant_id == current_user.tenant_id)
        .order_by(Warehouse.code, Zone.sequence, Location.pick_sequence, Location.barcode)
        .limit(limit)
    )
    if warehouse_id:
        query = query.where(Location.warehouse_id == warehouse_id)
    rows = (await db.execute(query)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": location.id,
                "barcode": location.barcode,
                "warehouse_code": warehouse_code,
                "warehouse_name": warehouse_name,
                "zone_code": zone_code,
                "zone_name": zone_name,
                "aisle": location.aisle,
                "rack": location.rack,
                "level": location.level,
                "position": location.position,
                "location_type": location.location_type,
                "current_status": location.current_status,
                "is_agv_accessible": location.is_agv_accessible,
                "pick_sequence": location.pick_sequence,
                "coordinate_x": float(location.coordinate_x)
                if location.coordinate_x is not None
                else None,
                "coordinate_y": float(location.coordinate_y)
                if location.coordinate_y is not None
                else None,
                "max_weight_kg": float(location.max_weight_kg)
                if location.max_weight_kg is not None
                else None,
                "max_volume_m3": float(location.max_volume_m3)
                if location.max_volume_m3 is not None
                else None,
                "dimensions": location.dimensions or {},
                "layout_metadata": location.layout_metadata or {},
                "drawing_source": location.drawing_source or {},
                "wcs_point_metadata": location.wcs_point_metadata or {},
                "blueprint_metadata": _location_blueprint_metadata(
                    warehouse_address, location.barcode
                ),
            }
            for (
                location,
                warehouse_code,
                warehouse_name,
                warehouse_address,
                zone_code,
                zone_name,
            ) in rows
        ],
    }


def _required_arg(args: dict, name: str) -> str:
    value = str(args.get(name, "") or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{name} is required")
    return value


def _dt(value) -> str | None:
    return value.isoformat() if value else None


def _num(value) -> float | None:
    return float(value) if value is not None else None


def _safe_user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "job_title": user.job_title,
        "permissions": normalize_permissions(user.role, user.permissions),
        "client_id": user.client_id,
        "tenant_id": user.tenant_id,
        "is_active": user.is_active,
        "is_email_verified": user.is_email_verified,
        "created_at": _dt(user.created_at),
        "updated_at": _dt(user.updated_at),
    }


async def _tool_user_get(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    user_id = _required_arg(args, "user_id")
    query = (
        select(User, Tenant.name.label("tenant_name"))
        .outerjoin(Tenant, Tenant.id == User.tenant_id)
        .where(User.id == user_id)
    )
    if current_user.role != UserRole.PLATFORM_ADMIN:
        query = query.where(User.tenant_id == current_user.tenant_id)
    row = (await db.execute(query)).first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    user, tenant_name = row
    return {**_safe_user_payload(user), "tenant_name": tenant_name}


async def _tool_warehouse_get(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    warehouse_id = _required_arg(args, "warehouse_id")
    warehouse = await db.scalar(
        select(Warehouse).where(
            Warehouse.id == warehouse_id, Warehouse.tenant_id == current_user.tenant_id
        )
    )
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    zone_rows = (
        await db.execute(
            select(Zone)
            .where(Zone.warehouse_id == warehouse.id, Zone.tenant_id == current_user.tenant_id)
            .order_by(Zone.sequence, Zone.code)
        )
    ).scalars()
    location_rows = (
        await db.execute(
            select(Location)
            .where(
                Location.warehouse_id == warehouse.id,
                Location.tenant_id == current_user.tenant_id,
            )
            .order_by(Location.pick_sequence, Location.barcode)
            .limit(100)
        )
    ).scalars()
    zones = [
        {
            "id": zone.id,
            "name": zone.name,
            "code": zone.code,
            "is_agv_zone": zone.is_agv_zone,
            "sequence": zone.sequence,
            "zone_type": zone.zone_type,
            "dimensions": zone.dimensions or {},
            "layout_metadata": zone.layout_metadata or {},
            "drawing_source": zone.drawing_source or {},
            "blueprint_metadata": _zone_blueprint_metadata(warehouse.address, zone.code),
        }
        for zone in zone_rows
    ]
    locations = [
        {
            "id": location.id,
            "zone_id": location.zone_id,
            "barcode": location.barcode,
            "location_type": location.location_type,
            "current_status": location.current_status,
            "pick_sequence": location.pick_sequence,
            "is_agv_accessible": location.is_agv_accessible,
            "dimensions": location.dimensions or {},
            "layout_metadata": location.layout_metadata or {},
            "drawing_source": location.drawing_source or {},
            "wcs_point_metadata": location.wcs_point_metadata or {},
            "blueprint_metadata": _location_blueprint_metadata(
                warehouse.address, location.barcode
            ),
        }
        for location in location_rows
    ]
    return {
        "id": warehouse.id,
        "name": warehouse.name,
        "code": warehouse.code,
        "timezone": warehouse.timezone,
        "is_active": warehouse.is_active,
        "address": _redact_settings(warehouse.address or {}),
        "zones": zones,
        "locations": locations,
        "location_count": len(locations),
    }


async def _tool_rate_card_get(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    rate_card_id = _required_arg(args, "rate_card_id")
    row = (
        await db.execute(
            select(RateCard, Client.name, Client.code)
            .join(Client, Client.id == RateCard.client_id)
            .where(RateCard.id == rate_card_id, RateCard.tenant_id == current_user.tenant_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Rate card not found")
    rate_card, client_name, client_code = row
    return {
        "id": rate_card.id,
        "name": rate_card.name,
        "client_id": rate_card.client_id,
        "client_name": client_name,
        "client_code": client_code,
        "effective_from": rate_card.effective_from.isoformat(),
        "effective_to": rate_card.effective_to.isoformat() if rate_card.effective_to else None,
        "rules": _redact_settings(rate_card.rules or {}),
        "is_active": rate_card.is_active,
        "notes": rate_card.notes,
    }


def _changes(current: dict, proposed: dict, allowed_fields: set[str] | None = None) -> list[dict]:
    result: list[dict] = []
    for field, proposed_value in proposed.items():
        if allowed_fields is not None and field not in allowed_fields:
            continue
        current_value = current.get(field)
        if current_value != proposed_value:
            result.append(
                {
                    "field": field,
                    "current": _redact_settings(current_value),
                    "proposed": _redact_settings(proposed_value),
                }
            )
    return result


def _proposed(args: dict, aliases: tuple[str, ...] = ("changes", "settings")) -> dict:
    for alias in aliases:
        value = args.get(alias)
        if isinstance(value, dict):
            return dict(value)
    return {
        key: value
        for key, value in args.items()
        if key
        not in {
            "client_id",
            "sku_id",
            "warehouse_id",
            "location_id",
            "rate_card_id",
            "user_id",
        }
    }


def _preview_payload(
    target: dict,
    current: dict,
    proposed: dict,
    changed_fields: list[dict],
    *,
    permission_required: str,
    affected_workflows: list[str],
    risk: str = "medium",
) -> dict:
    return {
        "ok": True,
        "dry_run": True,
        "preview": True,
        "writes": False,
        "action": target.get("action"),
        "entity": {"type": target.get("type"), "id": target.get("id")},
        "target": target,
        "current": _redact_settings(current),
        "proposed": _redact_settings(proposed),
        "changes": changed_fields,
        "changed_count": len(changed_fields),
        "affected_workflows": affected_workflows,
        "permission_required": permission_required,
        "risk": risk,
        "confirmation_required_for_write": False,
        "next_action": "review_preview_before_write_gate",
    }


def _settings_preview_args(body: SettingsPreviewRequest | SettingsAgentRequest) -> dict:
    args = body.model_dump(exclude_none=True)
    args.pop("confirmation_token", None)
    return args


def _settings_write_config(setting_key: str) -> dict:
    config = SETTINGS_WRITE_CONFIG.get(setting_key)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unsupported settings write '{setting_key}'")
    return config


def _settings_entity_id(config: dict, tenant: Tenant, args: dict) -> str:
    entity_id_arg = config.get("entity_id_arg")
    return str(args.get(entity_id_arg) or tenant.id) if entity_id_arg else tenant.id


def _import_preview_args(body: ImportPreviewRequest | ImportAgentRequest) -> dict:
    args = body.model_dump(exclude_none=True)
    args.pop("confirmation_token", None)
    return args


def _pack_list_preview_args(
    body: PackListImportPreviewRequest | PackListImportAgentRequest,
) -> dict:
    args = body.model_dump(exclude_none=True)
    args.pop("confirmation_token", None)
    return args


def _import_write_config(import_key: str) -> dict:
    config = IMPORT_WRITE_CONFIG.get(import_key)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unsupported import write '{import_key}'")
    return config


def _import_payload_hash(config: dict, args: dict, preview: dict) -> str:
    return AgentEvidenceService.payload_hash(
        {
            "action": config["action"],
            "body": _redact_settings(args),
            "summary": preview.get("summary"),
            "missing_required": preview.get("missing_required"),
            "total_rows": preview.get("total_rows"),
            "mapping_used": preview.get("mapping_used") or preview.get("suggested_mapping"),
        }
    )


def _import_entity_id(import_key: str, args: dict, preview: dict) -> str:
    payload_hash = AgentEvidenceService.payload_hash(
        {
            "import_key": import_key,
            "file_name": args.get("file_name"),
            "csv_text": args.get("csv_text"),
            "source_text": args.get("source_text"),
            "mapping": args.get("mapping"),
            "total_rows": preview.get("total_rows"),
        }
    )
    return f"{import_key}:{payload_hash[:16]}"


def _import_preview_is_confirmable(preview: dict) -> bool:
    if preview.get("ok") is False:
        return False
    if preview.get("missing_required"):
        return False
    summary = preview.get("summary")
    return not (isinstance(summary, dict) and int(summary.get("error") or 0) > 0)


async def _persist_import_preview_evidence(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    import_key: str,
    args: dict,
    preview: dict,
) -> dict:
    config = _import_write_config(import_key)
    preview.update(
        {
            "ok": preview.get("ok", True),
            "dry_run": True,
            "preview": True,
            "writes": False,
            "action": f"{config['action']}.preview",
            "risk": "medium",
            "permission": config["permission"],
            "confirmation_required_for_write": False,
        }
    )
    if not _import_preview_is_confirmable(preview):
        preview["next_action"] = "fix_import_preview_errors_before_confirm"
        return preview

    entity_id = _import_entity_id(import_key, args, preview)
    preview_state_after = {
        key: value
        for key, value in preview.items()
        if key not in {"planned_request", "confirmation_payload", "state_after"}
    }
    planned_body = _redact_settings(args)
    planned_request = {
        "endpoint": config["preview_endpoint"],
        "agent_endpoint": config["agent_endpoint"],
        "body": planned_body,
        "idempotency_key_required_for_write": True,
    }
    payload_hash = _import_payload_hash(config, args, preview)
    token = AgentEvidenceService.issue_token(config["token_prefix"])
    confirmation_payload = {
        "confirmation_token": token,
        "required_permission": config["permission"],
        "evidence_id": None,
        "impact": {
            "total_rows": preview.get("total_rows", 0),
            "summary": preview.get("summary"),
        },
        "records": [
            {
                "type": config["entity_type"],
                "id": entity_id,
                "total_rows": preview.get("total_rows", 0),
            }
        ],
    }
    evidence = await AgentEvidenceService(db, tenant.id).persist_preview(
        action=config["action"],
        risk="medium",
        required_permission=config["permission"],
        entity_type=config["entity_type"],
        entity_id=entity_id,
        actor_user_id=current_user.sub,
        payload_hash=payload_hash,
        confirmation_token=token,
        planned_endpoint=config["preview_endpoint"],
        state_before={"writes": False, "total_rows": preview.get("total_rows", 0)},
        state_after=preview_state_after,
        planned_request=planned_request,
        confirmation_payload=confirmation_payload,
    )
    confirmation_payload["evidence_id"] = evidence.id
    preview.update(
        {
            "action": config["action"],
            "entity": {"type": config["entity_type"], "id": entity_id},
            "state_before": {"writes": False, "total_rows": preview.get("total_rows", 0)},
            "state_after": preview_state_after,
            "confirmation_required_for_write": True,
            "planned_request": planned_request,
            "confirmation_payload": confirmation_payload,
            "evidence_id": evidence.id,
            "next_action": "submit_import_with_confirm_token_after_review",
        }
    )
    return preview


async def _persist_settings_preview_evidence(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    setting_key: str,
    args: dict,
    preview: dict,
) -> dict:
    config = _settings_write_config(setting_key)
    entity_id = _settings_entity_id(config, tenant, args)
    planned_endpoint = f"POST /api/v1/agent/settings/{setting_key}/preview"
    agent_endpoint = f"POST /api/v1/agent/settings/{setting_key}/agent"
    planned_body = _redact_settings(args)
    payload_hash = AgentEvidenceService.payload_hash(
        {
            "action": config["action"],
            "entity_type": config["entity_type"],
            "entity_id": entity_id,
            "body": planned_body,
            "changes": preview.get("changes", []),
        }
    )
    token = AgentEvidenceService.issue_token(config["token_prefix"])
    confirmation_payload = {
        "confirmation_token": token,
        "required_permission": config["permission"],
        "evidence_id": None,
        "impact": {
            "changed_count": preview.get("changed_count", 0),
            "affected_workflows": preview.get("affected_workflows", []),
        },
        "records": [
            {
                "type": config["entity_type"],
                "id": entity_id,
                "changed_fields": [change["field"] for change in preview.get("changes", [])],
            }
        ],
    }
    planned_request = {
        "endpoint": planned_endpoint,
        "agent_endpoint": agent_endpoint,
        "body": planned_body,
        "idempotency_key_required_for_write": True,
    }
    evidence = await AgentEvidenceService(db, tenant.id).persist_preview(
        action=config["action"],
        risk="medium",
        required_permission=config["permission"],
        entity_type=config["entity_type"],
        entity_id=entity_id,
        actor_user_id=current_user.sub,
        payload_hash=payload_hash,
        confirmation_token=token,
        planned_endpoint=planned_endpoint,
        state_before=preview.get("current"),
        state_after=preview.get("proposed"),
        planned_request=planned_request,
        confirmation_payload=confirmation_payload,
    )
    confirmation_payload["evidence_id"] = evidence.id
    preview.update(
        {
            "action": config["action"],
            "risk": "medium",
            "permission": config["permission"],
            "entity": {"type": config["entity_type"], "id": entity_id},
            "state_before": preview.get("current"),
            "state_after": preview.get("proposed"),
            "writes": False,
            "confirmation_required_for_write": True,
            "planned_request": planned_request,
            "confirmation_payload": confirmation_payload,
            "evidence_id": evidence.id,
            "next_action": "submit_with_confirm_token_after_review",
        }
    )
    return preview


def _clean_receiving_code_settings(raw: dict) -> dict:
    proposed = {**RECEIVING_CODE_DEFAULTS}
    for key in RECEIVING_CODE_DEFAULTS:
        if key in raw:
            proposed[key] = raw[key]

    proposed["prefix"] = str(proposed.get("prefix") or "RCV").strip()[:24] or "RCV"
    separator = str(proposed.get("separator") if proposed.get("separator") is not None else "-")
    if separator not in {"-", "_", ""}:
        raise HTTPException(status_code=400, detail="Unsupported receiving code separator")
    proposed["separator"] = separator
    try:
        sequence_padding = int(str(proposed.get("sequence_padding", 3)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="sequence_padding must be a number") from exc
    if sequence_padding < 1 or sequence_padding > 8:
        raise HTTPException(status_code=400, detail="sequence_padding must be between 1 and 8")
    proposed["sequence_padding"] = sequence_padding
    proposed["include_order_number"] = bool(proposed.get("include_order_number", True))
    proposed["uppercase"] = bool(proposed.get("uppercase", True))
    return proposed


def _clean_receiving_label_settings(raw: dict) -> dict:
    allowed = set(RECEIVING_LABEL_FIELDS)
    fields = raw.get("fields", RECEIVING_LABEL_DEFAULTS["fields"])
    if not isinstance(fields, list):
        raise HTTPException(status_code=400, detail="fields must be a list")
    cleaned_fields = [str(field) for field in fields if str(field) in allowed]
    if not cleaned_fields:
        raise HTTPException(status_code=400, detail="At least one printable field is required")
    return {
        "fields": cleaned_fields,
        "show_field_labels": bool(raw.get("show_field_labels", True)),
    }


def _string_value(value, field: str, *, max_length: int, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise HTTPException(status_code=400, detail=f"{field} is required")
        return None
    text = str(value).strip()
    if required and not text:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if len(text) > max_length:
        raise HTTPException(status_code=400, detail=f"{field} is too long")
    return text or None


def _bool_value(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{field} must be true or false")
    return value


def _non_negative_float(value, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be a number") from exc
    if number < 0:
        raise HTTPException(status_code=400, detail=f"{field} must be non-negative")
    return number


def _positive_int(value, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer") from exc
    if number < 1:
        raise HTTPException(status_code=400, detail=f"{field} must be at least 1")
    return number


def _non_negative_int(value, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer") from exc
    if number < 0:
        raise HTTPException(status_code=400, detail=f"{field} must be non-negative")
    return number


def _dict_value(value, field: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{field} must be an object")
    return value


async def _blueprint_target_warehouse(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> tuple[Warehouse | None, dict]:
    warehouse_id = str(args.get("warehouse_id") or "").strip()
    warehouse_payload = dict(args.get("warehouse") or {})
    warehouse_code = _blueprint_string(warehouse_payload.get("code"), "DAL", max_length=20).upper()
    warehouse_name = _blueprint_string(warehouse_payload.get("name"), "Dallas Warehouse", max_length=200)
    if warehouse_id:
        warehouse = await db.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == current_user.tenant_id,
            )
        )
    else:
        warehouse = await db.scalar(
            select(Warehouse).where(
                Warehouse.code == warehouse_code,
                Warehouse.tenant_id == current_user.tenant_id,
            )
        )
    return warehouse, {
        "id": warehouse.id if warehouse else None,
        "name": warehouse.name if warehouse else warehouse_name,
        "code": warehouse.code if warehouse else warehouse_code,
        "timezone": warehouse.timezone if warehouse else warehouse_payload.get("timezone", "America/Chicago"),
        "will_create": warehouse is None,
    }


async def _tool_warehouse_blueprint_preview(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    args: dict,
    *,
    persist_evidence: bool = True,
) -> dict:
    raw_zones = args.get("zones") or []
    if not isinstance(raw_zones, list) or not raw_zones:
        raise HTTPException(status_code=400, detail="zones must include at least one blueprint zone")
    warehouse, target = await _blueprint_target_warehouse(db, current_user, args)
    zones = [_normalize_blueprint_zone(zone, index) for index, zone in enumerate(raw_zones)]
    seen_codes: set[str] = set()
    for zone in zones:
        if zone["code"] in seen_codes:
            raise HTTPException(status_code=400, detail=f"Duplicate zone code {zone['code']}")
        seen_codes.add(zone["code"])
        zone["locations"] = _generate_blueprint_locations(zone)

    existing_zone_codes: list[str] = []
    existing_location_barcodes: list[str] = []
    if warehouse:
        zone_codes = [zone["code"] for zone in zones if zone.get("create_locations")]
        if zone_codes:
            existing_zone_codes = list(
                (
                    await db.execute(
                        select(Zone.code).where(
                            Zone.warehouse_id == warehouse.id,
                            Zone.tenant_id == current_user.tenant_id,
                            Zone.code.in_(zone_codes),
                        )
                    )
                ).scalars()
            )
        location_barcodes = [
            location["barcode"] for zone in zones for location in zone.get("locations", [])
        ]
        if location_barcodes:
            existing_location_barcodes = list(
                (
                    await db.execute(
                        select(Location.barcode).where(
                            Location.warehouse_id == warehouse.id,
                            Location.tenant_id == current_user.tenant_id,
                            Location.barcode.in_(location_barcodes),
                        )
                    )
                ).scalars()
            )
    agv_planning = _blueprint_agv_planning(args)
    validation = _blueprint_validation(zones) + _blueprint_agv_planning_validation(
        agv_planning, zones
    )
    blocking_errors = []
    if existing_zone_codes:
        blocking_errors.append({"code": "zone_code_exists", "zone_codes": existing_zone_codes})
    if existing_location_barcodes:
        blocking_errors.append(
            {"code": "location_barcode_exists", "barcodes": existing_location_barcodes[:20]}
        )
    if any(check["ok"] is False for check in validation):
        blocking_errors.append({"code": "validation_failed", "checks": validation})

    location_count = sum(len(zone["locations"]) for zone in zones)
    area_summaries = _blueprint_area_summaries(zones)
    dock_doors = [
        door
        for zone in zones
        for door in _blueprint_dock_doors(zone, target["code"])
    ]
    wcs_point_mapping_draft = _blueprint_wcs_mapping_draft(zones, target["code"])
    wcs_point_mapping_draft.extend(
        _blueprint_station_wcs_mapping(target["code"], station)
        for station in agv_planning.get("stations", [])
    )
    preview = {
        "ok": not blocking_errors,
        "dry_run": True,
        "preview": True,
        "writes": False,
        "action": WAREHOUSE_BLUEPRINT_ACTION,
        "risk": "medium",
        "permission": WAREHOUSE_BLUEPRINT_PERMISSION,
        "entity": {"type": "warehouse", "id": target["id"] or target["code"]},
        "target": target,
        "source_image_name": args.get("source_image_name"),
        "layout": args.get("layout") or {},
        "agv_planning": agv_planning,
        "route_policy": agv_planning["route_policy"],
        "route_nodes": agv_planning["route_nodes"],
        "agv_paths": agv_planning["agv_paths"],
        "stations": agv_planning["stations"],
        "safety_zones": agv_planning["safety_zones"],
        "notes": args.get("notes"),
        "zones": zones,
        "area_dimensions": {
            "unit": "ft",
            "areas": [
                {
                    "code": zone["code"],
                    "type": zone["type"],
                    "dimensions": zone.get("dimensions") or {},
                    "layout_percent": zone["layout_percent"],
                }
                for zone in zones
            ],
        },
        "abc_floor_areas": area_summaries["abc_floor_areas"],
        "rack_areas": area_summaries["rack_areas"],
        "dock_doors": dock_doors,
        "wcs_point_mapping_draft": wcs_point_mapping_draft,
        "summary": {
            "zone_count": len(zones),
            "location_count": location_count,
            "will_create_warehouse": target["will_create"],
            "will_create_zones": len([zone for zone in zones if zone.get("create_locations")]),
            "dock_door_count": len(dock_doors),
            "wcs_point_mapping_draft_count": len(wcs_point_mapping_draft),
        },
        "validation": validation,
        "blocking_errors": blocking_errors,
        "confirmation_required_for_write": False,
        "next_action": "fix_blueprint_preview_errors_before_confirm"
        if blocking_errors
        else "submit_blueprint_with_confirm_token_after_review",
    }
    if blocking_errors or not persist_evidence:
        return preview

    planned_body = _redact_settings(args)
    payload_hash = AgentEvidenceService.payload_hash(
        {
            "action": WAREHOUSE_BLUEPRINT_ACTION,
            "body": planned_body,
            "summary": preview["summary"],
            "validation": validation,
        }
    )
    token = AgentEvidenceService.issue_token("wh-blueprint")
    confirmation_payload = {
        "confirmation_token": token,
        "required_permission": WAREHOUSE_BLUEPRINT_PERMISSION,
        "evidence_id": None,
        "impact": preview["summary"],
        "records": [
            {
                "type": "warehouse_blueprint",
                "id": target["id"] or target["code"],
                "zone_count": len(zones),
                "location_count": location_count,
            }
        ],
    }
    planned_request = {
        "endpoint": "POST /api/v1/agent/warehouse-blueprints/preview",
        "agent_endpoint": "POST /api/v1/agent/warehouse-blueprints/agent",
        "body": planned_body,
        "idempotency_key_required_for_write": True,
    }
    evidence = await AgentEvidenceService(db, tenant.id).persist_preview(
        action=WAREHOUSE_BLUEPRINT_ACTION,
        risk="medium",
        required_permission=WAREHOUSE_BLUEPRINT_PERMISSION,
        entity_type="warehouse",
        entity_id=target["id"] or target["code"],
        actor_user_id=current_user.sub,
        payload_hash=payload_hash,
        confirmation_token=token,
        planned_endpoint=planned_request["endpoint"],
        state_before={"warehouse": target, "existing": bool(warehouse)},
        state_after={
            key: preview[key]
            for key in (
                "target",
                "layout",
                "zones",
                "summary",
                "validation",
                "abc_floor_areas",
                "rack_areas",
                "dock_doors",
                "wcs_point_mapping_draft",
                "agv_planning",
            )
        },
        planned_request=planned_request,
        confirmation_payload=confirmation_payload,
    )
    confirmation_payload["evidence_id"] = evidence.id
    preview.update(
        {
            "confirmation_required_for_write": True,
            "planned_request": planned_request,
            "confirmation_payload": confirmation_payload,
            "evidence_id": evidence.id,
        }
    )
    return preview


def _blueprint_confirmation_hash(args: dict, preview: dict) -> str:
    return AgentEvidenceService.payload_hash(
        {
            "action": WAREHOUSE_BLUEPRINT_ACTION,
            "body": _redact_settings(args),
            "summary": preview.get("summary"),
            "validation": preview.get("validation"),
        }
    )


async def _apply_warehouse_blueprint_write(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    args: dict,
    confirmation_token: str,
    idempotency_key: str,
) -> dict:
    preview = await _tool_warehouse_blueprint_preview(
        db, tenant, current_user, args, persist_evidence=False
    )
    if preview.get("blocking_errors"):
        raise HTTPException(status_code=409, detail={"code": "blueprint_preview_not_confirmable"})
    entity_id = preview["entity"]["id"]
    evidence_svc = AgentEvidenceService(db, tenant.id)
    evidence = await evidence_svc.find_preview(
        action=WAREHOUSE_BLUEPRINT_ACTION,
        entity_type="warehouse",
        entity_id=entity_id,
        payload_hash=_blueprint_confirmation_hash(args, preview),
        confirmation_token=confirmation_token,
    )
    if not evidence:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "confirmation_mismatch",
                "message": "Warehouse blueprint confirmation token does not match the latest preview.",
            },
        )

    warehouse_payload = dict(args.get("warehouse") or {})
    warehouse = await db.scalar(
        select(Warehouse).where(
            Warehouse.id == preview["target"].get("id"),
            Warehouse.tenant_id == current_user.tenant_id,
        )
    )
    if not warehouse:
        warehouse = Warehouse(
            tenant_id=current_user.tenant_id,
            name=preview["target"]["name"],
            code=preview["target"]["code"],
            timezone=preview["target"].get("timezone") or "America/Chicago",
            address=warehouse_payload.get("address") if isinstance(warehouse_payload.get("address"), dict) else {},
        )
        db.add(warehouse)
        await db.flush()

    address = dict(warehouse.address or {})
    address["_blueprint_layout"] = {
        "source_image_name": args.get("source_image_name"),
        "layout": args.get("layout") or {},
        "planning_standard": (preview.get("agv_planning") or {}).get("planning_standard") or {},
        "route_policy": preview.get("route_policy") or {},
        "route_nodes": preview.get("route_nodes") or [],
        "agv_paths": preview.get("agv_paths") or [],
        "stations": preview.get("stations") or [],
        "safety_zones": preview.get("safety_zones") or [],
        "notes": args.get("notes"),
        "area_dimensions": preview.get("area_dimensions") or {},
        "abc_floor_areas": preview.get("abc_floor_areas") or [],
        "rack_areas": preview.get("rack_areas") or [],
        "dock_doors": preview.get("dock_doors") or [],
        "wcs_point_mapping_draft": preview.get("wcs_point_mapping_draft") or [],
        "zones": [
            {
                "name": zone["name"],
                "code": zone["code"],
                "type": zone["type"],
                "layout_percent": zone["layout_percent"],
                "dimensions": zone["dimensions"],
                "metadata": zone["metadata"],
                "is_access_point": zone.get("is_access_point", False),
                "location_count": len(zone["locations"]),
            }
            for zone in preview["zones"]
        ],
        "access_points": [
            {
                "name": zone["name"],
                "code": zone["code"],
                "type": zone["type"],
                "layout_percent": zone["layout_percent"],
                "dimensions": zone["dimensions"],
                "metadata": zone["metadata"],
                "agv_usage": "unload_and_ship" if zone["type"] == "dock" else None,
            }
            for zone in preview["zones"]
            if zone.get("is_access_point")
        ],
        "validation": preview["validation"],
        "stored_at": datetime.now(UTC).isoformat(),
    }
    zone_modes = _agent_planner_zone_modes_from_address(address)
    location_metadata = dict(address.get("_blueprint_location_metadata") or {})
    created_zone_ids: list[str] = []
    created_location_ids: list[str] = []
    for zone_payload in preview["zones"]:
        if not zone_payload.get("create_locations"):
            continue
        zone = Zone(
            tenant_id=current_user.tenant_id,
            warehouse_id=warehouse.id,
            name=zone_payload["name"],
            code=zone_payload["code"],
            sequence=zone_payload["sequence"],
            is_agv_zone=True,
            zone_type=zone_payload["type"],
            coordinate_x=_decimal_or_none(zone_payload["layout_percent"].get("x")),
            coordinate_y=_decimal_or_none(zone_payload["layout_percent"].get("y")),
            coordinate_z=None,
            dimensions=zone_payload.get("dimensions") or {},
            layout_metadata={
                "coordinate_system": "drawing_percent",
                "layout_percent": zone_payload["layout_percent"],
                "layout_mode": zone_payload["layout_mode"],
                "route_role": (zone_payload.get("metadata") or {}).get("route_role"),
                "lane_policy": (zone_payload.get("metadata") or {}).get("lane_policy"),
                "agv_internal_travel": (zone_payload.get("metadata") or {}).get("agv_internal_travel"),
                "handoff_strategy": (zone_payload.get("metadata") or {}).get("handoff_strategy"),
                "handoff_edges": (zone_payload.get("metadata") or {}).get("handoff_edges"),
                "direction": (zone_payload.get("metadata") or {}).get("direction"),
                "docking_direction": (zone_payload.get("metadata") or {}).get("docking_direction"),
                "route_anchor_id": (zone_payload.get("metadata") or {}).get("route_anchor_id"),
                "route_exit_id": (zone_payload.get("metadata") or {}).get("route_exit_id"),
                "planning_standard": AGV_PLANNING_STANDARD_DOC,
            },
            drawing_source={
                "source_type": "blueprint",
                "source_name": args.get("source_image_name"),
                "imported_at": datetime.now(UTC).isoformat(),
            },
        )
        db.add(zone)
        await db.flush()
        created_zone_ids.append(zone.id)
        zone_modes[zone.id] = zone_payload["layout_mode"]
        for location_payload in zone_payload["locations"]:
            location_wcs_mapping = _blueprint_wcs_point_mapping(
                warehouse.code,
                zone=zone_payload,
                location=location_payload,
            )
            location_wcs_metadata = {
                **location_wcs_mapping,
                "draft_point_code": location_wcs_mapping.get("point_code"),
                "point_code": None,
                "route_anchor_id": (location_wcs_mapping.get("wcs_metadata") or {}).get("route_anchor_id"),
                "route_exit_id": (location_wcs_mapping.get("wcs_metadata") or {}).get("route_exit_id"),
                "docking_direction": (location_wcs_mapping.get("wcs_metadata") or {}).get("docking_direction"),
                "route_role": (location_wcs_mapping.get("wcs_metadata") or {}).get("route_role"),
                "agv_internal_travel": (location_wcs_mapping.get("wcs_metadata") or {}).get("agv_internal_travel"),
                "handoff_strategy": (location_wcs_mapping.get("wcs_metadata") or {}).get("handoff_strategy"),
                "handoff_edges": (location_wcs_mapping.get("wcs_metadata") or {}).get("handoff_edges"),
            }
            location = Location(
                tenant_id=current_user.tenant_id,
                warehouse_id=warehouse.id,
                zone_id=zone.id,
                barcode=location_payload["barcode"],
                aisle=location_payload["aisle"],
                rack=location_payload["rack"],
                level=location_payload["level"],
                position=location_payload["position"],
                location_type=location_payload["location_type"],
                current_status=LocationStatus.AVAILABLE.value,
                pick_sequence=location_payload["pick_sequence"],
                is_agv_accessible=True,
                coordinate_x=_decimal_or_none(
                    (location_payload.get("layout_percent") or {}).get("x")
                ),
                coordinate_y=_decimal_or_none(
                    (location_payload.get("layout_percent") or {}).get("y")
                ),
                coordinate_z=None,
                dimensions=location_payload.get("dimensions") or {},
                layout_metadata={
                    "coordinate_system": "drawing_percent",
                    "zone_layout_percent": zone_payload["layout_percent"],
                    "layout_percent": location_payload.get("layout_percent") or {},
                    "slot_layout_percent": location_payload.get("slot_layout_percent") or {},
                    "route_role": (zone_payload.get("metadata") or {}).get("route_role"),
                    "lane_policy": (zone_payload.get("metadata") or {}).get("lane_policy"),
                    "agv_internal_travel": (zone_payload.get("metadata") or {}).get("agv_internal_travel"),
                    "handoff_strategy": (zone_payload.get("metadata") or {}).get("handoff_strategy"),
                    "handoff_edges": (zone_payload.get("metadata") or {}).get("handoff_edges"),
                    "docking_direction": (zone_payload.get("metadata") or {}).get("docking_direction"),
                    "route_anchor_id": (zone_payload.get("metadata") or {}).get("route_anchor_id"),
                    "route_exit_id": (zone_payload.get("metadata") or {}).get("route_exit_id"),
                    "planning_standard": AGV_PLANNING_STANDARD_DOC,
                },
                drawing_source={
                    "source_type": "blueprint",
                    "source_name": args.get("source_image_name"),
                    "zone_code": zone_payload["code"],
                    "imported_at": datetime.now(UTC).isoformat(),
                },
                wcs_point_metadata=location_wcs_metadata,
            )
            db.add(location)
            await db.flush()
            created_location_ids.append(location.id)
            location_metadata[location.barcode] = {
                "zone_code": zone_payload["code"],
                "zone_type": zone_payload["type"],
                "location_type": location_payload["location_type"],
                "dimensions": location_payload.get("dimensions") or {},
                "pallet": zone_payload.get("metadata", {}).get("pallet"),
                "zone_layout_percent": zone_payload["layout_percent"],
                "layout_percent": location_payload.get("layout_percent") or zone_payload["layout_percent"],
                "slot_layout_percent": location_payload.get("slot_layout_percent") or {},
                "route_role": zone_payload.get("metadata", {}).get("route_role"),
                "lane_policy": zone_payload.get("metadata", {}).get("lane_policy"),
                "agv_internal_travel": zone_payload.get("metadata", {}).get("agv_internal_travel"),
                "handoff_strategy": zone_payload.get("metadata", {}).get("handoff_strategy"),
                "handoff_edges": zone_payload.get("metadata", {}).get("handoff_edges"),
                "docking_direction": zone_payload.get("metadata", {}).get("docking_direction"),
                "route_anchor_id": zone_payload.get("metadata", {}).get("route_anchor_id"),
                "route_exit_id": zone_payload.get("metadata", {}).get("route_exit_id"),
                "planning_standard": AGV_PLANNING_STANDARD_DOC,
                "source": "warehouse_blueprint",
                "wcs_point_metadata": location_wcs_metadata,
            }
    address["_planner_zone_modes"] = zone_modes
    address["_blueprint_location_metadata"] = location_metadata
    warehouse.address = address
    await db.flush()
    result = {
        "ok": True,
        "action": WAREHOUSE_BLUEPRINT_ACTION,
        "risk": "medium",
        "entity": {"type": "warehouse", "id": warehouse.id},
        "warehouse": {"id": warehouse.id, "name": warehouse.name, "code": warehouse.code},
        "created_zone_ids": created_zone_ids,
        "created_location_count": len(created_location_ids),
        "state_before": preview.get("state_before"),
        "state_after": {
            "warehouse_id": warehouse.id,
            "summary": preview["summary"],
            "validation": preview["validation"],
        },
        "confirmation_token": "[accepted]",
        "evidence_id": evidence.id,
        "idempotency_key": idempotency_key,
        "next_action": "open_warehouse_map_and_review_locations",
    }
    await evidence_svc.mark_executed(
        evidence,
        actor_user_id=current_user.sub,
        idempotency_key=idempotency_key,
        state_after=result["state_after"],
        result=result,
        success=True,
    )
    return result


async def _clean_client_profile_changes(
    db: AsyncSession, current_user: TokenPayload, client_id: str, raw: dict
) -> dict:
    cleaned: dict = {}
    if "name" in raw:
        cleaned["name"] = _string_value(raw["name"], "name", max_length=200, required=True)
    if "code" in raw:
        code = _string_value(raw["code"], "code", max_length=50, required=True)
        duplicate = await db.scalar(
            select(Client.id).where(
                Client.tenant_id == current_user.tenant_id,
                Client.code == code,
                Client.id != client_id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Client code already exists")
        cleaned["code"] = code
    if "contact_email" in raw:
        email = _string_value(raw["contact_email"], "contact_email", max_length=254)
        if email and "@" not in email:
            raise HTTPException(status_code=400, detail="contact_email must be an email address")
        cleaned["contact_email"] = email
    if "contact_phone" in raw:
        cleaned["contact_phone"] = _string_value(raw["contact_phone"], "contact_phone", max_length=20)
    if "billing_enabled" in raw:
        cleaned["billing_enabled"] = _bool_value(raw["billing_enabled"], "billing_enabled")
    if "portal_access" in raw:
        cleaned["portal_access"] = _bool_value(raw["portal_access"], "portal_access")
    if "is_active" in raw:
        cleaned["is_active"] = _bool_value(raw["is_active"], "is_active")
    if "address" in raw:
        cleaned["address"] = _dict_value(raw["address"], "address")
    if "notes" in raw:
        cleaned["notes"] = _string_value(raw["notes"], "notes", max_length=4000)
    return cleaned


async def _clean_sku_changes(
    db: AsyncSession, current_user: TokenPayload, sku: SKU, raw: dict
) -> dict:
    cleaned: dict = {}
    if "sku_code" in raw:
        sku_code = _string_value(raw["sku_code"], "sku_code", max_length=100, required=True)
        duplicate = await db.scalar(
            select(SKU.id).where(
                SKU.tenant_id == current_user.tenant_id,
                SKU.client_id == sku.client_id,
                SKU.sku_code == sku_code,
                SKU.id != sku.id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="SKU code already exists for this client")
        cleaned["sku_code"] = sku_code
    if "barcode" in raw:
        cleaned["barcode"] = _string_value(raw["barcode"], "barcode", max_length=100)
    if "name" in raw:
        cleaned["name"] = _string_value(raw["name"], "name", max_length=300, required=True)
    if "description" in raw:
        cleaned["description"] = _string_value(raw["description"], "description", max_length=4000)
    for field in ("weight_kg", "length_cm", "width_cm", "height_cm"):
        if field in raw:
            cleaned[field] = _non_negative_float(raw[field], field)
    for field in ("requires_lot", "requires_expiry", "is_hazmat"):
        if field in raw:
            cleaned[field] = _bool_value(raw[field], field)
    for field in ("units_per_case", "cases_per_pallet"):
        if field in raw:
            cleaned[field] = _positive_int(raw[field], field)
    return cleaned


async def _clean_warehouse_location_changes(
    db: AsyncSession, current_user: TokenPayload, location: Location, raw: dict
) -> dict:
    cleaned: dict = {}
    if "barcode" in raw:
        barcode = _string_value(raw["barcode"], "barcode", max_length=50, required=True)
        duplicate = await db.scalar(
            select(Location.id).where(
                Location.tenant_id == current_user.tenant_id,
                Location.warehouse_id == location.warehouse_id,
                Location.barcode == barcode,
                Location.id != location.id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Location barcode already exists")
        cleaned["barcode"] = barcode
    for field in ("aisle", "rack", "level", "position"):
        if field in raw:
            cleaned[field] = _string_value(raw[field], field, max_length=10, required=True)
    if "location_type" in raw:
        value = str(raw["location_type"]).strip()
        if value not in {item.value for item in LocationType}:
            raise HTTPException(status_code=400, detail="Unsupported location_type")
        cleaned["location_type"] = value
    if "current_status" in raw:
        value = str(raw["current_status"]).strip()
        if value not in {item.value for item in LocationStatus}:
            raise HTTPException(status_code=400, detail="Unsupported current_status")
        cleaned["current_status"] = value
    for field in ("max_weight_kg", "max_volume_m3"):
        if field in raw:
            cleaned[field] = _non_negative_float(raw[field], field)
    if "pick_sequence" in raw:
        cleaned["pick_sequence"] = _non_negative_int(raw["pick_sequence"], "pick_sequence")
    if "is_agv_accessible" in raw:
        cleaned["is_agv_accessible"] = _bool_value(raw["is_agv_accessible"], "is_agv_accessible")
    for field in ("dimensions", "layout_metadata", "drawing_source", "wcs_point_metadata"):
        if field in raw:
            cleaned[field] = _dict_value(raw[field], field)
    return cleaned


async def _tool_receiving_codes_preview(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    args: dict,
    *,
    persist_evidence: bool = True,
) -> dict:
    current = await _tool_receiving_codes_get(tenant)
    proposed = _clean_receiving_code_settings({**current, **_proposed(args)})
    proposed["sample_code"] = _compose_receiving_code_sample(proposed)
    changes = _changes(current, proposed, set(RECEIVING_CODE_DEFAULTS) | {"sample_code"})
    preview = _preview_payload(
        target={"type": "receiving_code_settings", "id": tenant.id},
        current=current,
        proposed=proposed,
        changed_fields=changes,
        permission_required=UserPermission.USERS_MANAGE.value,
        affected_workflows=["Receiving", "Package labels", "Inbound import recovery"],
    )
    if not persist_evidence:
        return preview
    return await _persist_settings_preview_evidence(
        db, tenant, current_user, "receiving-codes", args, preview
    )


async def _tool_receiving_labels_preview(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    args: dict,
    *,
    persist_evidence: bool = True,
) -> dict:
    current = await _tool_receiving_labels_get(tenant)
    proposed = _clean_receiving_label_settings({**current, **_proposed(args)})
    proposed["available_fields"] = RECEIVING_LABEL_FIELDS
    changes = _changes(current, proposed, {"fields", "show_field_labels"})
    preview = _preview_payload(
        target={"type": "receiving_label_settings", "id": tenant.id},
        current=current,
        proposed=proposed,
        changed_fields=changes,
        permission_required=UserPermission.USERS_MANAGE.value,
        affected_workflows=["Receiving", "Label printing", "Package exception recovery"],
    )
    if not persist_evidence:
        return preview
    return await _persist_settings_preview_evidence(
        db, tenant, current_user, "receiving-labels", args, preview
    )


async def _tool_client_profile_preview(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    client_id = _required_arg(args, "client_id")
    client_payload = await _tool_client_profile_get(
        db, current_user, {"client_id": client_id, "limit": 1}
    )
    if not client_payload["items"]:
        raise HTTPException(status_code=404, detail="Client not found")
    current = client_payload["items"][0]
    proposed = {
        **current,
        **await _clean_client_profile_changes(
            db, current_user, client_id, _proposed(args, ("changes", "profile"))
        ),
    }
    return _preview_payload(
        target={"type": "client", "id": client_id},
        current=current,
        proposed=proposed,
        changed_fields=_changes(current, proposed, CLIENT_PROFILE_WRITE_FIELDS),
        permission_required=UserPermission.MASTER_DATA_MANAGE.value,
        affected_workflows=["Client portal", "Inbound orders", "Outbound orders", "Billing"],
    )


async def _tool_sku_preview(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    sku_id = _required_arg(args, "sku_id")
    row = (
        await db.execute(
            select(SKU, Client.name, Client.code)
            .join(Client, Client.id == SKU.client_id)
            .where(SKU.id == sku_id, SKU.tenant_id == current_user.tenant_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="SKU not found")
    sku, client_name, client_code = row
    current = {
        "id": sku.id,
        "client_id": sku.client_id,
        "client_name": client_name,
        "client_code": client_code,
        "sku_code": sku.sku_code,
        "barcode": sku.barcode,
        "name": sku.name,
        "description": sku.description,
        "weight_kg": _num(sku.weight_kg),
        "length_cm": _num(sku.length_cm),
        "width_cm": _num(sku.width_cm),
        "height_cm": _num(sku.height_cm),
        "requires_lot": sku.requires_lot,
        "requires_expiry": sku.requires_expiry,
        "is_hazmat": sku.is_hazmat,
        "units_per_case": sku.units_per_case,
        "cases_per_pallet": sku.cases_per_pallet,
        "attributes": _redact_settings(sku.attributes or {}),
    }
    proposed = {
        **current,
        **await _clean_sku_changes(db, current_user, sku, _proposed(args, ("changes", "sku"))),
    }
    return _preview_payload(
        target={"type": "sku", "id": sku_id},
        current=current,
        proposed=proposed,
        changed_fields=_changes(current, proposed, SKU_WRITE_FIELDS),
        permission_required=UserPermission.MASTER_DATA_MANAGE.value,
        affected_workflows=["Receiving", "Inventory", "Picking", "Shipping"],
    )


async def _tool_warehouse_location_preview(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    location_id = _required_arg(args, "location_id")
    row = (
        await db.execute(
            select(Location, Warehouse.code, Zone.code)
            .join(Warehouse, Warehouse.id == Location.warehouse_id)
            .join(Zone, Zone.id == Location.zone_id)
            .where(Location.id == location_id, Location.tenant_id == current_user.tenant_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")
    location, warehouse_code, zone_code = row
    current = {
        "id": location.id,
        "warehouse_id": location.warehouse_id,
        "warehouse_code": warehouse_code,
        "zone_id": location.zone_id,
        "zone_code": zone_code,
        "barcode": location.barcode,
        "aisle": location.aisle,
        "rack": location.rack,
        "level": location.level,
        "position": location.position,
        "location_type": location.location_type,
        "current_status": location.current_status,
        "max_weight_kg": _num(location.max_weight_kg),
        "max_volume_m3": _num(location.max_volume_m3),
        "pick_sequence": location.pick_sequence,
        "is_agv_accessible": location.is_agv_accessible,
    }
    proposed = {
        **current,
        **await _clean_warehouse_location_changes(
            db, current_user, location, _proposed(args, ("changes", "location"))
        ),
    }
    return _preview_payload(
        target={"type": "location", "id": location_id},
        current=current,
        proposed=proposed,
        changed_fields=_changes(current, proposed, WAREHOUSE_LOCATION_WRITE_FIELDS),
        permission_required=UserPermission.MASTER_DATA_MANAGE.value,
        affected_workflows=["Receiving", "Putaway", "Picking", "Inventory"],
    )


async def _tool_billing_rate_card_preview(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    rate_card_id = _required_arg(args, "rate_card_id")
    current = await _tool_rate_card_get(db, current_user, {"rate_card_id": rate_card_id})
    proposed = {**current, **_redact_settings(_proposed(args, ("changes", "rate_card")))}
    allowed = {"name", "effective_from", "effective_to", "rules", "is_active", "notes"}
    return _preview_payload(
        target={"type": "rate_card", "id": rate_card_id},
        current=current,
        proposed=proposed,
        changed_fields=_changes(current, proposed, allowed),
        permission_required=UserPermission.BILLING_MANAGE.value,
        affected_workflows=["Billing", "Invoice generation", "Client reporting"],
    )


async def _settings_preview_for_key(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    setting_key: str,
    args: dict,
    *,
    persist_evidence: bool = True,
) -> dict:
    if setting_key == "receiving-codes":
        return await _tool_receiving_codes_preview(
            db, tenant, current_user, args, persist_evidence=persist_evidence
        )
    if setting_key == "receiving-labels":
        return await _tool_receiving_labels_preview(
            db, tenant, current_user, args, persist_evidence=persist_evidence
        )
    if setting_key == "client-profile":
        preview = await _tool_client_profile_preview(db, current_user, args)
    elif setting_key == "sku":
        preview = await _tool_sku_preview(db, current_user, args)
    elif setting_key == "warehouse-location":
        preview = await _tool_warehouse_location_preview(db, current_user, args)
    else:
        raise HTTPException(status_code=404, detail=f"Unsupported settings preview '{setting_key}'")

    if not persist_evidence or setting_key not in SETTINGS_WRITE_CONFIG:
        return preview
    return await _persist_settings_preview_evidence(
        db, tenant, current_user, setting_key, args, preview
    )


def _settings_confirmation_hash(config: dict, tenant: Tenant, args: dict, preview: dict) -> str:
    entity_id = _settings_entity_id(config, tenant, args)
    return AgentEvidenceService.payload_hash(
        {
            "action": config["action"],
            "entity_type": config["entity_type"],
            "entity_id": entity_id,
            "body": _redact_settings(args),
            "changes": preview.get("changes", []),
        }
    )


def _write_changed_fields(
    target, proposed: dict, allowed_fields: set[str], changed_names: set[str]
) -> list[str]:
    changed: list[str] = []
    for field in allowed_fields:
        if field not in proposed or field not in changed_names:
            continue
        setattr(target, field, proposed[field])
        changed.append(field)
    return changed


async def _apply_settings_write(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    setting_key: str,
    args: dict,
    confirmation_token: str,
    idempotency_key: str,
) -> dict:
    config = _settings_write_config(setting_key)
    preview = await _settings_preview_for_key(
        db, tenant, current_user, setting_key, args, persist_evidence=False
    )
    entity_id = _settings_entity_id(config, tenant, args)
    payload_hash = _settings_confirmation_hash(config, tenant, args, preview)
    evidence_svc = AgentEvidenceService(db, tenant.id)
    evidence = await evidence_svc.find_preview(
        action=config["action"],
        entity_type=config["entity_type"],
        entity_id=entity_id,
        payload_hash=payload_hash,
        confirmation_token=confirmation_token,
    )
    if not evidence:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "confirmation_mismatch",
                "message": "Settings confirmation token does not match the latest preview.",
            },
        )

    proposed = preview.get("proposed") or {}
    changed_names = {change["field"] for change in preview.get("changes", [])}
    changed_fields: list[str] = []
    if setting_key == "receiving-codes":
        tenant_settings = dict(tenant.settings or {})
        tenant_settings["receiving_code_rules"] = {
            key: proposed[key] for key in RECEIVING_CODE_DEFAULTS if key in proposed
        }
        tenant.settings = tenant_settings
        changed_fields = [change["field"] for change in preview.get("changes", [])]
    elif setting_key == "receiving-labels":
        tenant_settings = dict(tenant.settings or {})
        tenant_settings["receiving_label_template"] = {
            "fields": proposed.get("fields", RECEIVING_LABEL_DEFAULTS["fields"]),
            "show_field_labels": bool(proposed.get("show_field_labels", True)),
        }
        tenant.settings = tenant_settings
        changed_fields = [change["field"] for change in preview.get("changes", [])]
    elif setting_key == "client-profile":
        client = await db.scalar(
            select(Client).where(Client.id == entity_id, Client.tenant_id == current_user.tenant_id)
        )
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        changed_fields = _write_changed_fields(
            client,
            proposed,
            CLIENT_PROFILE_WRITE_FIELDS,
            changed_names,
        )
    elif setting_key == "sku":
        sku = await db.scalar(
            select(SKU).where(SKU.id == entity_id, SKU.tenant_id == current_user.tenant_id)
        )
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")
        changed_fields = _write_changed_fields(
            sku,
            proposed,
            SKU_WRITE_FIELDS,
            changed_names,
        )
    elif setting_key == "warehouse-location":
        location = await db.scalar(
            select(Location).where(
                Location.id == entity_id, Location.tenant_id == current_user.tenant_id
            )
        )
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")
        changed_fields = _write_changed_fields(
            location,
            proposed,
            WAREHOUSE_LOCATION_WRITE_FIELDS,
            changed_names,
        )
    else:
        raise HTTPException(status_code=404, detail=f"Unsupported settings write '{setting_key}'")

    await db.flush()
    result = {
        "ok": True,
        "action": config["action"],
        "risk": "medium",
        "entity": {"type": config["entity_type"], "id": entity_id},
        "changed_fields": changed_fields,
        "state_before": preview.get("current"),
        "state_after": preview.get("proposed"),
        "confirmation_token": "[accepted]",
        "evidence_id": evidence.id,
        "idempotency_key": idempotency_key,
        "next_action": "review_settings_audit",
    }
    await evidence_svc.mark_executed(
        evidence,
        actor_user_id=current_user.sub,
        idempotency_key=idempotency_key,
        state_after=preview.get("proposed"),
        result=result,
        success=True,
    )
    return result


async def _tool_inbound_orders_list(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    limit = max(1, min(int(args.get("limit", 8)), 25))
    status_filter = str(args.get("status", "") or "").strip().lower()
    query = (
        select(InboundOrder, Client.name, Warehouse.name)
        .join(Client, Client.id == InboundOrder.client_id)
        .join(Warehouse, Warehouse.id == InboundOrder.warehouse_id)
        .where(InboundOrder.tenant_id == current_user.tenant_id)
        .order_by(InboundOrder.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(InboundOrder.status == status_filter)
    rows = (await db.execute(query)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "reference_number": order.reference_number,
                "status": order.status,
                "client_name": client_name,
                "warehouse_name": warehouse_name,
                "expected_date": order.expected_date.isoformat() if order.expected_date else None,
                "supplier_name": order.supplier_name,
            }
            for order, client_name, warehouse_name in rows
        ],
    }


async def _tool_outbound_orders_list(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    limit = max(1, min(int(args.get("limit", 8)), 25))
    status_filter = str(args.get("status", "") or "").strip().lower()
    query = (
        select(OutboundOrder, Client.name, Warehouse.name)
        .join(Client, Client.id == OutboundOrder.client_id)
        .join(Warehouse, Warehouse.id == OutboundOrder.warehouse_id)
        .where(OutboundOrder.tenant_id == current_user.tenant_id)
        .order_by(OutboundOrder.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(OutboundOrder.status == status_filter)
    rows = (await db.execute(query)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "reference_number": order.reference_number,
                "status": order.status,
                "priority": order.priority,
                "client_name": client_name,
                "warehouse_name": warehouse_name,
                "carrier": order.carrier,
            }
            for order, client_name, warehouse_name in rows
        ],
    }


async def _tool_inventory_search(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit", 10)), 30))
    search = str(args.get("query", "") or "").strip()

    quantity_on_hand = func.coalesce(func.sum(Inventory.quantity_on_hand), 0)
    quantity_allocated = func.coalesce(func.sum(Inventory.quantity_allocated), 0)
    quantity_damaged = func.coalesce(func.sum(Inventory.quantity_damaged), 0)

    query = (
        select(
            SKU.id,
            SKU.sku_code,
            SKU.name,
            Client.name,
            quantity_on_hand.label("on_hand"),
            quantity_allocated.label("allocated"),
            quantity_damaged.label("damaged"),
        )
        .join(Client, Client.id == SKU.client_id)
        .outerjoin(Inventory, Inventory.sku_id == SKU.id)
        .where(SKU.tenant_id == current_user.tenant_id)
        .group_by(SKU.id, SKU.sku_code, SKU.name, Client.name)
        .order_by(SKU.created_at.desc())
        .limit(limit)
    )
    if search:
        like = f"%{search}%"
        query = query.where(
            or_(SKU.sku_code.ilike(like), SKU.name.ilike(like), Client.name.ilike(like))
        )

    rows = (await db.execute(query)).all()
    return {
        "count": len(rows),
        "query": search or None,
        "items": [
            {
                "sku_id": sku_id,
                "sku_code": sku_code,
                "sku_name": sku_name,
                "client_name": client_name,
                "quantity_on_hand": int(on_hand or 0),
                "quantity_allocated": int(allocated or 0),
                "quantity_damaged": int(damaged or 0),
                "quantity_available": int((on_hand or 0) - (allocated or 0) - (damaged or 0)),
            }
            for sku_id, sku_code, sku_name, client_name, on_hand, allocated, damaged in rows
        ],
    }


async def _tool_inventory_explain(
    db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
) -> dict:
    inventory_payload = await _tool_inventory_search(db, current_user, args)
    settings = _raw_agent_settings(tenant)
    service = AgentModelService(settings)
    return await service.explain_inventory(
        str(args.get("query", "") or "").strip(),
        inventory_payload,
        str(args.get("language", "") or "").strip() or None,
    )


async def _tool_clients_list(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit", 10)), 30))
    rows = (
        await db.execute(
            select(Client)
            .where(Client.tenant_id == current_user.tenant_id)
            .order_by(Client.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    items = [
        {
            "id": client.id,
            "name": client.name,
            "code": client.code,
            "contact_email": client.contact_email,
            "is_active": client.is_active,
        }
        for client in rows
    ]
    return {"count": len(items), "items": items}


async def _tool_warehouses_list(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit", 10)), 30))
    rows = (
        await db.execute(
            select(Warehouse)
            .where(Warehouse.tenant_id == current_user.tenant_id)
            .order_by(Warehouse.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    items = [
        {
            "id": warehouse.id,
            "name": warehouse.name,
            "code": warehouse.code,
            "timezone": warehouse.timezone,
            "is_active": warehouse.is_active,
        }
        for warehouse in rows
    ]
    return {"count": len(items), "items": items}


async def _tool_skus_list(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit", 10)), 30))
    search = str(args.get("query", "") or "").strip()
    query = (
        select(SKU, Client.name)
        .join(Client, Client.id == SKU.client_id)
        .where(SKU.tenant_id == current_user.tenant_id)
        .order_by(SKU.created_at.desc())
        .limit(limit)
    )
    if search:
        like = f"%{search}%"
        query = query.where(
            or_(SKU.sku_code.ilike(like), SKU.name.ilike(like), Client.name.ilike(like))
        )
    rows = (await db.execute(query)).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": sku.id,
                "sku_code": sku.sku_code,
                "name": sku.name,
                "client_name": client_name,
                "weight_kg": float(sku.weight_kg) if sku.weight_kg is not None else None,
                "requires_lot": sku.requires_lot,
                "requires_expiry": sku.requires_expiry,
            }
            for sku, client_name in rows
        ],
    }


async def _tool_rate_cards_list(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
    limit = max(1, min(int(args.get("limit", 10)), 30))
    rows = (
        await db.execute(
            select(RateCard, Client.name)
            .join(Client, Client.id == RateCard.client_id)
            .where(RateCard.tenant_id == current_user.tenant_id)
            .order_by(RateCard.created_at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": rate_card.id,
                "name": rate_card.name,
                "client_name": client_name,
                "effective_from": rate_card.effective_from.isoformat(),
                "is_active": rate_card.is_active,
            }
            for rate_card, client_name in rows
        ],
    }


async def _tool_preview_inbound_import(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    csv_text = str(args.get("csv_text", "") or "")
    file_name = str(args.get("file_name", "agent-inline.csv") or "agent-inline.csv")
    if not csv_text.strip():
        raise HTTPException(
            status_code=400, detail="csv_text is required for inbound import preview"
        )

    headers, rows = load_csv_rows(file_name, csv_text.encode("utf-8"))
    suggested_mapping = _parse_mapping(None, headers)
    sample_rows = rows[:5]
    mapped_preview = [
        {
            field: (row.get(header_name) or "").strip()
            for field, header_name in suggested_mapping.items()
        }
        for row in sample_rows
    ]

    return {
        "headers": headers,
        "required_fields": REQUIRED_INBOUND_FIELDS,
        "optional_fields": OPTIONAL_INBOUND_FIELDS,
        "suggested_mapping": suggested_mapping,
        "missing_required": [
            field for field in REQUIRED_INBOUND_FIELDS if field not in suggested_mapping
        ],
        "sample_rows": sample_rows,
        "mapped_preview": mapped_preview,
        "total_rows": len(rows),
    }


async def _tool_import_inbound_with_mapping(
    db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
) -> dict:
    csv_text = str(args.get("csv_text", "") or "")
    file_name = str(args.get("file_name", "agent-inline.csv") or "agent-inline.csv")
    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="csv_text is required for inbound import")

    settings = _raw_agent_settings(tenant)
    if settings.get("requires_human_confirmation_for_writes") and not bool(args.get("confirmed")):
        raise HTTPException(
            status_code=409, detail="Confirmation required before importing inbound data"
        )

    headers, rows = load_csv_rows(file_name, csv_text.encode("utf-8"))
    field_mapping = _parse_mapping(args.get("mapping"), headers)
    svc = ReceivingService(db, current_user.tenant_id)

    clients = {
        client.code: client
        for client in (
            await db.execute(select(Client).where(Client.tenant_id == current_user.tenant_id))
        ).scalars()
    }
    warehouses = {
        warehouse.code: warehouse
        for warehouse in (
            await db.execute(select(Warehouse).where(Warehouse.tenant_id == current_user.tenant_id))
        ).scalars()
    }
    skus = {
        sku.sku_code: sku
        for sku in (
            await db.execute(select(SKU).where(SKU.tenant_id == current_user.tenant_id))
        ).scalars()
    }

    grouped_rows, errors = _build_inbound_import_payloads(
        rows=rows,
        field_mapping=field_mapping,
        clients=clients,
        warehouses=warehouses,
        skus=skus,
    )

    imported = 0
    for order_number, payload in grouped_rows.items():
        await svc.create_inbound_order(
            client_id=payload["client_id"],
            warehouse_id=payload["warehouse_id"],
            order_number=order_number,
            lines=payload["lines"],
            reference_number=payload["reference_number"],
            supplier_name=payload["supplier_name"],
        )
        imported += 1

    await db.flush()
    return {
        "imported": imported,
        "errors": errors,
        "total_rows": len(rows),
        "mapping_used": field_mapping,
    }


async def _tool_preview_pack_list_import(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    return await PackListService(db, current_user.tenant_id).preview(args)


async def _tool_import_pack_list(
    db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
) -> dict:
    settings = _raw_agent_settings(tenant)
    if settings.get("requires_human_confirmation_for_writes") and not bool(args.get("confirmed")):
        raise HTTPException(
            status_code=409,
            detail="Confirmation required before importing a customer Pack List",
        )
    return await PackListService(db, current_user.tenant_id).import_after_preview(
        args, current_user.sub
    )


async def _tool_preview_outbound_import(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    csv_text = str(args.get("csv_text", "") or "")
    file_name = str(args.get("file_name", "agent-outbound.csv") or "agent-outbound.csv")
    if not csv_text.strip():
        raise HTTPException(
            status_code=400, detail="csv_text is required for outbound import preview"
        )

    headers, rows = load_csv_rows(file_name, csv_text.encode("utf-8"))
    suggested_mapping = _suggest_outbound_mapping(headers)
    sample_rows = rows[:5]
    mapped_preview = [
        {
            field: (row.get(header_name) or "").strip()
            for field, header_name in suggested_mapping.items()
        }
        for row in sample_rows
    ]

    return {
        "headers": headers,
        "required_fields": REQUIRED_OUTBOUND_FIELDS,
        "optional_fields": OPTIONAL_OUTBOUND_FIELDS,
        "suggested_mapping": suggested_mapping,
        "missing_required": [
            field for field in REQUIRED_OUTBOUND_FIELDS if field not in suggested_mapping
        ],
        "sample_rows": sample_rows,
        "mapped_preview": mapped_preview,
        "total_rows": len(rows),
    }


async def _tool_import_outbound_with_mapping(
    db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
) -> dict:
    csv_text = str(args.get("csv_text", "") or "")
    file_name = str(args.get("file_name", "agent-outbound.csv") or "agent-outbound.csv")
    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="csv_text is required for outbound import")

    settings = _raw_agent_settings(tenant)
    if settings.get("requires_human_confirmation_for_writes") and not bool(args.get("confirmed")):
        raise HTTPException(
            status_code=409, detail="Confirmation required before importing outbound data"
        )

    headers, rows = load_csv_rows(file_name, csv_text.encode("utf-8"))
    field_mapping = _parse_outbound_mapping(args.get("mapping"), headers)

    clients = {
        client.code: client
        for client in (
            await db.execute(select(Client).where(Client.tenant_id == current_user.tenant_id))
        ).scalars()
    }
    warehouses = {
        warehouse.code: warehouse
        for warehouse in (
            await db.execute(select(Warehouse).where(Warehouse.tenant_id == current_user.tenant_id))
        ).scalars()
    }
    skus = {
        sku.sku_code: sku
        for sku in (
            await db.execute(select(SKU).where(SKU.tenant_id == current_user.tenant_id))
        ).scalars()
    }

    grouped_rows: dict[str, dict] = {}
    errors: list[dict] = []
    for row_number, row in enumerate(rows, start=2):
        order_number = (row.get(field_mapping.get("order_number", "")) or "").strip()
        client_code = (row.get(field_mapping.get("client_code", "")) or "").strip()
        warehouse_code = (row.get(field_mapping.get("warehouse_code", "")) or "").strip()
        sku_code = (row.get(field_mapping.get("sku_code", "")) or "").strip()
        reference_header = field_mapping.get("reference_number")
        carrier_header = field_mapping.get("carrier")
        reference_number = (
            (row.get(reference_header) or "").strip() or None if reference_header else None
        )
        carrier = (row.get(carrier_header) or "").strip() or None if carrier_header else None

        try:
            quantity = int((row.get(field_mapping.get("quantity", "")) or "").strip())
        except ValueError:
            quantity = 0

        if (
            not order_number
            or not client_code
            or not warehouse_code
            or not sku_code
            or quantity <= 0
        ):
            errors.append({"row": row_number, "error": "Missing required outbound CSV fields"})
            continue
        if client_code not in clients:
            errors.append({"row": row_number, "error": f"Client '{client_code}' not found"})
            continue
        if warehouse_code not in warehouses:
            errors.append({"row": row_number, "error": f"Warehouse '{warehouse_code}' not found"})
            continue
        if sku_code not in skus:
            errors.append({"row": row_number, "error": f"SKU '{sku_code}' not found"})
            continue

        order_bucket = grouped_rows.setdefault(
            order_number,
            {
                "client_id": clients[client_code].id,
                "warehouse_id": warehouses[warehouse_code].id,
                "reference_number": reference_number,
                "carrier": carrier,
                "lines": [],
            },
        )
        order_bucket["lines"].append({"sku_id": skus[sku_code].id, "quantity": quantity})

    imported = 0
    for order_number, payload in grouped_rows.items():
        try:
            await _create_outbound_order(
                db=db,
                tenant_id=current_user.tenant_id,
                client_id=payload["client_id"],
                warehouse_id=payload["warehouse_id"],
                order_number=order_number,
                lines=payload["lines"],
                reference_number=payload["reference_number"],
                carrier=payload["carrier"],
            )
            imported += 1
        except ValueError as exc:
            errors.append({"row": order_number, "error": str(exc)})

    await db.flush()
    return {
        "imported": imported,
        "errors": errors,
        "total_rows": len(rows),
        "mapping_used": field_mapping,
    }


async def _tool_preview_inventory_import(
    db: AsyncSession, current_user: TokenPayload, args: dict
) -> dict:
    csv_text = str(args.get("csv_text", "") or "")
    file_name = str(args.get("file_name", "agent-inventory.csv") or "agent-inventory.csv")
    if not csv_text.strip():
        raise HTTPException(
            status_code=400, detail="csv_text is required for inventory import preview"
        )

    headers, rows = load_csv_rows(file_name, csv_text.encode("utf-8"))
    suggested_mapping = _suggest_inventory_mapping(headers)
    mapping = _parse_inventory_mapping(args.get("mapping"), headers)
    sample_rows = rows[:5]
    mapped_preview = [
        {
            field: (row.get(header_name) or "").strip() for field, header_name in mapping.items()
        }
        for row in sample_rows
    ]
    missing_required = [field for field in INVENTORY_REQUIRED_FIELDS if field not in mapping]
    row_results: list[dict] = []
    summary = {"create": 0, "update": 0, "noop": 0, "error": 0, "total_quantity_delta": 0}

    if not missing_required:
        for row_number, row in enumerate(rows, start=2):
            sku_code = (row.get(mapping.get("sku_code", "")) or "").strip()
            loc_barcode = (row.get(mapping.get("location_barcode", "")) or "").strip()
            client_value = (row.get(mapping.get("client_id", "")) or "").strip()
            lot_number = (row.get(mapping.get("lot_number", "")) or "").strip() or None
            raw_quantity = (row.get(mapping.get("quantity", "")) or "").strip()
            errors: list[str] = []
            try:
                quantity = int(raw_quantity)
            except ValueError:
                quantity = 0
                errors.append("quantity_must_be_integer")
            if not sku_code:
                errors.append("sku_code_required")
            if not loc_barcode:
                errors.append("location_barcode_required")
            if quantity <= 0:
                errors.append("quantity_must_be_positive")

            sku = None
            loc = None
            inv = None
            if sku_code:
                sku = await db.scalar(
                    select(SKU).where(
                        SKU.sku_code == sku_code,
                        SKU.tenant_id == current_user.tenant_id,
                    )
                )
                if not sku:
                    errors.append("sku_not_found")
            if loc_barcode:
                loc = await db.scalar(
                    select(Location).where(
                        Location.barcode == loc_barcode,
                        Location.tenant_id == current_user.tenant_id,
                    )
                )
                if not loc:
                    errors.append("location_not_found")
            if sku and client_value:
                client = await db.scalar(
                    select(Client).where(
                        Client.tenant_id == current_user.tenant_id,
                        or_(Client.id == client_value, Client.code == client_value),
                    )
                )
                if not client:
                    errors.append("client_not_found")
                elif client.id != sku.client_id:
                    errors.append("client_does_not_match_sku")
            if sku and loc:
                inv = await db.scalar(
                    select(Inventory).where(
                        Inventory.sku_id == sku.id,
                        Inventory.location_id == loc.id,
                        Inventory.tenant_id == current_user.tenant_id,
                        Inventory.warehouse_id == loc.warehouse_id,
                        Inventory.lot_number == lot_number,
                    )
                )

            current_quantity = int(inv.quantity_on_hand) if inv else 0
            delta = quantity - current_quantity
            operation = "error"
            if not errors:
                operation = "create" if inv is None else "noop" if delta == 0 else "update"
                summary[operation] += 1
                summary["total_quantity_delta"] += delta
            else:
                summary["error"] += 1

            row_results.append(
                {
                    "row": row_number,
                    "operation": operation,
                    "errors": errors,
                    "sku_code": sku_code,
                    "sku_id": sku.id if sku else None,
                    "location_barcode": loc_barcode,
                    "location_id": loc.id if loc else None,
                    "warehouse_id": loc.warehouse_id if loc else None,
                    "lot_number": lot_number,
                    "current_quantity": current_quantity,
                    "proposed_quantity": quantity,
                    "quantity_delta": delta if not errors else None,
                }
            )
    else:
        summary["error"] = len(rows)

    return {
        "ok": not missing_required,
        "dry_run": True,
        "action": "inventory.import.preview",
        "risk": "medium",
        "permission": "master_data.manage",
        "headers": headers,
        "required_fields": INVENTORY_REQUIRED_FIELDS,
        "optional_fields": INVENTORY_OPTIONAL_FIELDS,
        "suggested_mapping": suggested_mapping,
        "mapping_used": mapping,
        "missing_required": missing_required,
        "sample_rows": sample_rows,
        "mapped_preview": mapped_preview,
        "total_rows": len(rows),
        "summary": summary,
        "row_results": row_results[:100],
        "confirmation_required_for_write": False,
        "next_action": "fix_errors_or_route_to_manual_import",
        "result": {
            "what_happened": "Inventory import preview completed without writing inventory.",
            "why_blocked": "Agent inventory import writes remain disabled.",
            "recommended_action": "Review row_results and use a governed manual import path if approved.",
            "safe_commands": [
                "wms inventory import preview --file inventory.csv",
                "wms inventory lookup --query SKU",
            ],
        },
    }


async def _tool_import_inventory_with_mapping(
    db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
) -> dict:
    csv_text = str(args.get("csv_text", "") or "")
    file_name = str(args.get("file_name", "agent-inventory.csv") or "agent-inventory.csv")
    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="csv_text is required for inventory import")

    settings = _raw_agent_settings(tenant)
    if settings.get("requires_human_confirmation_for_writes") and not bool(args.get("confirmed")):
        raise HTTPException(
            status_code=409, detail="Confirmation required before importing inventory data"
        )

    headers, rows = load_csv_rows(file_name, csv_text.encode("utf-8"))
    field_mapping = _parse_inventory_mapping(args.get("mapping"), headers)

    imported = 0
    errors: list[dict] = []

    for row_number, row in enumerate(rows, start=2):
        sku_code = (row.get(field_mapping.get("sku_code", "")) or "").strip()
        loc_barcode = (row.get(field_mapping.get("location_barcode", "")) or "").strip()
        client_id = (row.get(field_mapping.get("client_id", "")) or "").strip()
        lot_number = (row.get(field_mapping.get("lot_number", "")) or "").strip() or None
        try:
            qty = int((row.get(field_mapping.get("quantity", "")) or "").strip())
        except ValueError:
            qty = 0

        if not sku_code or not loc_barcode or qty <= 0:
            errors.append(
                {"row": row_number, "error": "Missing sku_code, location_barcode, or quantity"}
            )
            continue

        sku = await db.scalar(
            select(SKU).where(SKU.sku_code == sku_code, SKU.tenant_id == current_user.tenant_id)
        )
        if not sku:
            errors.append({"row": row_number, "error": f"SKU '{sku_code}' not found"})
            continue

        loc = await db.scalar(
            select(Location).where(
                Location.barcode == loc_barcode, Location.tenant_id == current_user.tenant_id
            )
        )
        if not loc:
            errors.append({"row": row_number, "error": f"Location '{loc_barcode}' not found"})
            continue

        resolved_warehouse_id = loc.warehouse_id
        inv = await db.scalar(
            select(Inventory).where(
                Inventory.sku_id == sku.id,
                Inventory.location_id == loc.id,
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.warehouse_id == resolved_warehouse_id,
                Inventory.lot_number == lot_number,
            )
        )

        if inv:
            inv.quantity_on_hand = qty
        else:
            inv = Inventory(
                tenant_id=current_user.tenant_id,
                client_id=client_id or sku.client_id,
                warehouse_id=resolved_warehouse_id,
                location_id=loc.id,
                sku_id=sku.id,
                quantity_on_hand=qty,
                lot_number=lot_number,
                received_at=datetime.now(UTC),
            )
            db.add(inv)
        imported += 1

    await db.flush()
    return {
        "imported": imported,
        "errors": errors,
        "total_rows": len(rows),
        "mapping_used": field_mapping,
    }


async def _import_preview_for_key(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    import_key: str,
    args: dict,
    *,
    persist_evidence: bool = True,
) -> dict:
    if import_key == "inbound":
        preview = await _tool_preview_inbound_import(db, current_user, args)
    elif import_key == "pack-list":
        preview = await _tool_preview_pack_list_import(db, current_user, args)
    elif import_key == "outbound":
        preview = await _tool_preview_outbound_import(db, current_user, args)
    elif import_key == "inventory":
        preview = await _tool_preview_inventory_import(db, current_user, args)
    else:
        raise HTTPException(status_code=404, detail=f"Unsupported import preview '{import_key}'")
    if not persist_evidence:
        return preview
    return await _persist_import_preview_evidence(
        db, tenant, current_user, import_key, args, preview
    )


async def _apply_import_write(
    db: AsyncSession,
    tenant: Tenant,
    current_user: TokenPayload,
    import_key: str,
    args: dict,
    confirmation_token: str,
    idempotency_key: str,
) -> dict:
    config = _import_write_config(import_key)
    preview = await _import_preview_for_key(
        db, tenant, current_user, import_key, args, persist_evidence=False
    )
    if not _import_preview_is_confirmable(preview):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "import_preview_not_confirmable",
                "message": "Import preview has errors. Fix the CSV or mapping and rerun preview.",
            },
        )
    entity_id = _import_entity_id(import_key, args, preview)
    payload_hash = _import_payload_hash(config, args, preview)
    evidence_svc = AgentEvidenceService(db, tenant.id)
    evidence = await evidence_svc.find_preview(
        action=config["action"],
        entity_type=config["entity_type"],
        entity_id=entity_id,
        payload_hash=payload_hash,
        confirmation_token=confirmation_token,
    )
    if not evidence:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "confirmation_mismatch",
                "message": "Import confirmation token does not match the latest preview.",
            },
        )

    write_args = {**args, "confirmed": True}
    write_tx = await db.begin_nested()
    try:
        if import_key == "inbound":
            import_result = await _tool_import_inbound_with_mapping(
                db, tenant, current_user, write_args
            )
        elif import_key == "pack-list":
            import_result = await _tool_import_pack_list(
                db, tenant, current_user, write_args
            )
        elif import_key == "outbound":
            import_result = await _tool_import_outbound_with_mapping(
                db, tenant, current_user, write_args
            )
        else:
            import_result = await _tool_import_inventory_with_mapping(
                db, tenant, current_user, write_args
            )
    except Exception:
        await write_tx.rollback()
        raise

    if import_result.get("errors"):
        await write_tx.rollback()
    else:
        await write_tx.commit()

    success = not import_result.get("errors")
    result = {
        "ok": success,
        "action": config["action"],
        "risk": "medium",
        "entity": {"type": config["entity_type"], "id": entity_id},
        "state_before": {"writes": False, "total_rows": preview.get("total_rows", 0)},
        "state_after": import_result,
        "confirmation_token": "[accepted]",
        "evidence_id": evidence.id,
        "idempotency_key": idempotency_key,
        "next_action": "review_import_audit" if success else "review_import_errors",
        "result": import_result,
    }
    await evidence_svc.mark_executed(
        evidence,
        actor_user_id=current_user.sub,
        idempotency_key=idempotency_key,
        state_after=import_result,
        result=result,
        success=success,
        failure_reason=None if success else "import_result_has_errors",
    )
    return result


def _settings_preview_handler(setting_key: str):
    async def handler(db, tenant, current_user, args):
        return await _settings_preview_for_key(db, tenant, current_user, setting_key, args)

    return handler


def _import_preview_handler(import_key: str):
    async def handler(db, tenant, current_user, args):
        return await _import_preview_for_key(db, tenant, current_user, import_key, args)

    return handler


# Registry of agent tools. Every handler is normalized to the signature
# (db, tenant, current_user, args); wrappers drop the arguments the underlying
# _tool_* function does not take.
TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "settings.agent.get": lambda db, tenant, current_user, args: _tool_agent_settings_get(tenant),
    "settings.receiving_codes.get": lambda db, tenant, current_user, args: _tool_receiving_codes_get(tenant),
    "settings.receiving_labels.get": lambda db, tenant, current_user, args: _tool_receiving_labels_get(tenant),
    "settings.users.list": lambda db, tenant, current_user, args: _tool_users_list(db, current_user, args),
    "settings.users.get": lambda db, tenant, current_user, args: _tool_user_get(db, current_user, args),
    "settings.permissions.explain": lambda db, tenant, current_user, args: _tool_permissions_explain(current_user),
    "settings.client_profile.get": lambda db, tenant, current_user, args: _tool_client_profile_get(db, current_user, args),
    "settings.billing.explain": lambda db, tenant, current_user, args: _tool_billing_explain(db, tenant, current_user),
    "settings.warehouse_locations.list": lambda db, tenant, current_user, args: _tool_warehouse_locations_list(db, current_user, args),
    "settings.warehouse.get": lambda db, tenant, current_user, args: _tool_warehouse_get(db, current_user, args),
    "settings.rate_card.get": lambda db, tenant, current_user, args: _tool_rate_card_get(db, current_user, args),
    "settings.receiving_codes.preview": _settings_preview_handler("receiving-codes"),
    "settings.receiving_labels.preview": _settings_preview_handler("receiving-labels"),
    "settings.client_profile.preview": _settings_preview_handler("client-profile"),
    "settings.sku.preview": _settings_preview_handler("sku"),
    "settings.warehouse_location.preview": _settings_preview_handler("warehouse-location"),
    "warehouse.blueprint.preview": lambda db, tenant, current_user, args: _tool_warehouse_blueprint_preview(db, tenant, current_user, args),
    "settings.billing_rate_card.preview": lambda db, tenant, current_user, args: _tool_billing_rate_card_preview(db, current_user, args),
    "setup.progress": lambda db, tenant, current_user, args: _tool_setup_progress(db, current_user),
    "orders.inbound.list": lambda db, tenant, current_user, args: _tool_inbound_orders_list(db, current_user, args),
    "orders.outbound.list": lambda db, tenant, current_user, args: _tool_outbound_orders_list(db, current_user, args),
    "inventory.search": lambda db, tenant, current_user, args: _tool_inventory_search(db, current_user, args),
    "inventory.explain": lambda db, tenant, current_user, args: _tool_inventory_explain(db, tenant, current_user, args),
    "clients.list": lambda db, tenant, current_user, args: _tool_clients_list(db, current_user, args),
    "clients.get": lambda db, tenant, current_user, args: _tool_clients_list(db, current_user, args),
    "warehouses.list": lambda db, tenant, current_user, args: _tool_warehouses_list(db, current_user, args),
    "skus.list": lambda db, tenant, current_user, args: _tool_skus_list(db, current_user, args),
    "billing.rate_cards.list": lambda db, tenant, current_user, args: _tool_rate_cards_list(db, current_user, args),
    "receiving.inbound.preview_import": _import_preview_handler("inbound"),
    "receiving.inbound.import_with_mapping": lambda db, tenant, current_user, args: _tool_import_inbound_with_mapping(db, tenant, current_user, args),
    "receiving.inbound.preview_pack_list": lambda db, tenant, current_user, args: _tool_preview_pack_list_import(db, current_user, args),
    "receiving.inbound.import_pack_list": lambda db, tenant, current_user, args: _tool_import_pack_list(db, tenant, current_user, args),
    "orders.outbound.preview_import": _import_preview_handler("outbound"),
    "orders.outbound.import_with_mapping": lambda db, tenant, current_user, args: _tool_import_outbound_with_mapping(db, tenant, current_user, args),
    "migration.inventory.preview": _import_preview_handler("inventory"),
    "migration.inventory.import": lambda db, tenant, current_user, args: _tool_import_inventory_with_mapping(db, tenant, current_user, args),
}


async def _run_agent_tool(
    db: AsyncSession, tenant: Tenant, current_user: TokenPayload, tool_name: str, args: dict
) -> dict | list:
    if tool_name in DIRECT_IMPORT_WRITE_TOOLS:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "agent_write_gate_required",
                "message": (
                    f"Tool '{tool_name}' is disabled for direct agent execution. "
                    "Run the matching preview and use an evidence-backed /agent endpoint."
                ),
            },
        )
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise HTTPException(status_code=501, detail=f"Tool '{tool_name}' is not implemented yet")
    return await handler(db, tenant, current_user, args)


async def _append_agent_run_log(
    tenant: Tenant, current_user: TokenPayload, tool_name: str, tool_risk: str, args: dict
) -> datetime:
    tenant_settings = dict(tenant.settings or {})
    history = list(tenant_settings.get("agent_console_runs") or [])
    logged_at = datetime.now(UTC)
    history.insert(
        0,
        {
            "logged_at": logged_at.isoformat(),
            "user_id": current_user.sub,
            "tenant_id": current_user.tenant_id,
            "tool_name": tool_name,
            "risk": tool_risk,
            "args": args,
        },
    )
    tenant_settings["agent_console_runs"] = history[:20]
    tenant.settings = tenant_settings
    return logged_at


@router.get("/team/status")
async def agent_team_status(
    current_user: TokenPayload = Depends(get_current_user),
):
    if not _can_access_agent_team(current_user):
        raise HTTPException(status_code=403, detail="You cannot access the agent team")
    service = AgentTeamService()
    return {"agents": service.available_agents()}


@router.post("/team/run", response_model=AgentTeamRunResponse)
async def run_agent_team(
    body: AgentTeamRunRequest,
    current_user: TokenPayload = Depends(get_current_user),
):
    if not _can_access_agent_team(current_user):
        raise HTTPException(status_code=403, detail="You cannot access the agent team")
    service = AgentTeamService()
    return await service.run(body.mode, body.task, body.context, body.agents)


@router.get("/settings", response_model=AgentSettingsResponse)
async def get_agent_settings(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not _can_access_agent_console(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to the agent console")
    tenant = await _load_target_tenant(db, current_user)
    payload = _settings_payload(tenant)
    return AgentSettingsResponse(**payload, tool_catalog=TOOL_CATALOG)


@router.get("/evidence")
async def list_agent_evidence(
    action: str | None = Query(None),
    status: str | None = Query(None),
    entity_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.MASTER_DATA_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    query = (
        select(AgentEvidence)
        .where(AgentEvidence.tenant_id == current_user.tenant_id)
        .order_by(AgentEvidence.created_at.desc(), AgentEvidence.id.desc())
        .limit(limit)
    )
    if action:
        query = query.where(AgentEvidence.action == action)
    if status:
        query = query.where(AgentEvidence.status == status)
    if entity_id:
        query = query.where(AgentEvidence.entity_id == entity_id)
    rows = (await db.execute(query)).scalars().all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "risk": row.risk,
                "required_permission": row.required_permission,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "status": row.status,
                "payload_hash": row.payload_hash,
                "planned_endpoint": row.planned_endpoint,
                "idempotency_key": row.idempotency_key,
                "failure_reason": row.failure_reason,
                "created_at": row.created_at.isoformat(),
                "expires_at": row.expires_at.isoformat(),
                "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            }
            for row in rows
        ],
    }


def _agent_evidence_detail(row: AgentEvidence) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "risk": row.risk,
        "required_permission": row.required_permission,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "actor_user_id": row.actor_user_id,
        "status": row.status,
        "payload_hash": row.payload_hash,
        "planned_endpoint": row.planned_endpoint,
        "idempotency_key": row.idempotency_key,
        "failure_reason": row.failure_reason,
        "state_before": row.state_before,
        "state_after": row.state_after,
        "planned_request": row.planned_request,
        "confirmation_payload": row.confirmation_payload,
        "result": row.result,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
    }


@router.get("/evidence/failed")
async def list_failed_agent_evidence(
    action: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.MASTER_DATA_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    return await list_agent_evidence(
        action=action,
        status="failed",
        entity_id=None,
        limit=limit,
        current_user=current_user,
        db=db,
    )


@router.get("/evidence/{evidence_id}")
async def get_agent_evidence_detail(
    evidence_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.MASTER_DATA_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    row = await db.scalar(
        select(AgentEvidence).where(
            AgentEvidence.id == evidence_id,
            AgentEvidence.tenant_id == current_user.tenant_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent evidence not found")
    return _agent_evidence_detail(row)


@router.get("/evidence/{evidence_id}/replay-preview")
async def replay_agent_evidence_preview(
    evidence_id: str,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.MASTER_DATA_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    row = await db.scalar(
        select(AgentEvidence).where(
            AgentEvidence.id == evidence_id,
            AgentEvidence.tenant_id == current_user.tenant_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent evidence not found")
    return {
        "ok": True,
        "dry_run": True,
        "action": "evidence.replay_preview",
        "entity": {"type": "agent_evidence", "id": row.id},
        "source_action": row.action,
        "source_status": row.status,
        "state_before": row.state_before,
        "state_after": row.state_after,
        "planned_request": row.planned_request,
        "confirmation_payload": row.confirmation_payload,
        "confirmation_required_for_write": row.status == "previewed",
        "next_action": "rerun_live_preview_before_any_write",
        "result": {
            "what_happened": "Stored preview evidence was replayed for review only.",
            "why_blocked": "Replay does not refresh state or issue a new confirmation token.",
            "recommended_action": "Run the matching live preview again before any production write.",
            "safe_commands": ["wms capabilities --json", "wms evidence detail --id EVIDENCE-ID"],
        },
    }


@router.post("/inventory/import/preview")
async def preview_inventory_import_for_agent(
    body: InventoryImportPreviewRequest,
    current_user: TokenPayload = Depends(
        require_permission(UserPermission.MASTER_DATA_MANAGE.value)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    return await _tool_preview_inventory_import(
        db,
        current_user,
        {
            "csv_text": body.csv_text,
            "file_name": body.file_name,
            "mapping": body.mapping,
        },
    )


@router.post("/imports/{import_key}/preview")
async def preview_import_for_agent(
    import_key: str,
    body: ImportPreviewRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    tenant = await _load_target_tenant(db, current_user)
    config = _import_write_config(import_key)
    _ensure_agent_tool_access(tenant, current_user, config["preview_tool"])
    preview = await _import_preview_for_key(
        db,
        tenant,
        current_user,
        import_key,
        _import_preview_args(body),
        persist_evidence=True,
    )
    await db.flush()
    return preview


@router.post("/imports/{import_key}/agent")
async def confirm_import_for_agent(
    import_key: str,
    body: ImportAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent import writes",
            },
        )
    tenant = await _load_target_tenant(db, current_user)
    config = _import_write_config(import_key)
    _ensure_agent_tool_access(tenant, current_user, config["preview_tool"])
    args = _import_preview_args(body)

    async def execute():
        return await _apply_import_write(
            db,
            tenant,
            current_user,
            import_key,
            args,
            body.confirmation_token,
            x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation=f"{config['action']}.agent_confirm",
        request_payload={"import_key": import_key, "body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/packlists/preview")
async def preview_pack_list_for_agent(
    body: PackListImportPreviewRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    tenant = await _load_target_tenant(db, current_user)
    config = _import_write_config("pack-list")
    _ensure_agent_tool_access(tenant, current_user, config["preview_tool"])
    preview = await _import_preview_for_key(
        db,
        tenant,
        current_user,
        "pack-list",
        _pack_list_preview_args(body),
        persist_evidence=True,
    )
    await db.flush()
    return preview


@router.post("/packlists/agent")
async def confirm_pack_list_for_agent(
    body: PackListImportAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for Pack List writes",
            },
        )
    tenant = await _load_target_tenant(db, current_user)
    config = _import_write_config("pack-list")
    _ensure_agent_tool_access(tenant, current_user, config["preview_tool"])
    args = _pack_list_preview_args(body)

    async def execute():
        return await _apply_import_write(
            db,
            tenant,
            current_user,
            "pack-list",
            args,
            body.confirmation_token,
            x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation="receiving.inbound.import_pack_list.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/warehouse-blueprints/preview")
async def preview_warehouse_blueprint_for_agent(
    body: WarehouseBlueprintPreviewRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    tenant = await _load_target_tenant(db, current_user)
    _ensure_agent_tool_access(tenant, current_user, "warehouse.blueprint.preview")
    preview = await _tool_warehouse_blueprint_preview(
        db,
        tenant,
        current_user,
        body.model_dump(exclude_none=True),
        persist_evidence=True,
    )
    await db.flush()
    return preview


@router.post("/warehouse-blueprints/agent")
async def confirm_warehouse_blueprint_for_agent(
    body: WarehouseBlueprintAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent warehouse blueprint writes",
            },
        )
    tenant = await _load_target_tenant(db, current_user)
    _ensure_agent_tool_access(tenant, current_user, "warehouse.blueprint.preview")
    args = body.model_dump(exclude_none=True)
    args.pop("confirmation_token", None)

    async def execute():
        return await _apply_warehouse_blueprint_write(
            db,
            tenant,
            current_user,
            args,
            body.confirmation_token,
            x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation=f"{WAREHOUSE_BLUEPRINT_ACTION}.agent_confirm",
        request_payload={"body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/settings/{setting_key}/preview")
async def preview_settings_change_for_agent(
    setting_key: str,
    body: SettingsPreviewRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    tenant = await _load_target_tenant(db, current_user)
    config = _settings_write_config(setting_key)
    _ensure_agent_tool_access(tenant, current_user, config["preview_tool"])
    preview = await _settings_preview_for_key(
        db,
        tenant,
        current_user,
        setting_key,
        _settings_preview_args(body),
        persist_evidence=True,
    )
    await db.flush()
    return preview


@router.post("/settings/{setting_key}/agent")
async def confirm_settings_change_for_agent(
    setting_key: str,
    body: SettingsAgentRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not x_idempotency_key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "idempotency_key_required",
                "message": "X-Idempotency-Key is required for agent settings writes",
            },
        )
    tenant = await _load_target_tenant(db, current_user)
    config = _settings_write_config(setting_key)
    _ensure_agent_tool_access(tenant, current_user, config["preview_tool"])
    args = _settings_preview_args(body)

    async def execute():
        return await _apply_settings_write(
            db,
            tenant,
            current_user,
            setting_key,
            args,
            body.confirmation_token,
            x_idempotency_key,
        )

    return await IdempotencyService(db, current_user.tenant_id).run(
        key=x_idempotency_key,
        operation=f"{config['action']}.agent_confirm",
        request_payload={"setting_key": setting_key, "body": body.model_dump(mode="json")},
        handler=execute,
    )


@router.post("/tools/run", response_model=AgentToolRunResponse)
async def run_agent_tool(
    body: AgentToolRunRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not _can_access_agent_console(current_user):
        raise HTTPException(status_code=403, detail="You do not have access to the agent console")
    tenant = await _load_target_tenant(db, current_user)
    tool = _ensure_agent_tool_access(tenant, current_user, body.tool_name)
    args = body.args or {}
    result = await _run_agent_tool(db, tenant, current_user, body.tool_name, args)
    logged_at = await _append_agent_run_log(
        tenant, current_user, body.tool_name, tool["risk"], args
    )
    await db.flush()
    return AgentToolRunResponse(
        tool_name=body.tool_name,
        risk=tool["risk"],
        scope={"tenant_id": current_user.tenant_id, "role": current_user.role.value},
        result=result,
        audit_logged_at=logged_at,
    )


@router.put("/settings", response_model=AgentSettingsResponse)
async def update_agent_settings(
    body: AgentSettingsUpdate,
    current_user: TokenPayload = Depends(require_permission(UserPermission.USERS_MANAGE.value)),
    db: AsyncSession = Depends(get_db_session),
):
    tenant = await _load_target_tenant(db, current_user)
    tenant_settings = dict(tenant.settings or {})
    existing = dict(tenant_settings.get("agent_console") or {})

    updated = {
        "enabled": body.enabled,
        "provider_type": body.provider_type,
        "provider_label": body.provider_label,
        "base_url": body.base_url,
        "model_name": body.model_name,
        "region": body.region,
        "allow_data_logging": body.allow_data_logging,
        "allow_model_training": body.allow_model_training,
        "requires_human_confirmation_for_writes": body.requires_human_confirmation_for_writes,
        "allowed_tools": _normalize_allowed_tools(body.allowed_tools),
    }
    if body.api_key:
        updated["api_key"] = body.api_key
    elif existing.get("api_key"):
        updated["api_key"] = existing["api_key"]

    validation_status = None
    validation_message = None
    validation_checked_at = datetime.now(UTC)
    if updated.get("provider_type") and updated.get("model_name") and updated.get("api_key"):
        validator = AgentModelService(updated)
        try:
            validation = await validator.validate_configuration()
        except HTTPException as exc:
            detail = str(exc.detail or "Model validation failed")
            raise HTTPException(
                status_code=400, detail=f"Model validation failed: {detail}"
            ) from exc
        validation_status = validation.get("status") or "valid"
        validation_message = validation.get("message") or None

    updated["validation_status"] = validation_status
    updated["validation_message"] = validation_message
    updated["validation_checked_at"] = (
        validation_checked_at.isoformat() if validation_status else None
    )

    tenant_settings["agent_console"] = updated
    tenant.settings = tenant_settings
    await db.flush()

    payload = _settings_payload(tenant)
    return AgentSettingsResponse(**payload, tool_catalog=TOOL_CATALOG)
