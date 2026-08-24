"""Setup Wizard API — step-by-step or express warehouse configuration."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.setup_wizard_service import SetupWizardService

router = APIRouter()


# ─── Progress ───


@router.get("/progress")
async def setup_progress(
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Check setup completion status — which steps are done."""
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.get_progress()


# ─── Step-by-Step ───


class WarehouseSetup(BaseModel):
    name: str
    code: str | None = None
    address: dict | None = None
    timezone: str = "America/Chicago"


class LocationSetup(BaseModel):
    warehouse_id: str
    aisles: int = 3
    racks_per_aisle: int = 4
    levels: int = 3
    positions_per_level: int = 5
    agv_accessible: bool = False
    aisle_width_m: float = 3.2
    level_height_m: float = 1.5
    level_capacity_kg: float = 1200.0
    level_profiles: list[dict] | None = None


class ClientSetup(BaseModel):
    name: str
    code: str | None = None
    email: str | None = None
    portal_email: str | None = None
    portal_password: str | None = None
    portal_name: str | None = None


class SKUItem(BaseModel):
    sku_code: str
    name: str
    barcode: str | None = None
    weight_kg: float | None = None


class SKUSetup(BaseModel):
    client_id: str
    skus: list[SKUItem]


class BillingSetup(BaseModel):
    client_id: str
    client_name: str = ""
    storage_rate: float = 0.85
    receiving_rate: float = 0.25
    pick_per_order: float = 2.00
    pick_per_line: float = 0.50
    shipping_rate: float = 1.50
    minimum_monthly: float = 200


class TeamMember(BaseModel):
    email: str
    name: str
    password: str  # Required, no default — must be ≥6 chars
    role: str = "operator"


class TeamSetup(BaseModel):
    members: list[TeamMember]


@router.post("/step/warehouse")
async def step_warehouse(
    body: WarehouseSetup,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Step 1: Set up your warehouse facility."""
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.setup_warehouse(body.model_dump())


@router.post("/step/locations")
async def step_locations(
    body: LocationSetup,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Step 2: Generate storage locations automatically."""
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.setup_locations(body.model_dump())


@router.post("/step/client")
async def step_client(
    body: ClientSetup,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Step 3: Add your first client (cargo owner)."""
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.setup_first_client(body.model_dump())


@router.post("/step/skus")
async def step_skus(
    body: SKUSetup,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Step 4: Add products (SKUs) for a client."""
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.setup_skus(body.model_dump())


@router.post("/step/billing")
async def step_billing(
    body: BillingSetup,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Step 5: Set up billing rates for a client."""
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.setup_billing(body.model_dump())


@router.post("/step/team")
async def step_team(
    body: TeamSetup,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """Step 6: Invite team members."""
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.setup_team(body.model_dump())


# ─── Express Setup ───


class QuickSetup(BaseModel):
    """Answer all questions at once — system builds everything."""

    # Warehouse
    warehouse_name: str = "My Warehouse"
    warehouse_address: dict | None = None
    timezone: str = "America/Chicago"
    aisles: int = 3
    racks_per_aisle: int = 4
    levels: int = 3
    positions_per_level: int = 5
    agv_accessible: bool = False
    aisle_width_m: float = 3.2
    level_height_m: float = 1.5
    level_capacity_kg: float = 1200.0
    level_profiles: list[dict] | None = None
    # First client
    client_name: str | None = None
    client_email: str | None = None
    client_portal_email: str | None = None
    client_portal_password: str | None = None
    # SKUs
    skus: list[SKUItem] | None = None
    # Billing
    storage_rate: float | None = None
    receiving_rate: float | None = None
    pick_per_order: float | None = None
    pick_per_line: float | None = None
    minimum_monthly: float | None = None
    # Team
    team_members: list[TeamMember] | None = None


@router.post("/quick")
async def quick_setup(
    body: QuickSetup,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Express setup — answer all questions in one form, system builds everything.
    Creates warehouse + locations + client + SKUs + billing + team in one call.
    """
    svc = SetupWizardService(db, current_user.tenant_id)
    return await svc.quick_setup(body.model_dump())
