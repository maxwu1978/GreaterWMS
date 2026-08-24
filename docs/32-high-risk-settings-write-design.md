# High-Risk Settings Write Design

This design keeps high-risk Settings writes out of runtime agents until the
platform explicitly enables one small gate at a time.

## Decision

Do not enable high-risk Settings writes yet. The next platform work should add
preview-only design coverage and tests before any confirmed `/agent` write
endpoint is created.

## High-Risk Domains

| Domain | Current State | Write Decision |
| --- | --- | --- |
| Billing rate-card apply | Read and preview are allowed where documented | Design-only |
| Users and permissions | Reads are allowed for authorized admins | Design-only |
| Provider secrets | Redacted reads only | Design-only |
| Model roster settings | Read model roster without secrets | Design-only |
| Allowed-tool governance | Read allowed tools and policy | Design-only |
| Nested client settings | Read/redacted preview only | Design-only |
| SKU attributes | Scalar SKU writes are enabled; attributes are not | Design-only |

## Shared Gate Shape

Every future high-risk write must have:

- preview endpoint returning before/after state
- persisted evidence row with redacted sensitive fields
- confirmation token bound to action, entity, payload hash, and tenant
- dedicated `/agent` confirm endpoint
- `X-Idempotency-Key`
- permission gate scoped to the exact setting family
- structured recovery detail
- audit record showing actor, tenant, action, entity, and evidence
- preview-only production smoke by default

## Billing Rate-Card Apply

Object:

- `rate_card`
- entity id: rate card id

Permission:

- `billing.manage`

Allowed fields for first gate:

- none yet for write
- preview may show changed rule keys, effective date impact, and client count

Rejected fields:

- currency changes with existing invoices
- retroactive billing-period mutation
- nested arbitrary JSON rules not allowlisted

Recovery:

- keep current rate card active
- rerun billing explain and rate-card read
- route production correction to billing admin UI until a gate exists

## Users And Permissions

Object:

- `user`
- `role_assignment`
- `permission_override`

Permission:

- tenant admin or explicit `users.manage`

Allowed fields for first gate:

- none yet for write

Rejected fields:

- password, reset token, verification token
- platform admin promotion
- tenant switch
- permission grants outside caller authority

Recovery:

- keep current user active state and permissions unchanged
- return to user detail read
- route urgent access fixes to existing admin UI

## Provider Secrets And Model Settings

Object:

- `agent_provider_setting`
- `model_roster`
- `allowed_tool_policy`

Permission:

- tenant admin plus future dedicated agent governance permission

Allowed fields for first gate:

- none yet for write

Rejected fields:

- raw API key echo
- writing secrets through prompts
- enabling new write tools without platform capability metadata

Recovery:

- keep previous provider setting
- show redacted validation state
- require manual admin review for broken provider credentials

## Required Tests Before Any Write Gate

- preview redacts secrets
- missing permission returns 403
- missing idempotency returns 400
- token mismatch returns 409
- payload mismatch returns 409
- same idempotency key and same payload replays
- same idempotency key and different payload fails
- forbidden fields fail before evidence confirmation
- audit/evidence stores no raw secret
- production smoke defaults to preview-only

## Implementation Order

1. Keep all high-risk Settings write commands blocked.
2. Add static contract coverage that documents the blocked commands.
3. Add preview-only smoke for billing rate-card apply design.
4. Review whether `billing.manage` is sufficient or a narrower permission is
   needed.
5. Only after review, implement one small `/agent` write gate.
