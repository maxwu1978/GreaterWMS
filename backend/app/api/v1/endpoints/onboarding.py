"""Client onboarding wizard — one API call to set up a new client completely."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.plan_limits import check_limit
from app.core.security import TokenPayload, UserRole, hash_password
from app.models.billing import RateCard
from app.models.client import Client
from app.models.inventory import SKU
from app.models.tenant import User

router = APIRouter()


class SKUInput(BaseModel):
    sku_code: str
    name: str
    barcode: str | None = None
    weight_kg: float | None = None


class OnboardClientRequest(BaseModel):
    # Client info
    client_name: str
    client_code: str
    contact_email: str | None = None
    # Portal user (optional)
    portal_email: str | None = None
    portal_password: str | None = None
    portal_name: str | None = None
    # SKUs (optional)
    skus: list[SKUInput] | None = None
    # Rate card (optional)
    rate_rules: dict | None = None


@router.post("/client")
async def onboard_client(
    body: OnboardClientRequest,
    _limits=Depends(check_limit("clients")),
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    One-click new client onboarding wizard.
    Creates client + portal user + SKUs + rate card in one call.
    """
    results = {"steps": []}

    # 1. Create client
    client = Client(
        tenant_id=current_user.tenant_id,
        name=body.client_name,
        code=body.client_code,
        contact_email=body.contact_email,
        billing_enabled=True,
        portal_access=body.portal_email is not None,
    )
    db.add(client)
    await db.flush()
    results["client_id"] = client.id
    results["steps"].append({"step": "client", "status": "created", "name": body.client_name})

    # 2. Create portal user
    if body.portal_email and body.portal_password:
        user = User(
            tenant_id=current_user.tenant_id,
            email=body.portal_email,
            hashed_password=hash_password(body.portal_password),
            full_name=body.portal_name or body.client_name,
            role="client_viewer",
            client_id=client.id,
        )
        db.add(user)
        results["steps"].append(
            {"step": "portal_user", "status": "created", "email": body.portal_email}
        )

    # 3. Create SKUs
    if body.skus:
        for s in body.skus:
            db.add(
                SKU(
                    tenant_id=current_user.tenant_id,
                    client_id=client.id,
                    sku_code=s.sku_code,
                    name=s.name,
                    barcode=s.barcode,
                    weight_kg=s.weight_kg,
                )
            )
        results["steps"].append({"step": "skus", "status": "created", "count": len(body.skus)})

    # 4. Create rate card
    if body.rate_rules:
        db.add(
            RateCard(
                tenant_id=current_user.tenant_id,
                client_id=client.id,
                name=f"{body.client_name} Standard Rate",
                effective_from=date.today(),
                rules=body.rate_rules,
            )
        )
        results["steps"].append({"step": "rate_card", "status": "created"})

    await db.flush()
    results["success"] = True
    results["message"] = f"Client '{body.client_name}' fully onboarded"
    return results
