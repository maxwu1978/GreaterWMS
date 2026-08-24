# Local Agent Platform Contract Handoff

This handoff defines the contract between the WMS platform lane and the
separate local-agent runtime process.

> Reconciled 2026-08-24: the platform contract is current, but the historical
> CLI path tools/wms.mjs is not present in this checkout. Use the platform Agent
> API, tools/local-agent.mjs, or mcp-server/ as described in
> docs/25-greaterwms-cli-reference.md.

## Ownership

The platform process owns the platform contract:

- backend agent APIs under `/api/v1/agent`
- governed preview, evidence, confirmation-token, idempotency, permission, and
  rollback behavior
- platform capability metadata and governed Agent API operations
- skills, SOPs, runbooks, project plan, release gates, and smoke scripts

This current local-agent process owns only the runtime product shell:

- local service process and model orchestration
- local session handling and provider routing
- chat UX, local UI, local audit UX, and demo flow
- customer-facing local-agent behavior

## Boundary Rule

The local-agent process consumes the WMS platform contract. It should not add or
modify platform endpoints, capability metadata, database models, migrations,
import semantics, or the WMS web Agent Console. If a needed platform capability
is missing, record it as a dependency for the platform process.

The platform lane should not add new `wms-agent/` product features. It may
touch `wms-agent/` only for narrow compatibility fixes when a platform API
contract changes or when a contract fixture needs to stay aligned.

Existing `wms-agent/` code remains a tested reference implementation until it
is replaced or deliberately archived.

## Required References

Local-agent development should read these before implementing a write flow:

- [24-agent-capabilities-reference.md](24-agent-capabilities-reference.md)
- [25-greaterwms-cli-reference.md](25-greaterwms-cli-reference.md)
- [26-wms-agent-operator-sop.md](26-wms-agent-operator-sop.md)
- [29-high-risk-settings-agent-runbook.md](29-high-risk-settings-agent-runbook.md)
- [06-agent-console-spec.md](06-agent-console-spec.md)
- [.codex/skills/wms-local-agent-operator/SKILL.md](../.codex/skills/wms-local-agent-operator/SKILL.md)
- [../wms-agent/README.md](../wms-agent/README.md)

## Platform APIs To Consume

Read and preview operations should use:

- `POST /api/v1/agent/tools/run`
- `GET /api/v1/agent/settings`
- `GET /api/v1/agent/evidence/{evidence_id}`
- `GET /api/v1/agent/evidence/{evidence_id}/replay-preview`
- `GET /api/v1/agent/evidence/failed`
- documented domain preview endpoints listed in the CLI capabilities output

Confirmed writes must use only documented `/agent` endpoints after a preview
returns:

- `confirmation_required_for_write: true`
- `planned_request.endpoint` ending in `/preview`
- `planned_request.agent_endpoint`
- `confirmation_payload.confirmation_token`
- persisted `evidence_id`

Every confirmed write must include `X-Idempotency-Key`.

## Client Contract

The local-agent process must call documented Agent API endpoints or use the
MCP adapter. A generic platform CLI is not shipped in this checkout.

The supported local process smoke command is:

```bash
node tools/local-agent.mjs smoke
```

Production confirms must preserve the server-side preview, confirmation, and
idempotency contract. Clients must not invent a replacement confirmation
triplet or pass raw credentials through a model prompt.

## Hard Stops

The local-agent process must not:

- send WMS bearer tokens, confirmation tokens, passwords, API keys, or provider
  secrets to model prompts
- bypass preview evidence for writes
- call direct import tools through `/api/tools/run`
- connect directly to production databases
- enable high-risk Settings writes without a dedicated runbook and gate

High-risk Settings remain preview-only or design-only until separately enabled:

- billing rate-card apply
- users, roles, and permissions
- provider secrets and model roster settings
- allowed-tool governance
- nested client settings and SKU attributes

## Smoke And Gate Expectations

Before local-agent changes are accepted, run the standalone agent checks:

```bash
cd wms-agent
uv sync --extra dev
uv run ruff check local_agent tests
uv run pytest tests/ -q
```

For platform Agent API changes, run the backend test suite and review the
server-side capability catalog. Production preview or confirm requires a
disposable test tenant and explicit approval; do not infer platform readiness
from the retired frontend CLI-check scripts.

## Recovery Rules

If a write fails:

1. Read structured `detail`.
2. Load evidence detail when an `evidence_id` exists.
3. Rerun preview before retrying.
4. Use a new confirmation token if payload or state changed.
5. Preserve the same idempotency key only for exact replay of the same request.

If an import confirm returns row errors, treat the write as rolled back. Fix the
CSV or mapping and rerun preview.
