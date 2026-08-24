# Local Agent Process Checklist

This checklist is the executable handoff for the separate local-agent process.
It turns the platform contract into implementation checks without assigning
product-shell work back to the platform lane.

> Historical command examples later in this checklist refer to a retired
> platform CLI. Do not execute those paths. The current local smoke command is
> node tools/local-agent.mjs smoke; current Agent/MCP boundaries are in
> docs/25-greaterwms-cli-reference.md.

## Startup Contract

- Read [30-local-agent-platform-contract-handoff.md](30-local-agent-platform-contract-handoff.md).
- Start and smoke-test the local process with:

```bash
node tools/local-agent.mjs smoke
```

- Confirm local backend health before live testing:

```bash
curl -fsS http://localhost:8000/health
```

- Load only the WMS bearer token into the local runtime session boundary.
- Do not send WMS bearer tokens, confirmation tokens, passwords, API keys, or
  provider secrets to any model prompt.

## Read Flow Checklist

- Prefer read tools or CLI reads before planning a write.
- Use `POST /api/v1/agent/tools/run` only with tools present in the tenant
  `allowed_tools` list.
- Display read results without creating a confirmation card.
- Redact secrets in local logs and local audit output.

Useful platform reads must use documented Agent API endpoints through the
local governed agent or MCP adapter. This checkout does not ship a generic
platform CLI; see docs/25-greaterwms-cli-reference.md.

## Preview Flow Checklist

- For every medium/high-risk action, call preview first.
- Confirm preview response contains:
  - `confirmation_required_for_write: true`
  - `planned_request.endpoint`
  - `planned_request.agent_endpoint`
  - `confirmation_payload.confirmation_token`
  - `evidence_id`
- Show the user the action, risk, object, impact, and next step.
- Do not expose the raw confirmation token in UI, prompts, or logs.

## Confirm Flow Checklist

- Require explicit user confirmation from the local UI or command layer.
- Call only the documented `planned_request.agent_endpoint`.
- Include `X-Idempotency-Key`.
- Treat natural-language "yes" as insufficient unless the local UI binds it to
  the exact preview payload currently shown.
- On success, show what changed and the next safe action.
- On failure, show recovery and the evidence link.

Confirmation shape is owned by the server-side Agent API. The client must keep
the preview payload, evidence, confirmation state, and idempotency key bound
together without exposing or copying a raw token.

## Import Flow Checklist

- Use preview for inbound, outbound, and inventory imports.
- Stop when preview has row errors or `confirmation_required_for_write` is not
  true.
- If confirm returns row errors, treat the write as rolled back.
- Fix CSV or mapping, rerun preview, and use the new token.
- Never call direct import tools through `/api/tools/run`.

## High-Risk Settings Checklist

These are read-only or preview-only until a later platform gate enables them:

- billing rate-card apply and billing profile changes
- users, roles, permissions, invites, resets, and deactivation
- provider secrets, model roster settings, and allowed-tool governance
- nested client settings, SKU attributes, destructive deletes, and bulk mutation

Before implementing any high-risk write UI, require a platform design based on
[32-high-risk-settings-write-design.md](32-high-risk-settings-write-design.md).

## Acceptance Gate

Run these after local-agent changes:

```bash
cd wms-agent
uv sync --extra dev
uv run ruff check local_agent tests
uv run pytest tests/ -q
```

For platform Agent API changes, run the backend test suite and use the release
gate. Production preview or confirm requires a disposable test tenant and
explicit approval.

## Escalation

Escalate to the platform lane only when:

- capability metadata is missing or incorrect
- a preview response lacks required confirmation fields
- evidence detail or replay endpoints fail unexpectedly
- the CLI contract changes
- a high-risk Settings write needs a new gated platform design
