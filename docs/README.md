# WMS Documentation Index

This directory is the active documentation set for the current WMS workspace.
The machine-specific `/Volumes/MaxRelocated/WMS` path in older documents is a
historical path, not a requirement for a new checkout. Archived material lives
under `docs/archive/` and should be treated as recovery/reference material, not
the operational source of truth.

## Start Here

| Document | Use |
| --- | --- |
| `41-project-handoff.md` | Current repository identity, architecture, startup, deployment, workflow, and takeover procedure |
| `42-migration-release-status.md` | Current QuickStart-to-GreaterWMS migration, staging deployment, and production cutover status |
| `43-environment-release-manifest.md` | Authoritative environment/version mapping and release rules |
| `44-current-handoff-2026-08-25.md` | Short current-state handoff for the next development conversation |
| `project-plan.md` | Chronological project decisions, release evidence, and current closure status |
| `13-engineering-environment.md` | Canonical workspace, production baseline, and local engineering hygiene |
| `10-render-deploy-operations.md` | Render backend deployment, production environment, and email provider operations |
| `16-uat-runbook.md` | Formal UAT and production QA command boundaries |
| `17-release-gate-and-access-audit.md` | Release gate checklist, access control, and production readiness audit |
| `23-uat-execution-log.md` | Current release UAT evidence, automated UAT results, cleanup, and sign-off |

## Product And UX Rules

| Document | Use |
| --- | --- |
| `09-action-first-page-discipline.md` | Mobile action-first page discipline and workflow design principles |
| `ui-language-rules.md` | WMS UI language glossary, copy rules, and static copy guard expectations |
| `20-manual-uat-checklist.md` | Tester-facing UAT packet, now primarily used for evidence review and exceptional manual checks |
| `22-desktop-first-mobile-admin-audit.md` | Desktop-first/mobile-admin surface audit |

## Engineering References

| Document | Use |
| --- | --- |
| `11-backend-typecheck-baseline.md` | Backend type-check baseline |
| `12-user-management-hierarchy.md` | User roles, access hierarchy, and access-control audit notes |
| `14-stage-status-workflow.md` | Stage/status workflow behavior |
| `15-performance-and-database-plan.md` | Performance and database planning |
| `18-ios-ipad-build-runbook.md` | iOS/iPadOS build and verification runbook |
| `19-figma-design-system.md` | Figma/design-system notes |
| `21-recovery-code-coverage.md` | Recovery-code matrix used by `npm run smoke:recovery-matrix` |
| `24-agent-capabilities-reference.md` | Agent tool capabilities, risk levels, and backend contract matrix |
| `25-greaterwms-cli-reference.md` | Current WMS Agent/MCP entry points and write safety boundaries |
| `26-wms-agent-operator-sop.md` | Retired CLI SOP retained for historical recovery/reference only |
| `27-local-wms-agent-design.md` | Local WMS Agent architecture, login boundary, minimal UI, and MVP scope |
| `28-wms-agent-feature-map.md` | Complete feature map for Local Agent coverage, with settings-first priorities |
| `30-local-agent-platform-contract-handoff.md` | Ownership split and platform contract for the separate local-agent process |
| `31-local-agent-process-checklist.md` | Executable checklist for the separate local-agent runtime process |
| `32-high-risk-settings-write-design.md` | Preview-first design boundary for future high-risk Settings write gates |
| `33-agent-cli-skill-coverage-roadmap.md` | Platform-owned CLI and skill coverage roadmap after the local-agent split |
| `34-wcs-agv-integration-plan.md` | WCS/AGV integration plan, simulator, and certification workflow |
| `35-wcs-sandbox-certification-report.md` | WCS sandbox certification evidence and remaining caveats |
| `36-agv-planning-standard.md` | AGV field planning, clearance, route, station, and WMS metadata rules |
| `37-cad-layout-export-standard.md` | CAD/DXF layout export rules and closure checklist for WMS/AGV drawings |
| `38-real-customer-onboarding-runbook.md` | Real customer data, warehouse blueprint, WCS/AGV, backup, and release gate onboarding sequence |
| `39-platform-user-cleanup-runbook.md` | Preview-first platform cleanup of non-admin user accounts |
| `40-pack-list-cli-graphical-parity.md` | Shared Pack List intake contract and CLI/Receiving-page parity test |

## Domain Notes

| Document | Use |
| --- | --- |
| `02-shopify-integration-guide.md` | Shopify integration notes |
| `03-capability-gap-analysis.md` | Capability gap analysis |
| `04-qa-test-report.md` | QA report history |
| `05-ceo-usability-report.md` | Usability review |
| `06-agent-console-spec.md` | Agent console specification |
| `07-putaway-retrospective.md` | Putaway retrospective |
| `08-wms-roundtable-skill.md` | WMS roundtable skill notes |

## Numbering Notes

Documents `01-*` and legacy deployment notes were archived when this workspace
was consolidated. The current active sequence intentionally starts at `02`.
Release-specific logs may be added after the numbered product/engineering
documents; prefer the next unused number and update this index when adding one.
