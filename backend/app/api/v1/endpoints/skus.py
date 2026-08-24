"""SKU management endpoints — CRUD for product definitions."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_role
from app.core.pagination import PaginationParams, paginate_window
from app.core.plan_limits import check_limit
from app.core.security import TokenPayload, UserRole
from app.models.inventory import SKU

router = APIRouter()


class SKUCreate(BaseModel):
    client_id: str
    sku_code: str
    name: str
    barcode: str | None = None
    description: str | None = None
    weight_kg: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    requires_lot: bool = False
    requires_expiry: bool = False
    is_hazmat: bool = False
    units_per_case: int | None = None
    cases_per_pallet: int | None = None


class SKUResponse(BaseModel):
    id: str
    client_id: str
    sku_code: str
    name: str
    barcode: str | None
    weight_kg: float | None
    requires_lot: bool
    requires_expiry: bool


@router.get("/")
async def list_skus(
    client_id: str | None = None,
    page: PaginationParams = Depends(),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(SKU)
    if current_user.role != UserRole.PLATFORM_ADMIN:
        if not current_user.tenant_id:
            raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")
        query = query.where(SKU.tenant_id == current_user.tenant_id)
    if current_user.role == UserRole.CLIENT_VIEWER and current_user.client_id:
        query = query.where(SKU.client_id == current_user.client_id)
    elif client_id:
        query = query.where(SKU.client_id == client_id)
    query = query.order_by(SKU.sku_code)

    result = await paginate_window(db, query, page)
    result["items"] = [
        SKUResponse(
            id=s.id,
            client_id=s.client_id,
            sku_code=s.sku_code,
            name=s.name,
            barcode=s.barcode,
            weight_kg=float(s.weight_kg) if s.weight_kg else None,
            requires_lot=s.requires_lot,
            requires_expiry=s.requires_expiry,
        )
        for s in result["items"]
    ]
    return result


@router.post("/", response_model=SKUResponse, status_code=201)
async def create_sku(
    body: SKUCreate,
    _limits=Depends(check_limit("skus")),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    # Check uniqueness within tenant+client
    existing = await db.execute(
        select(SKU).where(
            SKU.client_id == body.client_id,
            SKU.sku_code == body.sku_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail=f"SKU '{body.sku_code}' already exists for this client"
        )

    sku = SKU(
        tenant_id=current_user.tenant_id,
        client_id=body.client_id,
        sku_code=body.sku_code,
        name=body.name,
        barcode=body.barcode,
        description=body.description,
        weight_kg=body.weight_kg,
        length_cm=body.length_cm,
        width_cm=body.width_cm,
        height_cm=body.height_cm,
        requires_lot=body.requires_lot,
        requires_expiry=body.requires_expiry,
        is_hazmat=body.is_hazmat,
        units_per_case=body.units_per_case,
        cases_per_pallet=body.cases_per_pallet,
    )
    db.add(sku)
    await db.flush()
    return SKUResponse(
        id=sku.id,
        client_id=sku.client_id,
        sku_code=sku.sku_code,
        name=sku.name,
        barcode=sku.barcode,
        weight_kg=float(sku.weight_kg) if sku.weight_kg else None,
        requires_lot=sku.requires_lot,
        requires_expiry=sku.requires_expiry,
    )


@router.post("/import-from-shopify")
async def import_skus_from_shopify(
    client_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Bulk import SKUs from a client's Shopify store.
    Reads products via Shopify Admin API and creates SKU records in WMS.
    """
    import httpx

    from app.models.client import Client

    # Get Shopify config
    client_result = await db.execute(select(Client).where(Client.id == client_id))
    client = client_result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    shopify_config = (client.settings or {}).get("shopify")
    if not shopify_config:
        raise HTTPException(status_code=400, detail="Shopify not configured for this client")

    shop = shopify_config["shop_domain"]
    token = shopify_config["access_token"]

    # Fetch products from Shopify
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"https://{shop}/admin/api/2024-01/products.json?limit=250",
            headers={"X-Shopify-Access-Token": token},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Shopify API error: {resp.status_code}")

    products = resp.json().get("products", [])
    imported = 0
    skipped = 0

    for product in products:
        for variant in product.get("variants", []):
            sku_code = variant.get("sku", "").strip()
            if not sku_code:
                skipped += 1
                continue

            # Check if already exists
            existing = await db.execute(
                select(SKU).where(SKU.client_id == client_id, SKU.sku_code == sku_code)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            sku = SKU(
                tenant_id=current_user.tenant_id,
                client_id=client_id,
                sku_code=sku_code,
                barcode=variant.get("barcode"),
                name=f"{product.get('title', '')} - {variant.get('title', '')}".strip(" -"),
                weight_kg=float(variant.get("weight", 0)) / 1000 if variant.get("weight") else None,
            )
            db.add(sku)
            imported += 1

    await db.flush()
    return {
        "imported": imported,
        "skipped": skipped,
        "total_products": len(products),
    }
