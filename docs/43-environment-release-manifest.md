# Environment And Release Manifest

Effective date: 2026-08-25

This document closes the repository/version ambiguity created by the
QuickStart-to-GreaterWMS migration. The machine-readable source of truth is
[`../release/environment-manifest.json`](../release/environment-manifest.json).

## Current Mapping

| Environment | Render service | Code line | Verified version | Traffic |
| --- | --- | --- | --- | --- |
| Legacy production | `greaterwms-production` / `srv-d9v6ahvqj5pc73d4spp0` | `codex/cli-install-info` | `7592afe8` / `prod-legacy-2026-08-24` | Customer traffic |
| Migrated staging | `wms-quickstart-staging` / `srv-d7qgk4rbc2fs73fsjbo0` | `main` | `36ae74e6` | No customer traffic |

The legacy production frontend and API remain a matched Django pair. The
migrated FastAPI/React pair is a separate validation target. `main` must not be
described as the current production version until the coordinated cutover is
approved.

## Release Rules

1. Every production state must have a full commit SHA and an immutable `prod-*`
   tag recorded in the manifest.
2. Production data is never used as a writable migration test target. Export it
   read-only, rehearse against a separate database, and record the migration
   plan hash and verification counts.
3. A `main` push can update migrated staging only. It must not switch the
   legacy production service or its DNS.
4. A cutover is one release across backend, frontend, API domain, database,
   secrets, health checks, and rollback evidence. Partial cutovers are not
   allowed.
5. Before each release, run `python tools/verify_release_manifest.py`, verify
   the Render service's live `build_sha`, and attach the health response to the
   release record.

## Rollback

Before cutover, rollback means keeping the legacy production pair unchanged.
After a future cutover, rollback must restore the matching backend commit,
frontend artifact, API domain, and database recovery point together. The old
baseline branch `legacy/greaterwms-original-20260824` is not a production
rollback target.

## Operator Checks

```bash
python tools/verify_release_manifest.py
git show-ref --tags prod-legacy-2026-08-24
curl --fail --silent --show-error \
  https://wms-quickstart-staging.onrender.com/health
```

The current staging health response must report
`build_sha=36ae74e651076df03afed755a69621bb05da0588`. Do not paste database
URLs, Render API tokens, or customer source files into this document or into
GitHub issues.
