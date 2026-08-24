"""Authentication endpoints — login, token refresh, password reset."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import apply_session_context, get_db_session
from app.core.security import (
    UserRole,
    create_access_token,
    default_permissions_for_role,
    hash_password,
    normalize_email,
    normalize_permissions,
    verify_password,
)
from app.models.tenant import Tenant, User
from app.services.email_service import email_delivery_enabled, send_password_reset_email

router = APIRouter()

PASSWORD_RESET_TTL_MINUTES = 60


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant_id: str | None = None
    job_title: str | None = None
    permissions: list[str] = []


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    success: bool = True
    message: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResetPasswordValidationResponse(BaseModel):
    valid: bool
    message: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db_session)):
    # Login must bypass tenant RLS to look up a user by email across all tenants.
    await apply_session_context(db, is_platform_admin=True)

    email = normalize_email(str(body.email))
    result = await db.execute(
        select(User)
        .where(func.lower(User.email) == email, User.is_active == True)  # noqa: E712
        .order_by(User.created_at.desc())
    )
    users = list(result.scalars())
    user = next(
        (
            candidate
            for candidate in users
            if verify_password(body.password, candidate.hashed_password)
        ),
        None,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before signing in.",
        )

    if user.tenant_id:
        tenant_approval = await db.scalar(
            select(Tenant.approval_status).where(Tenant.id == user.tenant_id)
        )
        if tenant_approval == "pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your workspace is awaiting administrator approval. You will be able to sign in once it is approved.",
            )
        if tenant_approval == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your workspace registration was declined. Contact support if you believe this is a mistake.",
            )

    token = create_access_token(
        user_id=user.id,
        role=UserRole(user.role),
        tenant_id=user.tenant_id,
        client_id=user.client_id,
        permissions=normalize_permissions(user.role, user.permissions),
    )

    return TokenResponse(
        access_token=token,
        role=user.role,
        tenant_id=user.tenant_id,
        job_title=user.job_title,
        permissions=normalize_permissions(
            user.role, user.permissions or default_permissions_for_role(user.role)
        ),
    )


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db_session)):
    message = "If that email exists, a password reset link has been sent."
    if not email_delivery_enabled():
        return ForgotPasswordResponse(message=message)

    await apply_session_context(db, is_platform_admin=True)

    email = normalize_email(str(body.email))
    result = await db.execute(
        select(User)
        .where(func.lower(User.email) == email, User.is_active == True)  # noqa: E712
        .order_by(User.created_at.desc())
    )
    user = result.scalars().first()
    if not user:
        return ForgotPasswordResponse(message=message)

    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_sent_at = datetime.now(UTC)
    await db.flush()

    reset_url = f"{settings.APP_BASE_URL.rstrip('/')}/reset-password?token={reset_token}"
    await send_password_reset_email(
        to_email=user.email,
        company_name=settings.APP_NAME,
        reset_url=reset_url,
    )
    return ForgotPasswordResponse(message=message)


@router.get("/reset-password/validate", response_model=ResetPasswordValidationResponse)
async def validate_reset_password_token(token: str, db: AsyncSession = Depends(get_db_session)):
    if not token.strip():
        return ResetPasswordValidationResponse(valid=False, message="Missing reset token")

    await apply_session_context(db, is_platform_admin=True)

    result = await db.execute(select(User).where(User.password_reset_token == token))
    user = result.scalar_one_or_none()
    if not user or not user.password_reset_sent_at:
        return ResetPasswordValidationResponse(valid=False, message="Invalid or expired reset link")

    expires_at = user.password_reset_sent_at + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)
    if expires_at < datetime.now(UTC):
        return ResetPasswordValidationResponse(valid=False, message="Invalid or expired reset link")

    return ResetPasswordValidationResponse(valid=True, message="Reset link is valid")


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db_session)):
    if not body.token.strip():
        raise HTTPException(status_code=400, detail="Missing reset token")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    await apply_session_context(db, is_platform_admin=True)

    result = await db.execute(select(User).where(User.password_reset_token == body.token))
    user = result.scalar_one_or_none()
    if not user or not user.password_reset_sent_at:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    expires_at = user.password_reset_sent_at + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)
    if expires_at < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = hash_password(body.new_password)
    user.password_reset_token = None
    user.password_reset_sent_at = None
    user.is_email_verified = True
    await db.flush()
    return {"success": True, "message": "Password reset successfully"}
