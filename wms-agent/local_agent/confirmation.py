"""Confirmation-card helpers for governed WMS agent writes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4


class ConfirmationError(ValueError):
    pass


def extract_confirmation_card(payload: dict[str, Any]) -> dict[str, Any] | None:
    preview = _unwrap_preview(payload)
    if not isinstance(preview, dict):
        return None
    confirmation_payload = preview.get("confirmation_payload") or {}
    token = confirmation_payload.get("confirmation_token")
    planned_request = preview.get("planned_request") or {}
    endpoint = planned_request.get("endpoint")
    body = planned_request.get("body")
    if not (preview.get("confirmation_required_for_write") and token and endpoint and body):
        return None
    card = {
        "action": preview.get("action"),
        "risk": preview.get("risk"),
        "permission": preview.get("permission") or confirmation_payload.get("required_permission"),
        "entity": preview.get("entity"),
        "evidence_id": preview.get("evidence_id") or confirmation_payload.get("evidence_id"),
        "state_before": preview.get("state_before"),
        "state_after": preview.get("state_after"),
        "records": confirmation_payload.get("records") or [],
        "impact": confirmation_payload.get("impact"),
        "planned_request": planned_request,
        "confirmation_token": token,
        "agent_endpoint": agent_endpoint_from_preview(str(endpoint)),
    }
    card["strong_confirmation_required"] = requires_strong_confirmation(card)
    card["strong_confirmation_phrase"] = (
        card.get("evidence_id") if card["strong_confirmation_required"] else None
    )
    return card


STRONG_CONFIRMATION_ACTIONS = {
    "migration.inventory.import",
    "receiving.inbound.import_with_mapping",
    "orders.outbound.import_with_mapping",
    "settings.billing_rate_card.update",
    "settings.permissions.update",
    "users.create",
    "users.update",
    "users.reset_password",
    "users.update_permissions",
}


def build_confirmation_request(
    preview_payload: dict[str, Any],
    idempotency_key: str | None = None,
    strong_confirmation: str | None = None,
) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    card = extract_confirmation_card(preview_payload)
    if not card:
        raise ConfirmationError("A WMS preview with a confirmation token is required.")
    if requires_strong_confirmation(card):
        expected = str(card.get("evidence_id") or "").strip()
        provided = (strong_confirmation or "").strip()
        if not expected or provided != expected:
            raise ConfirmationError("Strong confirmation must match the evidence id.")
    planned_body = dict(card["planned_request"]["body"])
    planned_body["confirmation_token"] = card["confirmation_token"]
    key = idempotency_key or f"local-agent:{uuid4().hex}"
    headers = {"X-Idempotency-Key": key}
    return card["agent_endpoint"], planned_body, key, headers


def requires_strong_confirmation(card: dict[str, Any]) -> bool:
    action = str(card.get("action") or "")
    risk = str(card.get("risk") or "").lower()
    endpoint = str(card.get("agent_endpoint") or "")
    return (
        risk in {"high", "critical"}
        or action in STRONG_CONFIRMATION_ACTIONS
        or "/imports/" in endpoint
    )


def agent_endpoint_from_preview(endpoint: str) -> str:
    if not endpoint.startswith("POST "):
        raise ConfirmationError("Only POST preview endpoints can be confirmed.")
    path = endpoint.removeprefix("POST ").strip()
    if not path.startswith("/api/v1/"):
        raise ConfirmationError("Preview endpoint must be an /api/v1 path.")
    if not path.endswith("/preview"):
        raise ConfirmationError("Preview endpoint must end with /preview.")
    return path.removeprefix("/api/v1").removesuffix("/preview") + "/agent"


def _unwrap_preview(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("confirmation_required_for_write"):
        return payload
    result = payload.get("tool_result")
    if isinstance(result, dict):
        return _unwrap_preview(result)
    nested = payload.get("result")
    if isinstance(nested, dict):
        return _unwrap_preview(nested)
    return None
