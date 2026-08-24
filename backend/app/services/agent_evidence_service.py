"""Helpers for governed agent preview evidence and confirmation tokens."""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_evidence import AgentEvidence


class AgentEvidenceService:
    """Persist and match evidence for agent-only write gates."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        encoded = jsonable_encoder(payload)
        body = json.dumps(encoded, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def issue_token(prefix: str) -> str:
        return f"{prefix}:{secrets.token_urlsafe(24)}"

    async def persist_preview(
        self,
        *,
        action: str,
        risk: str,
        required_permission: str,
        entity_type: str,
        entity_id: str,
        actor_user_id: str | None,
        payload_hash: str,
        confirmation_token: str,
        planned_endpoint: str,
        state_before: dict | None,
        state_after: dict | None,
        planned_request: dict | None,
        confirmation_payload: dict | None,
        ttl_minutes: int = 30,
    ) -> AgentEvidence:
        evidence = AgentEvidence(
            tenant_id=self.tenant_id,
            action=action,
            risk=risk,
            required_permission=required_permission,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            status="previewed",
            payload_hash=payload_hash,
            confirmation_token_hash=self.token_hash(confirmation_token),
            planned_endpoint=planned_endpoint,
            state_before=state_before,
            state_after=state_after,
            planned_request=planned_request,
            confirmation_payload={
                **(confirmation_payload or {}),
                "confirmation_token": "[redacted]",
            },
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
        )
        self.db.add(evidence)
        await self.db.flush()
        return evidence

    async def find_preview(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload_hash: str,
        confirmation_token: str,
    ) -> AgentEvidence | None:
        return await self.db.scalar(
            select(AgentEvidence).where(
                AgentEvidence.tenant_id == self.tenant_id,
                AgentEvidence.action == action,
                AgentEvidence.status == "previewed",
                AgentEvidence.entity_type == entity_type,
                AgentEvidence.entity_id == entity_id,
                AgentEvidence.payload_hash == payload_hash,
                AgentEvidence.confirmation_token_hash
                == self.token_hash(confirmation_token.strip()),
                AgentEvidence.expires_at > datetime.now(UTC),
            )
        )

    async def mark_executed(
        self,
        evidence: AgentEvidence,
        *,
        actor_user_id: str | None,
        idempotency_key: str | None,
        state_after: dict | None,
        result: dict | list | None,
        success: bool,
        failure_reason: str | None = None,
    ) -> None:
        evidence.status = "executed" if success else "failed"
        evidence.actor_user_id = actor_user_id or evidence.actor_user_id
        evidence.idempotency_key = idempotency_key
        evidence.confirmed_at = datetime.now(UTC)
        evidence.state_after = state_after
        evidence.result = result
        if failure_reason:
            evidence.failure_reason = failure_reason
        await self.db.flush()
