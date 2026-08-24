"""Integration API — Shopify webhooks, integration config, order sync."""

import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import apply_session_context, get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.integration_service import ShopifyService
from app.services.wcs_adapter_service import WcsAdapterError, WcsAdapterService

router = APIRouter()


class IntegrationConfig(BaseModel):
    """Configure a Shopify or Amazon integration for a client."""

    client_id: str
    platform: str  # "shopify" or "amazon"
    config: dict  # platform-specific credentials


class ShopifyWebhookPayload(BaseModel):
    """Shopify sends order data as JSON."""

    id: int
    name: str
    line_items: list[dict]
    shipping_address: dict | None = None


class WcsConfigRequest(BaseModel):
    """Tenant warehouse-level WCS adapter config."""

    warehouse_id: str
    base_url: str
    callback_url: str | None = None
    username: str | None = None
    password: str | None = None
    access_token: str | None = None
    scode: str | None = None
    default_pallet_spec: str | None = None
    task_type_map: dict[str, str] | None = None


class WcsConfigUpdateRequest(BaseModel):
    """Partial WCS adapter config update that preserves omitted secrets."""

    warehouse_id: str
    base_url: str | None = None
    callback_url: str | None = None
    username: str | None = None
    password: str | None = None
    access_token: str | None = None
    scode: str | None = None
    default_pallet_spec: str | None = None
    task_type_map: dict[str, str] | None = None
    reason: str | None = None


class WcsDispatchRequest(BaseModel):
    """Dispatch an existing WMS task to WCS."""

    callback_url: str | None = None


class WcsCallbackReplayRequest(BaseModel):
    """Replay a WCS callback payload without mutating task or inventory state."""

    payload: dict


class WcsCertificationTaskRequest(BaseModel):
    """Preview or create a sandbox certification move task for WCS callback testing."""

    warehouse_id: str
    source_location_id: str
    destination_location_id: str
    sku_id: str
    quantity: int = Field(default=1, ge=1)
    certification_scope: str = "normal_path_sandbox_certification"
    reference_id: str | None = None
    lpn_prefix: str | None = "WCS-SBX-CERT"
    confirm_create: bool = False


class WcsReadyConfigRequest(BaseModel):
    """Update WCS ready-AGV vehicle config."""

    warehouse_id: str
    ready_sign: str
    api_sign: int | str
    api_num: int | str


class WcsQualityCompleteRequest(BaseModel):
    """Notify WCS that a quality step is complete."""

    warehouse_id: str
    wtaskstep_tid: str | None = None
    wtaskinfo_psn: str | None = None
    quality_status: str | None = None
    unqualified_buffer: str | None = None
    params: str | dict | None = None


class WcsPointMapping(BaseModel):
    """Map a WMS location to a WCS executable point."""

    location_id: str | None = None
    location_barcode: str | None = None
    point_code: str | None = None
    point_type: str | None = None
    point_role: str | None = None
    point_name: str | None = None
    buffer_code: str | None = None
    aisle_group: str | None = None
    station_role: str | None = None
    agv_reachable: bool = True
    wcs_metadata: dict | None = None


class WcsPointMappingRequest(BaseModel):
    """Replace warehouse WCS point mappings."""

    warehouse_id: str
    mappings: list[WcsPointMapping]
    merge: bool = False


class WcsPointMappingImportRequest(BaseModel):
    """Import WCS point mappings from JSON rows."""

    warehouse_id: str
    mappings: list[WcsPointMapping]
    merge: bool = False
    validate_only: bool = False


# --- Configuration ---


@router.post("/configure")
async def configure_integration(
    body: IntegrationConfig,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Save integration credentials for a client."""
    result = await db.execute(select(Client).where(Client.id == body.client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    settings = client.settings or {}
    settings[body.platform] = body.config
    client.settings = settings

    await db.flush()
    return {"status": "configured", "platform": body.platform, "client_id": body.client_id}


@router.get("/status/{client_id}")
async def integration_status(
    client_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Check which integrations are configured for a client."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    settings = client.settings or {}
    return {
        "client_id": client_id,
        "shopify": {
            "configured": "shopify" in settings,
            "shop_domain": settings.get("shopify", {}).get("shop_domain"),
        },
        "amazon": {
            "configured": "amazon" in settings,
            "marketplace": settings.get("amazon", {}).get("marketplace_id"),
        },
    }


# --- WCS Adapter ---


async def _tenant_warehouse(
    db: AsyncSession,
    tenant_id: str,
    warehouse_id: str,
) -> Warehouse:
    warehouse = await db.scalar(
        select(Warehouse).where(
            Warehouse.tenant_id == tenant_id,
            Warehouse.id == warehouse_id,
        )
    )
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return warehouse


def _mapping_dicts(mappings: list[WcsPointMapping]) -> list[dict]:
    return [mapping.model_dump() for mapping in mappings]


def _point_mappings_csv(items: list[dict]) -> str:
    output = StringIO()
    fieldnames = [
        "location_id",
        "location_barcode",
        "location_type",
        "aisle",
        "rack",
        "level",
        "position",
        "wms_agv_accessible",
        "point_code",
        "point_type",
        "point_role",
        "point_name",
        "buffer_code",
        "aisle_group",
        "station_role",
        "agv_reachable",
        "wcs_metadata",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in items:
        writer.writerow({field: item.get(field) for field in fieldnames})
    return output.getvalue()


def _wcs_error_detail(exc: WcsAdapterError) -> dict | str:
    return exc.detail if getattr(exc, "detail", None) else str(exc)


@router.get("/wcs/config/{warehouse_id}")
async def read_wcs_config(
    warehouse_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Read redacted WCS config and point mappings for a warehouse."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).read_config(warehouse_id)
    except WcsAdapterError as exc:
        raise HTTPException(status_code=404, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/configure")
async def configure_wcs(
    body: WcsConfigRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Save WCS adapter settings for a warehouse."""
    warehouse = await _tenant_warehouse(db, current_user.tenant_id, body.warehouse_id)

    address = dict(warehouse.address or {})
    existing_wcs = dict(address.get("_wcs") or {})
    address["_wcs"] = {
        "base_url": body.base_url.rstrip("/"),
        "callback_url": body.callback_url,
        "username": body.username,
        "password": body.password,
        "access_token": body.access_token,
        "scode": body.scode or warehouse.code,
        "default_pallet_spec": body.default_pallet_spec,
        "task_type_map": body.task_type_map or {},
        "point_mappings": existing_wcs.get("point_mappings") or {},
    }
    warehouse.address = address
    await db.flush()
    return {"status": "configured", "warehouse_id": warehouse.id, "wcs_base_url": body.base_url}


@router.post("/wcs/configure/preview")
async def preview_wcs_config_update(
    body: WcsConfigUpdateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Preview a WCS config update without writing or calling external WCS."""
    changes = body.model_dump(exclude={"warehouse_id", "reason"}, exclude_unset=True)
    try:
        return await WcsAdapterService(db, current_user.tenant_id).preview_config_update(
            body.warehouse_id,
            changes,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/configure/update")
async def update_wcs_config(
    body: WcsConfigUpdateRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Apply a reviewed WCS config update without exposing secret values."""
    changes = body.model_dump(exclude={"warehouse_id", "reason"}, exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No WCS config changes were provided")
    try:
        return await WcsAdapterService(db, current_user.tenant_id).update_config(
            body.warehouse_id,
            changes,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.get("/wcs/bindings")
async def list_wcs_bindings(
    warehouse_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Read WCS task bindings for dispatch and callback diagnosis."""
    return await WcsAdapterService(db, current_user.tenant_id).list_bindings(
        warehouse_id=warehouse_id,
        task_id=task_id,
        status=status,
        limit=limit,
    )


@router.get("/wcs/point-mappings")
async def list_wcs_point_mappings(
    warehouse_id: str = Query(...),
    include_unmapped: bool = False,
    format: str = Query("json", pattern="^(json|csv)$"),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """List or export WCS point-code mappings for a warehouse."""
    warehouse = await _tenant_warehouse(db, current_user.tenant_id, warehouse_id)
    result = await WcsAdapterService(db, current_user.tenant_id).list_point_mappings(
        warehouse,
        include_unmapped=include_unmapped,
    )
    if format == "csv":
        return Response(
            content=_point_mappings_csv(result["items"]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="wcs-point-mappings-{warehouse_id}.csv"'
            },
        )
    return result


@router.post("/wcs/point-mappings/validate")
async def validate_wcs_point_mappings(
    body: WcsPointMappingRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Validate WCS point mappings without writing them."""
    warehouse = await _tenant_warehouse(db, current_user.tenant_id, body.warehouse_id)
    return await WcsAdapterService(db, current_user.tenant_id).validate_point_mappings(
        warehouse,
        _mapping_dicts(body.mappings),
    )


@router.post("/wcs/point-mappings/import")
async def import_wcs_point_mappings(
    body: WcsPointMappingImportRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Validate or import WCS point mappings."""
    warehouse = await _tenant_warehouse(db, current_user.tenant_id, body.warehouse_id)
    service = WcsAdapterService(db, current_user.tenant_id)
    mappings = _mapping_dicts(body.mappings)
    if body.validate_only:
        return await service.validate_point_mappings(warehouse, mappings)
    try:
        return await service.replace_point_mappings(warehouse, mappings, merge=body.merge)
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/point-mappings")
async def configure_wcs_point_mappings(
    body: WcsPointMappingRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Save WCS point-code mappings for a warehouse."""
    warehouse = await _tenant_warehouse(db, current_user.tenant_id, body.warehouse_id)
    try:
        return await WcsAdapterService(db, current_user.tenant_id).replace_point_mappings(
            warehouse,
            _mapping_dicts(body.mappings),
            merge=body.merge,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/tasks/{task_id}/dispatch/preview")
async def preview_wcs_dispatch(
    task_id: str,
    body: WcsDispatchRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Dry-run WCS dispatch gate and payload generation without calling WCS."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).preview_dispatch_task(
            task_id,
            callback_url=body.callback_url,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/certification-tasks/preview")
async def preview_wcs_certification_task(
    body: WcsCertificationTaskRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Preview a tenant-scoped sandbox certification move task without writing task rows."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).preview_certification_task(
            warehouse_id=body.warehouse_id,
            source_location_id=body.source_location_id,
            destination_location_id=body.destination_location_id,
            sku_id=body.sku_id,
            quantity=body.quantity,
            certification_scope=body.certification_scope,
            reference_id=body.reference_id,
            lpn_prefix=body.lpn_prefix,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/certification-tasks/create")
async def create_wcs_certification_task(
    body: WcsCertificationTaskRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a sandbox-only certification move task after explicit confirm flag review."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).create_certification_task(
            warehouse_id=body.warehouse_id,
            source_location_id=body.source_location_id,
            destination_location_id=body.destination_location_id,
            sku_id=body.sku_id,
            quantity=body.quantity,
            certification_scope=body.certification_scope,
            reference_id=body.reference_id,
            lpn_prefix=body.lpn_prefix,
            confirm_create=body.confirm_create,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/tasks/{task_id}/dispatch")
async def dispatch_wcs_task(
    task_id: str,
    body: WcsDispatchRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a WCS transport task from an existing WMS task."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).dispatch_task(
            task_id,
            callback_url=body.callback_url,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/webhook/{tenant_id}/taskfinish/replay")
async def replay_wcs_taskfinish_webhook(
    tenant_id: str,
    body: WcsCallbackReplayRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Replay WCS task lifecycle callback mapping without applying it."""
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cannot replay callbacks for another tenant")
    try:
        return await WcsAdapterService(db, tenant_id).preview_task_callback(body.payload)
    except WcsAdapterError as exc:
        raise HTTPException(status_code=404, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/ready-config")
async def update_wcs_ready_config(
    body: WcsReadyConfigRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Call WCS ready-vehicle config update for outbound AGV preparation."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).update_ready_config(
            body.warehouse_id,
            ready_sign=body.ready_sign,
            api_sign=body.api_sign,
            api_num=body.api_num,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/ready-config/preview")
async def preview_wcs_ready_config(
    body: WcsReadyConfigRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Preview WCS ready-vehicle config payload without calling WCS."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).preview_ready_config(
            body.warehouse_id,
            ready_sign=body.ready_sign,
            api_sign=body.api_sign,
            api_num=body.api_num,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/quality-complete")
async def complete_wcs_quality(
    body: WcsQualityCompleteRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Call WCS after WMS quality inspection is complete."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).complete_quality(
            body.warehouse_id,
            wtaskstep_tid=body.wtaskstep_tid,
            wtaskinfo_psn=body.wtaskinfo_psn,
            quality_status=body.quality_status,
            unqualified_buffer=body.unqualified_buffer,
            params=body.params,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/quality-complete/preview")
async def preview_wcs_quality(
    body: WcsQualityCompleteRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Preview WCS quality completion payload without calling WCS."""
    try:
        return await WcsAdapterService(db, current_user.tenant_id).preview_quality_complete(
            body.warehouse_id,
            wtaskstep_tid=body.wtaskstep_tid,
            wtaskinfo_psn=body.wtaskinfo_psn,
            quality_status=body.quality_status,
            unqualified_buffer=body.unqualified_buffer,
            params=body.params,
        )
    except WcsAdapterError as exc:
        raise HTTPException(status_code=400, detail=_wcs_error_detail(exc)) from exc


@router.post("/wcs/webhook/{tenant_id}/taskfinish")
async def wcs_taskfinish_webhook(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Receive WCS task lifecycle callbacks from the configured return URL."""
    try:
        await apply_session_context(db, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Tenant not found") from exc
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    payload = await request.json()
    try:
        return await WcsAdapterService(db, tenant_id).apply_task_callback(payload)
    except WcsAdapterError as exc:
        raise HTTPException(status_code=404, detail=_wcs_error_detail(exc)) from exc


# --- Shopify Webhook ---


@router.post("/shopify/webhook/{tenant_id}/{client_id}")
async def shopify_order_webhook(
    tenant_id: str,
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Shopify order.created webhook receiver.

    Webhook URL configured in Shopify:
    https://api.wmsquickstart.com/api/v1/integrations/shopify/webhook/{tenant_id}/{client_id}
    """
    body = await request.body()
    payload = await request.json()

    # Load client to get webhook secret and default warehouse
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    shopify_config = (client.settings or {}).get("shopify", {})
    webhook_secret = shopify_config.get("webhook_secret")
    warehouse_id = shopify_config.get("default_warehouse_id")

    # Verify webhook signature if secret is configured
    if webhook_secret:
        hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
        svc = ShopifyService(db, tenant_id, client_id)
        if not svc.verify_webhook(body, hmac_header, webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not warehouse_id:
        raise HTTPException(status_code=400, detail="Default warehouse not configured for Shopify")

    svc = ShopifyService(db, tenant_id, client_id)
    order = await svc.process_order_webhook(payload, warehouse_id)

    return {"status": "imported", "order_id": order.id, "order_number": order.order_number}
