"""JWT token creation/verification and password hashing."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings


class UserRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    OPERATOR = "operator"
    CLIENT_VIEWER = "client_viewer"


class UserPermission(StrEnum):
    INBOUND_ORDERS_MANAGE = "inbound_orders.manage"
    INBOUND_ORDERS_IMPORT = "inbound_orders.import"
    RECEIVING_EXECUTE = "receiving.execute"
    OUTBOUND_ORDERS_MANAGE = "outbound_orders.manage"
    PICKING_EXECUTE = "picking.execute"
    SHIPPING_EXECUTE = "shipping.execute"
    MASTER_DATA_MANAGE = "master_data.manage"
    USERS_MANAGE = "users.manage"
    BILLING_MANAGE = "billing.manage"
    PLANNER_MANAGE = "planner.manage"
    PORTAL_VIEW = "portal.view"


class TokenPayload(BaseModel):
    sub: str  # user_id
    tenant_id: str | None = None
    client_id: str | None = None  # only for client_viewer role
    role: UserRole
    permissions: list[str] = []
    exp: datetime


def create_access_token(
    user_id: str,
    role: UserRole,
    tenant_id: str | None = None,
    client_id: str | None = None,
    permissions: list[str] | None = None,
) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role.value,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "permissions": permissions or default_permissions_for_role(role),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> TokenPayload | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return TokenPayload(
            sub=payload["sub"],
            tenant_id=payload.get("tenant_id"),
            client_id=payload.get("client_id"),
            role=UserRole(payload["role"]),
            permissions=list(
                payload.get("permissions") or default_permissions_for_role(payload["role"])
            ),
            exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (JWTError, KeyError, ValueError):
        return None


MIN_PASSWORD_LENGTH = 6


def normalize_email(email: str) -> str:
    return email.strip().lower()


def default_permissions_for_role(role: UserRole | str) -> list[str]:
    normalized_role = role if isinstance(role, UserRole) else UserRole(role)
    if normalized_role == UserRole.PLATFORM_ADMIN:
        return ["*"]
    if normalized_role == UserRole.TENANT_ADMIN:
        return [
            UserPermission.INBOUND_ORDERS_MANAGE.value,
            UserPermission.INBOUND_ORDERS_IMPORT.value,
            UserPermission.RECEIVING_EXECUTE.value,
            UserPermission.OUTBOUND_ORDERS_MANAGE.value,
            UserPermission.PICKING_EXECUTE.value,
            UserPermission.SHIPPING_EXECUTE.value,
            UserPermission.MASTER_DATA_MANAGE.value,
            UserPermission.USERS_MANAGE.value,
            UserPermission.BILLING_MANAGE.value,
            UserPermission.PLANNER_MANAGE.value,
        ]
    if normalized_role == UserRole.OPERATOR:
        return [
            UserPermission.RECEIVING_EXECUTE.value,
            UserPermission.PICKING_EXECUTE.value,
            UserPermission.SHIPPING_EXECUTE.value,
        ]
    if normalized_role == UserRole.CLIENT_VIEWER:
        return [UserPermission.PORTAL_VIEW.value]
    return []


def normalize_permissions(role: UserRole | str, permissions: list[str] | None) -> list[str]:
    candidate_permissions = list(permissions or default_permissions_for_role(role))
    if "*" in candidate_permissions:
        return ["*"]
    deduped: list[str] = []
    for permission in candidate_permissions:
        if permission not in deduped:
            deduped.append(permission)
    return deduped


def has_permission(
    role: UserRole | str, permissions: list[str] | None, required_permission: str
) -> bool:
    normalized = normalize_permissions(role, permissions)
    return "*" in normalized or required_permission in normalized


def validate_password(password: str) -> None:
    """Raise ValueError if password doesn't meet requirements."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
