# GreaterWMS API Authentication

The tenant `openid` is an identifier, not an API password. API requests must
use an opaque session token in the `HTTP_TOKEN` header.

## Administrator session

1. `POST /login/` with the administrator username and password.
2. Use `data.token` from the response as `HTTP_TOKEN`.
3. The response also contains `data.tenant_openid` for display and tenant
   context. Do not use it as a bearer credential.

## Staff session

Staff can sign in directly with their own staff name and check code:

```http
POST /staff/login/
Content-Type: application/json

{"staff_name":"op10@peaksmartlogistics.com","check_code":123456}
```

The response contains `data.token`. Use that value as `HTTP_TOKEN` for the
staff member's subsequent requests. The staff name must identify exactly one
active non-administrator account across the system; duplicate names are
rejected so a login cannot select the wrong tenant. Direct-login failures are
rate-limited by client IP and staff name. They do not increment the shared
account lock counter, so a caller cannot lock every operator by submitting
three bad codes. An administrator can still lock an account explicitly, and a
locked account requires administrator intervention.

For compatibility, an administrator can still validate a staff name and check
code from an existing administrator session:

```http
GET /staff/?staff_name=WM1&check_code=1234
HTTP_TOKEN: <administrator-session-token>
```

The response contains `auth_token`. Use that value as `HTTP_TOKEN` for the
staff member's subsequent requests. The token is bound to the staff record
and expires according to `AUTH_SESSION_TTL_DAYS` (30 days by default).

For non-administrator write requests, send the authenticated staff record ID
as `HTTP_OPERATOR`. A different operator ID, or a missing operator ID, is
rejected. Administrator sessions may act without an operator header.

The previous behavior of accepting a tenant `openid` directly as an API token
is disabled by default. `ALLOW_LEGACY_OPENID_AUTH=true` is available only for
a controlled migration and must not be enabled in production.

## Tenant cleanup

Tenant cleanup is a destructive test-data operation. It is disabled by default,
including for production administrators. To use it in an isolated disposable
environment, set both variables in that environment only:

```text
TENANT_CLEANUP_ENABLED=true
TENANT_CLEANUP_ALLOWED_OPENIDS=<explicit-disposable-tenant-openid>
```

The production service must not set either variable. A valid administrator
session alone is not sufficient to authorize cleanup.
