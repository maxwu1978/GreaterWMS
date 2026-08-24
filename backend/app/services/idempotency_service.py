"""Tenant-scoped idempotency support for mutation endpoints."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyRecord


class IdempotencyService:
    """Caches successful mutation responses by X-Idempotency-Key."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def run(
        self,
        *,
        key: str | None,
        operation: str,
        request_payload: dict[str, Any],
        handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        if not key:
            return await handler()

        idempotency_key = key.strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Idempotency-Key must not be blank",
            )
        if len(idempotency_key) > 128:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Idempotency-Key must be 128 characters or fewer",
            )

        request_hash = self._request_hash(operation, request_payload)
        existing = await self.db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.tenant_id == self.tenant_id,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if existing:
            if existing.operation != operation or existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=("X-Idempotency-Key was already used for a different mutation request"),
                )
            if existing.status == "completed":
                return existing.response_json
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A request with this X-Idempotency-Key is still processing",
            )

        try:
            async with self.db.begin_nested():
                record = IdempotencyRecord(
                    tenant_id=self.tenant_id,
                    idempotency_key=idempotency_key,
                    operation=operation,
                    request_hash=request_hash,
                    status="in_progress",
                )
                self.db.add(record)
                await self.db.flush()
        except IntegrityError:
            existing = await self.db.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.tenant_id == self.tenant_id,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.operation != operation or existing.request_hash != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=("X-Idempotency-Key was already used for a different mutation request"),
                    ) from None
                if existing.status == "completed":
                    return existing.response_json
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A request with this X-Idempotency-Key is still processing",
            ) from None

        try:
            response = await handler()
        except Exception:
            await self.db.delete(record)
            await self.db.flush()
            raise

        encoded_response = jsonable_encoder(response)
        record.status = "completed"
        record.response_status_code = status.HTTP_200_OK
        record.response_json = encoded_response
        await self.db.flush()
        return encoded_response

    @staticmethod
    def _request_hash(operation: str, request_payload: dict[str, Any]) -> str:
        encoded = jsonable_encoder({"operation": operation, "request": request_payload})
        body = json.dumps(encoded, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()
