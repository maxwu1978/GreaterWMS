# UAT Execution Log

This log tracks release acceptance after the 2026-05-06 production frontend
deployment. The release was accepted through automated UAT plus evidence review,
with manual testing reserved for exceptional real-device checks.

## Release Under Test

| Field | Value |
| --- | --- |
| Frontend deployment | `dpl_2zU2mWFifUC44hzQFRJAKYAsjArm` |
| Production app | `https://app.maxsmartwms.online` |
| Frontend source commit | `dc59a65` for the Receiving split, with release evidence recorded in `35e0a89` |
| Backend health build | `9a459f7c0d80dc398da34a8d19d7716602e7e8ef` |
| UAT checklist | `docs/20-manual-uat-checklist.md` |
| Runbook | `docs/16-uat-runbook.md` |

## Read-Only Gate

| Check | Result | Evidence |
| --- | --- | --- |
| CI for release evidence commit | Pass | GitHub Actions run `25421643453` |
| Production app alias | Pass | `https://app.maxsmartwms.online` returned `HTTP/2 200` on 2026-05-06 |
| Production API health | Pass | `GET https://api.maxsmartwms.online/health` returned `HTTP/2 200`, status `ok` |
| Production-writing automation prerequisites | Ready with blocker | Platform credential, monitored email, and cleanup preserve list are configured; release owner approved automated UAT; mail-provider smoke is blocked |

## Automated UAT Attempt

| Step | Result | Evidence |
| --- | --- | --- |
| `npm run smoke:mail-provider` | Fail | Diagnostic returned `success=false`; MailerSend returned `401 Unauthorized`; SMTP fallback returned network unreachable |
| `npm run smoke:production-bootstrap` | Not run | Paused because the email-provider gate failed |
| `npm run uat:production` | Not run | Paused because the email-provider gate failed |
| `npm run uat:mobile-orchestrator` | Not run | Paused because the email-provider gate failed |
| `npm run audit:production-pages` | Not run | Paused because the email-provider gate failed |
| `npm run uat:production:cleanup` | Not run | No automated UAT tenants were created in this attempt |

## Automated UAT Completion

| Step | Result | Evidence |
| --- | --- | --- |
| Render email env repair | Pass | Updated production `MAILERSEND_API_KEY`, deployed backend `dep-d7tglvd0lvsc7397n9o0`, health build `0616d3240c3dd7e5bb37f0f9f22fd358bca40ef0` |
| `npm run smoke:mail-provider` | Pass | Diagnostic email sent by `mailersend`, `success=true` |
| `npm run smoke:production-bootstrap` | Pass | Created verified tenant admin `boot299387@example.com`, tenant code `BTBOOT299387`, `verificationRequired=false` |
| `npm run uat:production` | Pass | Batch `UAT-20260506-01`, receiving `2` packages, putaway `2` tasks, billing invoice sent/paid, shipped final status, `consoleErrors=0` |
| `npm run uat:mobile-orchestrator` | Pass | Covered Admin, Agent, Dashboard, Inventory, Master Data, Migration, Picking, Putaway, Receiving, Shipping |
| Orchestrator cleanup | Pass | Deleted `7` test tenants and `130` tenant-scoped rows; preserved operational rows deleted `0` |
| `npm run audit:production-pages` | Pass | Checked `70` pages, `0` failures, `0` console errors |
| `npm run uat:production:cleanup` | Pass | Deleted final layout-audit tenant and `11` tenant-scoped rows; final dry-run test tenants `0`, rows `0`, preserved operational rows deleted `0` |

## UAT Batch Setup

| Field | Value |
| --- | --- |
| Batch ID | `UAT-YYYYMMDD-01` |
| Tester names |  |
| Test window |  |
| Devices |  |
| Tenant / client |  |
| Browser or app shell |  |
| Release owner approval for production-writing scripts | Not approved / Approved |

## Lane Status

| Lane | Owner | Status | Evidence folder / notes |
| --- | --- | --- | --- |
| Mobile execution | Automated UAT | Pass | `npm run uat:mobile-orchestrator` |
| Desktop management | Automated UAT | Pass | `npm run audit:production-pages` |
| Recovery contract | Automated UAT | Pass | `npm run uat:mobile-orchestrator` |
| Release gate | Release owner | Pass | CI, deploy, health, mail gate, automated UAT, and cleanup passed |
| Cleanup and data safety | Release owner / ops | Pass | Final cleanup dry-run found `0` test tenants and `0` test rows |

## Scenario Results

| ID | Scenario | Device | Result | Issue ID | Evidence |
| --- | --- | --- | --- | --- | --- |
| M-UAT-ACC-01 | Sign in as tenant admin | Phone + desktop | Automated pass |  | `smoke:production-bootstrap`, `uat:production`, `uat:mobile-orchestrator` |
| M-UAT-REC-01 | Open Receiving list | Phone | Automated pass |  | `uat:mobile-orchestrator` |
| M-UAT-REC-04 | Confirm receipt | Phone | Automated pass |  | `uat:production`, `uat:mobile-orchestrator` |
| M-UAT-PUT-01 | Open Putaway | Phone | Automated pass |  | `uat:mobile-orchestrator` |
| M-UAT-PUT-04 | Confirm putaway | Phone | Automated pass |  | `uat:production`, `uat:mobile-orchestrator` |
| M-UAT-INV-02 | Review Inventory primary task | Phone | Automated pass |  | `uat:mobile-orchestrator` |
| M-UAT-PIC-01 | Open Picking | Phone | Automated pass |  | `uat:mobile-orchestrator` |
| M-UAT-PIC-05 | Complete pick | Phone | Automated pass |  | `uat:production` |
| M-UAT-SHP-01 | Open Shipping | Phone | Automated pass |  | `uat:mobile-orchestrator` |
| M-UAT-SHP-07 | Confirm shipment | Phone | Automated pass |  | `uat:production`, `uat:mobile-orchestrator` |
| M-UAT-EXC-STRUCT-01 | Recovery panel structure | Phone / desktop | Automated pass |  | `uat:mobile-orchestrator`, `smoke:recovery-matrix` in CI |

## Issue Log

| Issue ID | Severity | Area | Summary | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| UAT-BLOCKER-001 | Blocker | Production email | Mail-provider diagnostic could not deliver because the old MailerSend token returned `401 Unauthorized`. | Release owner / email provider owner | Closed after token update and backend deploy |

## Exit Decision

| Decision | Owner | Date | Notes |
| --- | --- | --- | --- |
| Release ready | Release owner | 2026-05-06 | Automated UAT, production page audit, cleanup, CI, frontend production deploy, and backend health all passed. No page-by-page manual UAT is required for this release. |

## Closure Summary

| Field | Value |
| --- | --- |
| Automated UAT evidence commit | `f9cd86f` |
| Release closure commit | `f60ed6c` |
| Release closure CI | `25428249062`, passed |
| Frontend production deployment | `dpl_2zU2mWFifUC44hzQFRJAKYAsjArm` |
| Backend production deploy | `dep-d7tglvd0lvsc7397n9o0` |
| Backend health build | `0616d3240c3dd7e5bb37f0f9f22fd358bca40ef0` |
| Production app health | `https://app.maxsmartwms.online` ready |
| Production API health | `GET /health` returned `HTTP/2 200`, status `ok` |
| Automated UAT outcome | Pass |
| Cleanup outcome | Pass, final dry-run found `0` test tenants and `0` test rows |
| Remaining work | Evidence review and owner sign-off only |
