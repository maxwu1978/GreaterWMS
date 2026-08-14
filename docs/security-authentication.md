# GreaterWMS API Authentication

The tenant `openid` is an identifier, not an API password. API requests must
use an opaque session token in the `HTTP_TOKEN` header.

## Administrator session

1. `POST /login/` with the administrator username and password.
2. Use `data.token` from the response as `HTTP_TOKEN`.
3. The response also contains `data.tenant_openid` for display and tenant
   context. Do not use it as a bearer credential.

## Staff session

An administrator session can validate a staff name and check code:

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
