# Project Plan

## Current Focus

### UX Hardening: Trust, Guidance, and Navigation

Goal: make the product feel easier to understand, easier to move through, and more credible for first-time 3PL users evaluating a trial.

#### Workstream 1: Human-friendly imagery

- Add real visual anchors to the public site and auth surfaces instead of relying mostly on text and icon blocks.
- Introduce warehouse-themed illustrations or product screenshots on the landing page and login page.
- Use visuals to explain the operator journey: receive, control, pick, ship, bill, and client visibility.

#### Workstream 2: Cross-page navigation

- Add a consistent in-app orientation bar with breadcrumbs and obvious return paths.
- Surface a clear “back to dashboard” action from operational pages.
- Add “previous area” and “next area” links so users can move through the warehouse flow without relying only on the left sidebar.

#### Workstream 3: Guided first-run experience

- Keep the dashboard checklist tied to real setup progress.
- Extend guidance beyond headings so users know what to do after finishing a task on each page.
- Tighten empty states and action hints around warehouse setup, first inbound, first inventory action, and first outbound action.

#### Workstream 4: Comparative product polish

- Review public open-source WMS products for presentation patterns, navigation ideas, and feature storytelling.
- Borrow what works best for trust-building:
  - stronger screenshots and feature proof
  - clearer warehouse workflow framing
  - obvious demo / live-product affordances

## Immediate Execution

1. Add image-led sections to the landing page and login page.
2. Add global breadcrumbs and cross-page movement cues inside the app shell.
3. Re-test the product from the trial-user perspective after the navigation update.
4. Continue with richer screenshots and workflow-specific visual proof in the next pass.

## Next Focus

### BYO Model Agent Console

Goal: let customers use an in-product AI operations console while keeping model choice, jurisdiction, and data handling under their control.

#### Workstream 1: Customer-supplied model providers

- Support bring-your-own-model configuration instead of binding the product to one default LLM vendor.
- Let each tenant choose an approved provider such as Azure OpenAI, AWS Bedrock, Google Vertex AI, or a private model endpoint.
- Keep model routing and credentials tenant-scoped.

#### Workstream 2: Controlled WMS tool layer

- Expose a whitelist of business-safe tools instead of letting the model write directly to the database.
- Route actions through existing authenticated APIs such as inbound import, inventory lookup, client creation, and outbound order management.
- Require explicit user confirmation for high-risk actions such as billing changes, bulk writes, and destructive updates.

#### Workstream 3: Governance, audit, and compliance

- Record who invoked the agent, which model provider handled the request, what tools were called, and what changes were proposed or applied.
- Allow customers to set their own retention, logging, and approval policy according to internal legal or procurement rules.
- Keep region and provider choice visible so regulated customers can avoid unapproved cross-border model use.

#### Workstream 4: Practical first release scope

- Start with a browser-based Agent Console inside the authenticated product instead of a standalone external CLI.
- Focus the first release on high-value operational tasks:
  - inbound CSV mapping and import
  - inventory search and explanation
  - client and SKU setup help
  - outbound order intake guidance
  - migration field-mapping assistance

## Agent Console Immediate Execution

1. Write the BYO model and tool-governance specification.
2. Define the first approved tool whitelist and confirmation rules.
3. Add admin-facing provider settings for tenant-scoped model configuration.
4. Build the first in-app Agent Console around inbound import, migration mapping, and inventory lookup.

## 2026-04-10 Progress Record

### What has been hardened so far

- Guidance and onboarding were expanded across login, dashboard, setup, receiving, putaway, inventory, and picking so the product behaves more like an operator workflow and less like a static demo.
- Multi-language support was pushed through public pages and in-app operations in Traditional Chinese, English, Spanish, Hungarian, and German, including navigation, dashboard activity, inventory activity, and key warehouse flows.
- Receiving and putaway were connected into a clearer closed loop:
  - receive into staging
  - create or recover putaway tasks
  - plan locations visually
  - confirm formal putaway
- Inventory was reshaped from a flat table into a control surface with view switching, graphic location reading, cycle count, adjustment, and recent activity.
- Sidebar navigation was grouped into operational sections so the app feels less like an unstructured menu dump.

### Working lessons we should keep applying

- Every operator-facing sentence should come from i18n keys. Hardcoded English always resurfaces during real walkthroughs.
- Shared task queues must always be filtered by business intent. A picking page must not accidentally read putaway or cycle-count work just because everything is `pending`.
- Buttons need a visible downstream step. If the user cannot tell what happens next, the flow is not done yet.
- Warehouse pages should prefer visual mental models over database mental models:
  - aisle
  - rack
  - level
  - slot
  instead of raw IDs wherever possible.
- Closed-loop design matters more than isolated features. Every operational action should end in a clear new state, visible follow-up, or confirmation path.
- Production testing with the real tenant account catches issues that local mock data misses, especially for i18n, role visibility, and workflow state transitions.

### Picking-specific audit note

- Picking should only fetch `task_type=pick` tasks at both the queue view and the execution flow.
- The picking flow still needs a later enhancement to validate scanned location/SKU values against expected barcodes instead of accepting any scan event.
- Empty states should explain whether the missing work is:
  - not released yet
  - already completed
  - blocked by missing outbound allocation

## 2026-04-11 Progress Record

### Delivery progress

- Import Center was expanded into a unified intake surface for three document families:
  - inbound orders
  - outbound orders
  - inventory records
- Each document family now supports both file import and single-record entry so users are not blocked when a customer does not have a CSV ready.
- The public/auth domain strategy was hardened so canonical app traffic now lands on `app.maxsmartwms.online`, while:
  - `maxsmartwms.online`
  - `www.maxsmartwms.online`
  permanently redirect to the app domain and preserve paths such as `/login`.
- A self-service password reset flow was added across backend and frontend:
  - forgot password request
  - reset token validation
  - reset password submission
  - login-page recovery entry point

### Production validation completed

- Production API and frontend health were re-checked and are healthy:
  - backend health endpoint returns `{"status":"ok","version":"0.1.0"}`
  - frontend is serving successfully from Vercel
- Production warehouse flow was verified end-to-end across pages:
  - receiving
  - putaway
  - inventory
  - picking
  - shipping
- Outbound flow was also verified through live status transitions:
  - pending
  - picking
  - picked
  - packed
  - shipped
- The `wuqxmark@gmail.com` tenant-admin account was manually recovered in production after the email reset flow failed, and login was re-validated successfully.

### Current production risks and follow-up

- Password recovery is functionally shipped, but email delivery is still not production-ready.
- Root cause found in live logs:
  - SMTP delivery fails on Render with `Network is unreachable`
- Current consequence:
  - forgot-password requests return success to avoid email enumeration
  - but recovery emails are not actually delivered
- Temporary workaround:
  - manual admin/database password reset
- Recommended follow-up:
  - replace the current SMTP path with a stable API-based email provider
  - then re-test both verification email and password reset email in production

### Handoff note for next agent upgrade

- Canonical frontend domain:
  - `https://app.maxsmartwms.online`
- Canonical backend domain:
  - `https://api.maxsmartwms.online`
- Latest production backend deploy for password reset:
  - commit `baca63d`
  - Render deploy `dep-d7d0961kh4rs739gauig`
- Latest repo commit for canonical domain redirect rules:
  - `8f3c88c Force canonical frontend domain redirects`

### Billing workbench progress

- Billing was split into two clearer surfaces:
  - `billing` for execution
  - `billing-settings` for master-data configuration
- Billing execution now behaves like a period workbench instead of a mixed setup screen:
  - choose client
  - choose period
  - preview charges
  - generate draft invoice
  - track draft / sent / paid / overdue
- Billing settings now carries:
  - rate-card management
  - issuer billing profile
  - bill-to profile
  - tax region
  - payment terms
- Tax handling was hardened for two supported regions:
  - US = Sales Tax
  - EU = VAT
- Invoice totals now round to currency precision, and production validation confirmed:
  - billing preview
  - draft generation
  - sent / paid status updates
  - PDF download
- Billing queue visibility was improved:
  - queue spotlight cards
  - actionable status summary
  - clickable spotlight filtering
  - tighter empty-state handling
- UI polish delivered on billing:
  - removed large empty preview area by turning empty preview help into a compact expandable block
  - prevented status badges from wrapping into vertical-looking Chinese text

### Engineering environment maintenance

- Frontend build currently passes with `npm run build`.
- Backend test environment was hardened for local async SQLite runs by adding `aiosqlite` to dev dependencies in `backend/pyproject.toml`.
- Backend regression suite now passes through `uv run --extra dev pytest -q` with:
  - `42 passed`
- One real backend regression was fixed during maintenance:
  - CSV inventory import now keys inventory upserts by lot number as well as tenant / warehouse / location / SKU, preventing different lots from overwriting one another.
- Another real backend correctness issue was fixed during review:
  - rate-card listing is now ordered by latest effective date first, so billing screens no longer risk treating an older version as the current rate card.

### Review notes to carry forward

- Billing page still contains some legacy billing-settings state and mutation logic that is no longer part of the rendered execution UI. It does not currently break the flow, but it increases component weight and should be removed in a cleanup pass.
- Local Python test execution should prefer `uv run --extra dev pytest -q` so tests do not depend on globally installed tooling.
- When reviewing billing behavior, verify both frontend filtering and backend ordering together. The execution UI assumes the first rate card is the active one, so backend order must stay deterministic.
