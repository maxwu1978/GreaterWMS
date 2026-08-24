"""Shipping label API — rate shopping, label generation, packing slip."""

import base64
import io
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.inventory import SKU
from app.models.order import OutboundOrder, OutboundOrderLine
from app.services.shipping_label_service import ShippingLabelService

router = APIRouter()


class BuyLabelRequest(BaseModel):
    order_id: str
    rate_id: str | None = None


def _pdf_text(value: object | None) -> str:
    return escape(str(value or ""))


def _packing_slip_included_quantity(line: OutboundOrderLine) -> int:
    return int(line.quantity_shipped or line.quantity_picked or 0)


@router.get("/rates/{order_id}")
async def get_shipping_rates(
    order_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Get shipping rates from UPS/FedEx/USPS for an order."""
    svc = ShippingLabelService(db, current_user.tenant_id)
    return await svc.get_rates(order_id)


@router.post("/buy-label")
async def buy_shipping_label(
    body: BuyLabelRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Purchase a shipping label. Returns label PDF (base64) + tracking number."""
    svc = ShippingLabelService(db, current_user.tenant_id)
    return await svc.buy_label(body.order_id, body.rate_id)


@router.get("/label/{order_id}/pdf")
async def download_label_pdf(
    order_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Download shipping label as PDF."""
    svc = ShippingLabelService(db, current_user.tenant_id)
    result = await svc.buy_label(order_id)
    if not result.get("success"):
        return result

    pdf_b64 = result.get("label_pdf_base64", "")
    if pdf_b64:
        return Response(
            content=base64.b64decode(pdf_b64),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="label-{order_id[:8]}.pdf"'},
        )
    return {"error": "No label generated"}


@router.get("/packing-slip/{order_id}/pdf")
async def download_packing_slip(
    order_id: str,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """Generate and download packing slip PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context required")

    result = await db.execute(
        select(OutboundOrder).where(
            OutboundOrder.id == order_id,
            OutboundOrder.tenant_id == current_user.tenant_id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    lines_result = await db.execute(
        select(OutboundOrderLine, SKU)
        .join(SKU, SKU.id == OutboundOrderLine.sku_id)
        .where(
            OutboundOrderLine.order_id == order_id,
            OutboundOrderLine.tenant_id == order.tenant_id,
            SKU.tenant_id == order.tenant_id,
        )
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>PACKING SLIP</b>", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Order: <b>{_pdf_text(order.order_number)}</b>", styles["Normal"]))
    elements.append(Paragraph(f"Ship To: {_pdf_text(order.ship_to_name)}", styles["Normal"]))
    addr = order.ship_to_address or {}
    elements.append(
        Paragraph(
            _pdf_text(
                f"{addr.get('street', '')} {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zip', '')}"
            ),
            styles["Normal"],
        )
    )
    if order.tracking_number:
        elements.append(Paragraph(f"Tracking: {_pdf_text(order.tracking_number)}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    table_data: list[list[object]] = [["SKU", "Product", "Qty Ordered", "Qty Included"]]
    for line, sku in lines_result.all():
        table_data.append(
            [
                Paragraph(_pdf_text(sku.sku_code), styles["Normal"]),
                Paragraph(_pdf_text(sku.name), styles["Normal"]),
                str(line.quantity_ordered),
                str(_packing_slip_included_quantity(line)),
            ]
        )

    t = Table(table_data, colWidths=[100, 250, 80, 80])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(t)
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Thank you for your business!", styles["Normal"]))

    doc.build(elements)
    safe_order_number = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in order.order_number
    ) or order_id[:8]
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="packing-slip-{safe_order_number}.pdf"'
        },
    )
