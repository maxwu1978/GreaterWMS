"""Create or promote a platform super admin.

Usage:
    PLATFORM_ADMIN_EMAIL=owner@example.com PLATFORM_ADMIN_PASSWORD='change-me' \
        uv run python scripts/create_platform_admin.py

The users table is tenant-scoped, so platform admins are stored under a small
host tenant while their role gives them cross-tenant access at login.
"""

import asyncio
import getpass
import os

from sqlalchemy import func, select

from app.core.database import apply_session_context, async_session_factory
from app.core.security import UserRole, hash_password, normalize_email, normalize_permissions
from app.models.tenant import Tenant, User

PLATFORM_TENANT_CODE = "PLATFORM"
PLATFORM_TENANT_ID = "platform-admin-tenant"


async def main() -> None:
    email = normalize_email(os.environ.get("PLATFORM_ADMIN_EMAIL") or input("Email: "))
    password = os.environ.get("PLATFORM_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    full_name = os.environ.get("PLATFORM_ADMIN_NAME", "Platform Super Admin")

    async with async_session_factory() as db:
        await apply_session_context(db, is_platform_admin=True)

        tenant = (
            await db.execute(select(Tenant).where(Tenant.code == PLATFORM_TENANT_CODE))
        ).scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=PLATFORM_TENANT_ID,
                name="WMS QuickStart Platform",
                code=PLATFORM_TENANT_CODE,
                contact_email=email,
                plan_tier="enterprise",
                is_active=True,
            )
            db.add(tenant)
            await db.flush()

        user = (
            await db.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one_or_none()
        existing_admin = await db.scalar(
            select(User).where(User.role == UserRole.PLATFORM_ADMIN.value).limit(1)
        )
        if existing_admin and (not user or existing_admin.id != user.id):
            raise RuntimeError(
                "A platform admin already exists; use the governed user-management flow "
                "instead of creating another super admin."
            )
        if not user:
            user = User(
                tenant_id=tenant.id,
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                role=UserRole.PLATFORM_ADMIN.value,
                permissions=normalize_permissions(UserRole.PLATFORM_ADMIN.value, ["*"]),
                is_active=True,
                is_email_verified=True,
            )
            db.add(user)
            action = "created"
        else:
            user.tenant_id = tenant.id
            user.hashed_password = hash_password(password)
            user.full_name = user.full_name or full_name
            user.role = UserRole.PLATFORM_ADMIN.value
            user.permissions = normalize_permissions(UserRole.PLATFORM_ADMIN.value, ["*"])
            user.is_active = True
            user.is_email_verified = True
            action = "promoted"

        await db.commit()
        print(f"Platform super admin {action}: {email}")


if __name__ == "__main__":
    asyncio.run(main())
