"""
Shared framework for the governed agent preview/confirm-token write gate.

Every governed agent write follows the same two-step protocol:

1. ``preview_*`` renders a dry-run response — either by replaying the real
   write inside a savepoint and rolling it back (:func:`savepoint_dry_run`)
   or by computing the projected state — then hashes the payload, issues a
   confirmation token, and persists an ``AgentEvidence`` row
   (:func:`issue_preview`).
2. ``confirm_*_with_token`` re-runs the preview without persisting evidence,
   matches the stored evidence by payload hash + token
   (:func:`match_evidence`), executes the real write, and records the outcome
   (:func:`finalize_confirmation`).

This module owns the response-dict skeletons, the evidence/token sequence,
and the confirm preamble, so the per-domain services only provide their
action-specific state functions, scope/records/impact payloads, and result
shaping. Response key order and error payload shapes are kept exactly as the
original per-service implementations produced them.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_evidence import AgentEvidence
from app.services.agent_evidence_service import AgentEvidenceService


@dataclass(frozen=True)
class AgentGateSpec:
    """Static description of one governed agent action."""

    action: str
    risk: str
    permission: str
    entity_type: str
    token_prefix: str
    # Some domains (receiving, putaway) expose their HTTP error payloads under
    # "code" instead of "error_code"; keep each domain's wire format intact.
    error_code_key: str = "error_code"

    def gate_error(self, code: str, message: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={self.error_code_key: code, "message": message},
        )


def planned_request(endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "body": body,
        "idempotency_key_required_for_write": True,
    }


def blocked_preview(
    spec: AgentGateSpec,
    *,
    entity: dict[str, Any],
    state_before: Any,
    endpoint: str,
    body: dict[str, Any],
    next_action: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """ok=False dry-run response: nothing was written and no token is issued."""
    return {
        "ok": False,
        "dry_run": True,
        "action": spec.action,
        "risk": spec.risk,
        "permission": spec.permission,
        "entity": entity,
        "state_before": state_before,
        "state_after": "unchanged",
        "planned_request": planned_request(endpoint, body),
        "confirmation_required_for_write": False,
        "next_action": next_action,
        "evidence_id": None,
        "result": result,
    }


async def savepoint_dry_run(
    db: AsyncSession,
    execute: Callable[[], Awaitable[Any]],
    capture_state: Callable[[], Awaitable[Any]],
) -> tuple[Any, Any]:
    """Run the real write inside a savepoint, capture state, then roll back."""
    savepoint = await db.begin_nested()
    try:
        planned_result = await execute()
        state_after = await capture_state()
    finally:
        await savepoint.rollback()
    return planned_result, state_after


async def issue_preview(
    db: AsyncSession,
    tenant_id: str,
    spec: AgentGateSpec,
    *,
    entity: dict[str, Any],
    entity_id: str,
    endpoint: str,
    body: dict[str, Any],
    hash_scope: dict[str, Any],
    state_before: Any,
    state_after: Any,
    scope: dict[str, Any],
    records: list[dict[str, Any]],
    impact: dict[str, Any],
    result: dict[str, Any],
    user_id: str | None,
    persist_evidence: bool,
) -> dict[str, Any]:
    """Build the ok=True preview, issue a token, and persist evidence.

    ``hash_scope`` carries the action-specific identifier keys that are mixed
    into the payload hash alongside tenant, action, body, and both states
    (e.g. ``{"task_id": task_id}`` or ``{"order_id": ..., "package_id": ...}``).
    """
    evidence_svc = AgentEvidenceService(db, tenant_id)
    payload_hash = evidence_svc.payload_hash(
        {
            "tenant_id": tenant_id,
            "action": spec.action,
            **hash_scope,
            "body": body,
            "state_before": state_before,
            "state_after": state_after,
        }
    )
    confirmation_token = evidence_svc.issue_token(spec.token_prefix) if persist_evidence else None
    confirmation_payload: dict[str, Any] = {
        "tool_name": spec.action,
        "risk": spec.risk,
        "required_permission": spec.permission,
        "payload_hash": payload_hash,
        "scope": scope,
        "records": records,
        "impact": impact,
    }
    if confirmation_token:
        confirmation_payload["confirmation_token"] = confirmation_token

    preview = {
        "ok": True,
        "dry_run": True,
        "action": spec.action,
        "risk": spec.risk,
        "permission": spec.permission,
        "entity": entity,
        "state_before": state_before,
        "state_after": state_after,
        "planned_request": planned_request(endpoint, body),
        "confirmation_payload": confirmation_payload,
        "confirmation_required_for_write": True,
        "next_action": "submit_with_confirm_token_after_review",
        "evidence_id": f"agent-preview:{payload_hash[:16]}",
        "result": result,
    }
    if not persist_evidence:
        return preview

    evidence = await evidence_svc.persist_preview(
        action=spec.action,
        risk=spec.risk,
        required_permission=spec.permission,
        entity_type=spec.entity_type,
        entity_id=entity_id,
        actor_user_id=user_id,
        payload_hash=payload_hash,
        confirmation_token=confirmation_token,
        planned_endpoint=endpoint,
        state_before=state_before,
        state_after=state_after,
        planned_request=preview["planned_request"],
        confirmation_payload=confirmation_payload,
    )
    preview["evidence_id"] = evidence.id
    preview["confirmation_payload"]["evidence_id"] = evidence.id
    return preview


def require_confirmation_token(
    spec: AgentGateSpec, confirmation_token: str, *, message: str
) -> None:
    """409 ``confirmation_required`` when the agent supplied no token."""
    if not confirmation_token.strip():
        raise spec.gate_error("confirmation_required", message)


def require_preview_ok(
    spec: AgentGateSpec, preview: dict[str, Any], *, error_code: str, default_message: str
) -> None:
    """409 with the preview's ``what_happened`` when the dry run was blocked."""
    if not preview.get("ok"):
        raise spec.gate_error(
            error_code,
            preview.get("result", {}).get("what_happened", default_message),
        )


async def match_evidence(
    db: AsyncSession,
    tenant_id: str,
    spec: AgentGateSpec,
    *,
    entity_id: str,
    payload_hash: str,
    confirmation_token: str,
    mismatch_message: str,
) -> AgentEvidence:
    """Find the previewed evidence for this token or raise 409 ``confirmation_mismatch``."""
    evidence = await AgentEvidenceService(db, tenant_id).find_preview(
        action=spec.action,
        entity_type=spec.entity_type,
        entity_id=entity_id,
        payload_hash=payload_hash,
        confirmation_token=confirmation_token,
    )
    if evidence is None:
        raise spec.gate_error("confirmation_mismatch", mismatch_message)
    return evidence


async def finalize_confirmation(
    db: AsyncSession,
    tenant_id: str,
    spec: AgentGateSpec,
    *,
    evidence: AgentEvidence,
    ok: bool,
    entity: dict[str, Any],
    state_before: Any,
    state_after: Any,
    payload_hash: str,
    next_action: str,
    result: Any,
    user_id: str | None,
    idempotency_key: str | None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Build the executed-write response and mark the evidence row accordingly."""
    response = {
        "ok": ok,
        "dry_run": False,
        "action": spec.action,
        "risk": spec.risk,
        "permission": spec.permission,
        "entity": entity,
        "state_before": state_before,
        "state_after": state_after,
        "confirmation_payload": {
            "payload_hash": payload_hash,
            "confirmation_token": "[accepted]",
        },
        "confirmation_required_for_write": False,
        "next_action": next_action,
        "evidence_id": evidence.id,
        "result": result,
    }
    await AgentEvidenceService(db, tenant_id).mark_executed(
        evidence,
        actor_user_id=user_id,
        idempotency_key=idempotency_key,
        state_after=state_after,
        result=result,
        success=ok,
        failure_reason=failure_reason,
    )
    return response
