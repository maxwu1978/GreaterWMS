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
```

The existing guarded deployment script targets the old service and must not be
used as the production cutover command until it is updated intentionally.
