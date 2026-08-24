"""
Batch Operations API — bulk label printing and bulk billing.

These are the "一键" operations that a warehouse supervisor needs daily.
"""

import base64
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.order import OutboundOrder
from app.services.billing_service import BillingService
from app.services.shipping_label_service import ShippingLabelService

router = APIRouter()


# ═══════════════════════════════════════
# BATCH LABEL PRINTING
# ═══════════════════════════════════════


class BatchLabelRequest(BaseModel):
    order_ids: list[str]


@router.post("/labels")
async def batch_print_labels(
    body: BatchLabelRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Buy shipping labels for multiple orders at once.
    Returns all tracking numbers + combined label PDF.
    """
    svc = ShippingLabelService(db, current_user.tenant_id)
    results = []
    all_pdfs = []

    for order_id in body.order_ids:
        try:
            label = await svc.buy_label(order_id)
            results.append(
                {
                    "order_id": order_id,
                    "success": label.get("success", False),
                    "tracking": label.get("tracking_number"),
                    "carrier": label.get("carrier"),
                    "rate": label.get("rate"),
                }
            )
            pdf_b64 = label.get("label_pdf_base64", "")
            if pdf_b64:
                all_pdfs.append(base64.b64decode(pdf_b64))
        except Exception:
            results.append(
                {
                    "order_id": order_id,
                    "success": False,
                    "error": "Processing failed",
                }
            )

    total_cost = sum(r.get("rate", 0) or 0 for r in results if r.get("success"))
    success_count = sum(1 for r in results if r.get("success"))

    return {
        "total_orders": len(body.order_ids),
        "success_count": success_count,
        "failed_count": len(body.order_ids) - success_count,
        "total_shipping_cost": round(total_cost, 2),
        "labels": results,
    }


@router.post("/labels/auto")
async def batch_print_all_ready(
    warehouse_id: str = "wh-dfw1",
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Auto-print labels for ALL orders that are picked/packed and ready to ship.
    One click → all labels printed.
    """
    result = await db.execute(
        select(OutboundOrder.id).where(
            OutboundOrder.warehouse_id == warehouse_id,
            OutboundOrder.status.in_(["picked", "packed"]),
            OutboundOrder.tracking_number.is_(None),
        )
    )
    order_ids = [row[0] for row in result.all()]

    if not order_ids:
        return {"message": "No orders ready for labels", "count": 0}

    # Reuse the batch endpoint logic
    svc = ShippingLabelService(db, current_user.tenant_id)
    results = []
    for oid in order_ids:
        try:
            label = await svc.buy_label(oid)
            results.append(
                {
                    "order_id": oid,
                    "success": label.get("success", False),
                    "tracking": label.get("tracking_number"),
                    "carrier": label.get("carrier"),
                    "rate": label.get("rate"),
                }
            )
        except Exception:
            results.append({"order_id": oid, "success": False, "error": "Processing failed"})

    total_cost = sum(r.get("rate", 0) or 0 for r in results if r.get("success"))
    return {
        "total_orders": len(order_ids),
        "success_count": sum(1 for r in results if r.get("success")),
        "total_shipping_cost": round(total_cost, 2),
        "labels": results,
    }


# ═══════════════════════════════════════
# BATCH BILLING
# ═══════════════════════════════════════


class BatchBillingRequest(BaseModel):
    period_start: date
    period_end: date
    client_ids: list[str] | None = None  # None = all active clients
    send_email: bool = False  # Email invoices to clients


@router.post("/billing")
async def batch_generate_billing(
    body: BatchBillingRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Generate billing for ALL clients in one click.
    Creates billing periods, calculates charges, and generates invoices.
    """
    svc = BillingService(db, current_user.tenant_id)

    # Get clients
    if body.client_ids:
        client_ids = body.client_ids
    else:
        result = await db.execute(
            select(Client.id, Client.name).where(
                Client.is_active == True,  # noqa
                Client.billing_enabled == True,  # noqa
            )
        )
        clients = result.all()
        client_ids = [c[0] for c in clients]

    results = []
    total_revenue = 0
    invoice_count = 0

    for i, client_id in enumerate(client_ids):
        try:
            # Create billing period
            period = await svc.create_billing_period(
                client_id=client_id,
                period_start=body.period_start,
                period_end=body.period_end,
            )

            # Calculate charges
            charges = await svc.calculate_charges(
                client_id=client_id,
                period_id=period.id,
                period_start=body.period_start,
                period_end=body.period_end,
            )

            # Generate invoice
            invoice_num = f"INV-{body.period_end.strftime('%Y%m')}-{i + 1:03d}"
            invoice = await svc.generate_invoice(
                client_id=client_id,
                period_id=period.id,
                invoice_number=invoice_num,
            )

            total = float(invoice.total_amount)
            total_revenue += total
            invoice_count += 1

            # Get client info
            client_result = await db.execute(select(Client).where(Client.id == client_id))
            client_obj = client_result.scalar_one()
            client_name = client_obj.name

            # Send email to client if requested
            email_sent = False
            if body.send_email and client_obj.contact_email:
                try:
                    from app.services.email_service import email_delivery_enabled, send_survey_email

                    if email_delivery_enabled():
                        charge_summary = "\n".join(
                            f"  {c['charge_type']}: {c['description']} = ${c['total_amount']:.2f}"
                            for c in charges
                            if "error" not in c
                        )
                        await send_survey_email(
                            to_email=client_obj.contact_email,
                            company_name=client_name,
                            contact_name=client_name,
                            contact_email=client_obj.contact_email,
                            summary=f"Invoice {invoice_num}\nPeriod: {body.period_start} to {body.period_end}\n\n{charge_summary}\n\nTotal: ${total:.2f}",
                            pdf_base64="",
                        )
                        email_sent = True
                except Exception:
                    pass

            results.append(
                {
                    "client_id": client_id,
                    "client_name": client_name,
                    "invoice_number": invoice_num,
                    "total_amount": total,
                    "charges_count": len([c for c in charges if "error" not in c]),
                    "email_sent": email_sent,
                    "status": "generated",
                }
            )
        except Exception:
            results.append(
                {
                    "client_id": client_id,
                    "status": "error",
                    "error": "Processing failed",
                }
            )

    return {
        "period": f"{body.period_start} to {body.period_end}",
        "clients_billed": invoice_count,
        "total_revenue": round(total_revenue, 2),
        "invoices": results,
    }
