# GreaterWMS Production Service

## Service boundary

| Item | Value |
| --- | --- |
| Render service | `greaterwms-production` |
| Render service ID | `srv-d9v6ahvqj5pc73d4spp0` |
| Render URL | `https://greaterwms-production.onrender.com` |
| Repository | `https://github.com/maxwu1978/GreaterWMS` |
| Branch | `codex/sn-receiving` |
| Database | `greaterwms-v2-test3-db` (`dpg-d9rhe27avr4c7399pjpg-a`) |
| Plan | Render Free |

## Required Render environment

The service must define these variables before the first deployment of the
security-hardened build. Values are kept in Render, never in Git:

```text
SECRET_KEY=<long random secret, shared by all instances of this service>
DEBUG=False
ALLOWED_HOSTS=greaterwms-production.onrender.com,maxsmartwms.online,app.maxsmartwms.online,api.maxsmartwms.online
CORS_ALLOWED_ORIGINS=https://greaterwms-production.onrender.com,https://maxsmartwms.online,https://app.maxsmartwms.online
CORS_ALLOW_CREDENTIALS=False
SECURE_HSTS_SECONDS=31536000
# Keep tenant cleanup disabled in production; no cleanup allowlist is needed.
# TENANT_CLEANUP_ENABLED=False
# TENANT_CLEANUP_ALLOWED_OPENIDS=
```

Set the Render health-check path to `/health/`. The endpoint performs a small
database readiness query and returns `{"status":"ok"}` only when the service
can reach its configured database.

The service uses the existing GreaterWMS PostgreSQL database so the production
service and the current live service see the same business data during the
cutover period. Do not run data migrations, cleanup, or test writes against
either service without an explicit production change record.

## Domain cutover

`maxsmartwms.online` remains attached to the existing service
`greaterwms-v2-test3-sn` until the new service passes the release gate. This
keeps the current system available as a rollback target. The domain must be
migrated only after the new service passes read-only API, login, dashboard,
inbound, Pack List, QC, receiving, and putaway smoke tests.

## Deployment

Deploy the reviewed commit to the independent service:

```bash
render deploys create srv-d9v6ahvqj5pc73d4spp0 --commit <COMMIT> --wait --confirm
```

Verify the deployment before any domain change:

```bash
render deploys list srv-d9v6ahvqj5pc73d4spp0 --output json
curl -fsS https://greaterwms-production.onrender.com/
curl -fsS https://greaterwms-production.onrender.com/health/
```

The existing guarded deployment script targets the old service and must not be
used as the production cutover command until it is updated intentionally.
