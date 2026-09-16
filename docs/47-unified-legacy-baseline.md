# Unified GreaterWMS legacy delivery baseline

Reconciliation date: 2026-09-16. The delivery branch is `main`; use its verified remote HEAD rather than any historical branch name as a release identity.

## Histories reconciled

| Source | Original tip | Decision |
| --- | --- | --- |
| Previous main | `5371d0af4858d04ac007b8940d47d908abeec163` | Preserve ancestry and canonical Mail2Task redirects; supersede its Dashboard mail panel with the separate workbench |
| Latest legacy business line | `ede37c11db51317f0adca3449393e9d17dc8eb76` | Keep its Django workflow, Vue/Quasar shell, permissions, shared operational table, date/count fixes and personnel view |
| Previous release line | `347d599424ef5f0f4d5a38b9294f22bb9d34a8a3` | Preserve ancestry; warehouse permissions and labels are already covered by the newer implementation |

The `/mail2task` and `/source-intake` HTTP entry paths both redirect to `/#/mail2task`. The warehouse Dashboard contains only `operations-board`; `mailTaskBoard.vue` is superseded. The merge resolution was reviewed beyond conflict markers because Git automatically reintroduced the old Dashboard panel in an otherwise cleanly merged file.

The root snapshot `a026140` and the FastAPI/React migration history have no common ancestor with this legacy line. They remain a separate experiment; do not use `--allow-unrelated-histories` to fold them into the product.

Archive references under `archive/before-integration-20260916/` preserve the pre-integration tips. Only work branches whose commits are contained in the accepted main may be deleted. Historical and migration references are not release selections.

## Working directory and Cursor

On the audited Mac, the canonical checkout is `/Users/max/Projects/GreaterWMS`; the workspace file is `/Volumes/ORICO/Cursor 指导/GreaterWMS.code-workspace`. Git data stays on the local filesystem because the external volume produced AppleDouble pack-index artifacts during setup.

`/Users/max/Desktop/test/Program/greaterwms-poc` is a preserved detached V2.1.49 checkout. `/Volumes/MaxRelocated/WMS` belongs to `wms-quickstart`. Do not infer the repository from a window name.

Start every task with:

```sh
python3 scripts/check_workspace.py
```

Before editing, use a clean work branch based on the current main and run `python3 scripts/check_workspace.py --require-work-branch`. The output records repository, branch, commit and dirty state. Check existing work before making changes; do not reset someone else's worktree.

Cursor Terra medium is the ordinary implementation default. Narrow documentation/text work can use Luna low; difficult shared boundaries can receive focused Sol high review. Model choice is per task, not a global setting change.

## Regression and merge gates

- `python scripts/run_baseline_tests.py`: authorization, ASN, receiving, outbound, Mail2Task/Pack List, transport and dashboard regressions in an isolated in-memory database, with network disabled.
- `cd templates && npm ci --legacy-peer-deps && npm run build`: includes both the shared operational table check and the legacy release contract.
- Browser verification must cover representative legacy pages, independent Mail2Task, the Dashboard, direct entry paths and list pagination. Static contracts protect specific integration invariants; they do not establish visual or business correctness alone.
- GitHub's `legacy-baseline` check requires backend regression and frontend build success. Use PRs with preserved merge ancestry; avoid squash/rebase when reconciling historical release branches.

Receiving and transport lists now use server-side `page` / `max_page` pagination, a 200-row API page limit and stable descending ID order. Their Quasar tables expose page controls and default to 30 rows; refresh, linked-number filters and receiving assignment reload the first page. Four regression tests cover eight-row visibility at the API, records beyond 200, page limits, tenant isolation and invalid pages.

The npm lock repair adds missing optional macOS dependency entries without intentionally upgrading existing package versions. The CI installation uses the lock rather than a fresh dependency resolution.

## Known separate work

This integration establishes one legacy delivery baseline. It does not implement the full phase-one multi-owner pallet model, customer isolation, supervisor approval or business acceptance plan. The previously reviewed cycle-count/Customer authorization gaps remain separate priority work; passing existing tests is not a claim that these gaps are fixed.

The remaining visual audit includes the inbound layout spacing, modal conventions, status labels, and broader page-template consistency. Preserve the existing GreaterWMS visual language when implementing that work.

Production's running SHA must be verified separately. Branch names, historical production tags and a green merge do not establish which frontend/backend deployment is currently live.
