"""Import all models so Alembic can discover them."""

from app.models.agent_evidence import AgentEvidence
from app.models.base import Base
from app.models.billing import BillingLineItem, BillingPeriod, Invoice, RateCard
from app.models.client import Client
from app.models.idempotency import IdempotencyRecord
from app.models.inventory import SKU, Inventory, InventoryTransaction
from app.models.kit import Kit, KitComponent
from app.models.mail_task import MailAttachment, MailMessage, MailTask, MailTaskApproval
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    OutboundOrder,
    OutboundOrderLine,
    ReceivingLabel,
    ReceivingObservedCode,
)
from app.models.pack_list import PackListDocument, PackListLine
from app.models.returns import ReturnOrder, ReturnOrderLine
from app.models.subscription import PlanTier, Subscription
from app.models.task import PickAllocation, PutawayAllocation, Task
from app.models.tenant import Tenant, User
from app.models.warehouse import Location, Warehouse, Zone
from app.models.wcs import WcsTaskBinding

__all__ = [
    "Base",
    "AgentEvidence",
    "Tenant",
    "User",
    "Client",
    "Warehouse",
    "Zone",
    "Location",
    "WcsTaskBinding",
    "SKU",
    "Inventory",
    "InventoryTransaction",
    "IdempotencyRecord",
    "InboundOrder",
    "InboundOrderLine",
    "InboundPackage",
    "ReceivingLabel",
    "ReceivingObservedCode",
    "PackListDocument",
    "PackListLine",
    "MailMessage",
    "MailTask",
    "MailAttachment",
    "MailTaskApproval",
    "HandlingUnit",
    "OutboundOrder",
    "OutboundOrderLine",
    "Task",
    "PutawayAllocation",
    "PickAllocation",
    "RateCard",
    "BillingPeriod",
    "BillingLineItem",
    "Invoice",
    "PlanTier",
    "Subscription",
    "Kit",
    "KitComponent",
    "ReturnOrder",
    "ReturnOrderLine",
]
