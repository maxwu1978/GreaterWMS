# GreaterWMS development baseline

This repository's delivery branch is `main`. The product is the existing Django + Vue 2 / Quasar application in `templates/`. The FastAPI/React migration experiment is separate and must not be merged as unrelated history.

- Start by running `python3 scripts/check_workspace.py`. Record repository, branch, HEAD and dirty state. Preserve existing changes; develop on an isolated work branch based on the verified remote main.
- Use one reviewed PR per bounded change. Keep main protected, do not force-push it, and retain merge ancestry when reconciling release branches. After a verified merge, delete only work branches whose work is contained in main; preserve archived release references.
- Dashboard remains the warehouse operations board. Mail2Task is a separate route. Do not reintroduce `dashboard/mailTaskBoard.vue` from older branches.
- Keep the existing GreaterWMS shell and Quasar components. Operational boards use `GreaterWmsOperationsTable`; traditional business lists retain their established workflow. Changes need representative browser screenshots and real pagination checks, not only string-based guards.
- Use `templates/vercel.json` as the deployment entry configuration. `/mail2task` and `/source-intake` both redirect to `/#/mail2task`.
- Validate relevant backend changes with `python scripts/run_baseline_tests.py`, using a supported project virtual environment. It intentionally uses an in-memory database and denies outbound network. It does not prove production database concurrency or full business acceptance.
- Validate frontend changes with `npm ci --legacy-peer-deps` and `npm run build` from `templates/`, followed by affected browser flows. Keep generated assets consistent if a change updates the committed frontend bundle.
- Prefer Cursor `gpt-5.6-terra-medium` for ordinary implementation, `gpt-5.6-luna-low` for narrow documentation/text changes, and focused `gpt-5.6-sol-high` review for difficult or high-impact boundaries. Use tools for deterministic checks.
- Never point tests at production data. A merge is not proof that a production environment runs the same SHA; record deployment identity separately.

See `docs/47-unified-legacy-baseline.md` for the reconciliation record and known follow-up work.
