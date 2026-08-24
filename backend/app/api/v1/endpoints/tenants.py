"""Tenant management endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.tenant import Tenant

router = APIRouter()


class TenantCreate(BaseModel):
    name: str
    code: str
    contact_email: str
    contact_phone: str | None = None
    plan_tier: str = "starter"


class TenantResponse(BaseModel):
    id: str
    name: str
    code: str
    contact_email: str
    contact_phone: str | None = None
    address: dict | None = None
    plan_tier: str
    is_active: bool


class CurrentTenantResponse(TenantResponse):
    settings: dict


class TenantSettingsUpdate(BaseModel):
    business_mode: str | None = None
    billing_profile: dict | None = None


class ReceivingCodeRuleSettings(BaseModel):
    prefix: str = "RCV"
    separator: str = "-"
    include_order_number: bool = True
    sequence_padding: int = 3
    uppercase: bool = True


class ReceivingCodeRuleResponse(ReceivingCodeRuleSettings):
    sample_code: str


class ReceivingLabelTemplateSettings(BaseModel):
    fields: list[str] = [
        "order_number",
        "sku_code",
        "expected_qty",
        "tracking_number",
    ]
    show_field_labels: bool = True


class ReceivingLabelTemplateResponse(ReceivingLabelTemplateSettings):
    available_fields: list[str]


def _receiving_code_defaults() -> dict:
    return {
        "prefix": "RCV",
        "separator": "-",
        "include_order_number": True,
        "sequence_padding": 3,
        "uppercase": True,
    }


def _receiving_label_template_defaults() -> dict:
    return {
        "fields": [
            "order_number",
            "sku_code",
            "expected_qty",
            "tracking_number",
        ],
        "show_field_labels": True,
    }


def _receiving_label_template_fields() -> list[str]:
    return [
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


def _normalize_order_component(order_number: str, uppercase: bool) -> str:
    raw = order_number.upper() if uppercase else order_number
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "INBOUND"


def _compose_receiving_code(order_number: str, sequence: int, settings_payload: dict) -> str:
    prefix_value = settings_payload.get("prefix")
    prefix = str(prefix_value if prefix_value is not None else "RCV").strip() or "RCV"
    separator_value = settings_payload.get("separator")
    separator = str(separator_value) if separator_value is not None else "-"
    include_order_number = bool(settings_payload.get("include_order_number", True))
    sequence_padding = max(1, min(int(settings_payload.get("sequence_padding", 3)), 8))
    uppercase = bool(settings_payload.get("uppercase", True))

    parts: list[str] = [prefix.upper() if uppercase else prefix]
    if include_order_number:
        parts.append(_normalize_order_component(order_number, uppercase))
    parts.append(f"{sequence:0{sequence_padding}d}")
    return separator.join(part for part in parts if part)


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Tenant).where(Tenant.is_active == True))  # noqa: E712
    return [
        TenantResponse(
            id=t.id,
            name=t.name,
            code=t.code,
            contact_email=t.contact_email,
            contact_phone=t.contact_phone,
            address=t.address,
            plan_tier=t.plan_tier,
            is_active=t.is_active,
        )
        for t in result.scalars()
    ]


class TenantApprovalItem(BaseModel):
    id: str
    name: str
    code: str
    contact_email: str
    plan_tier: str
    approval_status: str
    created_at: str


class TenantApprovalRequest(BaseModel):
    action: str  # "approve" | "reject"


@router.get("/approvals", response_model=list[TenantApprovalItem])
async def list_tenant_approvals(
    approval_status: str = "pending",
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Registration approval queue for platform admins."""
    if approval_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Unsupported approval status filter")
    result = await db.execute(
        select(Tenant)
        .where(Tenant.approval_status == approval_status)
        .order_by(Tenant.created_at.asc())
    )
    return [
        TenantApprovalItem(
            id=t.id,
            name=t.name,
            code=t.code,
            contact_email=t.contact_email,
            plan_tier=t.plan_tier,
            approval_status=t.approval_status,
            created_at=t.created_at.isoformat() if t.created_at else "",
        )
        for t in result.scalars()
    ]


@router.post("/{tenant_id}/approval", response_model=TenantApprovalItem)
async def decide_tenant_approval(
    tenant_id: str,
    body: TenantApprovalRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Approve or reject a pending workspace registration."""
    if body.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.approval_status = "approved" if body.action == "approve" else "rejected"
    tenant.approved_at = datetime.now(UTC)
    tenant.approved_by = current_user.sub
    await db.flush()
    return TenantApprovalItem(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        contact_email=tenant.contact_email,
        plan_tier=tenant.plan_tier,
        approval_status=tenant.approval_status,
        created_at=tenant.created_at.isoformat() if tenant.created_at else "",
    )


@router.get("/current", response_model=CurrentTenantResponse)
async def get_current_tenant(
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return CurrentTenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        contact_email=tenant.contact_email,
        contact_phone=tenant.contact_phone,
        address=tenant.address,
        plan_tier=tenant.plan_tier,
        is_active=tenant.is_active,
        settings=tenant.settings or {},
    )


@router.patch("/current/settings", response_model=CurrentTenantResponse)
async def update_current_tenant_settings(
    body: TenantSettingsUpdate,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")
    if body.business_mode is not None and body.business_mode not in {"3pl", "self_use"}:
        raise HTTPException(status_code=400, detail="Unsupported business mode")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    next_settings = dict(tenant.settings or {})
    if body.business_mode is not None:
        next_settings["business_mode"] = body.business_mode
    if body.billing_profile is not None:
        next_settings["billing_profile"] = body.billing_profile
    tenant.settings = next_settings
    await db.flush()

    return CurrentTenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        contact_email=tenant.contact_email,
        contact_phone=tenant.contact_phone,
        address=tenant.address,
        plan_tier=tenant.plan_tier,
        is_active=tenant.is_active,
        settings=tenant.settings or {},
    )


@router.get("/current/receiving-code-rules", response_model=ReceivingCodeRuleResponse)
async def get_current_receiving_code_rules(
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    payload = {
        **_receiving_code_defaults(),
        **dict((tenant.settings or {}).get("receiving_code_rules") or {}),
    }
    return ReceivingCodeRuleResponse(
        **payload,
        sample_code=_compose_receiving_code("INB-20260416", 1, payload),
    )


@router.patch("/current/receiving-code-rules", response_model=ReceivingCodeRuleResponse)
async def update_current_receiving_code_rules(
    body: ReceivingCodeRuleSettings,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")
    if body.separator not in {"-", "_", ""}:
        raise HTTPException(status_code=400, detail="Unsupported separator")
    if body.sequence_padding < 1 or body.sequence_padding > 8:
        raise HTTPException(status_code=400, detail="Sequence padding must be between 1 and 8")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    next_settings = dict(tenant.settings or {})
    next_settings["receiving_code_rules"] = body.model_dump()
    tenant.settings = next_settings
    await db.flush()

    payload = {
        **_receiving_code_defaults(),
        **body.model_dump(),
    }
    return ReceivingCodeRuleResponse(
        **payload,
        sample_code=_compose_receiving_code("INB-20260416", 1, payload),
    )


@router.get("/current/receiving-label-template", response_model=ReceivingLabelTemplateResponse)
async def get_current_receiving_label_template(
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    payload = {
        **_receiving_label_template_defaults(),
        **dict((tenant.settings or {}).get("receiving_label_template") or {}),
    }
    allowed = set(_receiving_label_template_fields())
    payload["fields"] = [
        field for field in payload.get("fields", []) if field in allowed
    ] or _receiving_label_template_defaults()["fields"]
    return ReceivingLabelTemplateResponse(
        **payload,
        available_fields=_receiving_label_template_fields(),
    )


@router.patch("/current/receiving-label-template", response_model=ReceivingLabelTemplateResponse)
async def update_current_receiving_label_template(
    body: ReceivingLabelTemplateSettings,
    current_user: TokenPayload = Depends(
        require_role(UserRole.TENANT_ADMIN, UserRole.PLATFORM_ADMIN)
    ),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    allowed = set(_receiving_label_template_fields())
    cleaned_fields = [field for field in body.fields if field in allowed]
    if not cleaned_fields:
        raise HTTPException(status_code=400, detail="At least one printable field must be selected")

    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    next_settings = dict(tenant.settings or {})
    next_settings["receiving_label_template"] = {
        "fields": cleaned_fields,
        "show_field_labels": body.show_field_labels,
    }
    tenant.settings = next_settings
    await db.flush()

    return ReceivingLabelTemplateResponse(
        fields=cleaned_fields,
        show_field_labels=body.show_field_labels,
        available_fields=_receiving_label_template_fields(),
    )


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    # Check code uniqueness
    existing = await db.execute(select(Tenant).where(Tenant.code == body.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Tenant code '{body.code}' already exists")

    tenant = Tenant(
        name=body.name,
        code=body.code,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        plan_tier=body.plan_tier,
    )
    db.add(tenant)
    await db.flush()
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        code=tenant.code,
        contact_email=tenant.contact_email,
        contact_phone=tenant.contact_phone,
        address=tenant.address,
        plan_tier=tenant.plan_tier,
        is_active=tenant.is_active,
    )
