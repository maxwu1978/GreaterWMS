# Desktop-First Mobile Admin Audit

This audit converts the "desktop is management, mobile is execution" rule into
page-level acceptance criteria for Billing, Master Data, Users, Settings,
Migration, and Agent administration.

## Contract

Desktop-first pages may be available on phones, but their phone layout must not
pretend to be an operator execution path. A phone view is acceptable when it
offers quick lookup, selected-record review, and one safe edit path. It fails
when bulk management, dense filters, import centers, or configuration grids sit
in the first mobile viewport.

Every desktop-first phone page should answer:

1. Which management object am I looking at?
2. Is this page for quick review or selected-record editing?
3. What is the one safe action on phone?
4. Where do I go for full desktop management?

## Page Decisions

| Area | Desktop owner | Phone contract | Hidden or collapsed on phone | Safe phone action |
| --- | --- | --- | --- | --- |
| Billing workbench | Period execution, invoice review, batch status | Show current period state and selected invoice/client summary | Bulk invoice runs, wide reconciliation tables, complex period filters | Open selected invoice/client or return to billing settings |
| Billing settings | Rate cards, bill-to identity, tax/payment rules | Show selected client billing profile before editable fields | Rate-card version history, tax grids, bulk client comparison | Edit the selected client profile after row selection |
| Clients | Client master data, portal/billing settings | List clients, then edit one selected record | Activity history, portal setup detail, rate-card tables | Select client, edit core profile |
| SKUs | SKU master data and barcode maintenance | Search/select one SKU before editing | Bulk upload, packaging tables, advanced attributes | Edit selected SKU basics |
| Warehouses | Warehouse, zone, location, planner rules | Review selected warehouse and open setup/planner links | Location grids, planner canvas, AGV rules | Open selected warehouse or planner |
| Users | Team administration and permissions | Review users and selected user status | Permission matrix and role comparison tables | Open selected user; sensitive role changes prefer desktop |
| Receiving code/label settings | Label and matching configuration | Read current mode and selected rule | Batch code settings, template tuning | Open settings on desktop or edit a single selected rule |
| Migration | File mapping and import preview | Explain that imports are desktop-first; allow file status review | Upload/dropzone, mapping grid, bulk import confirmation | Review import status and open desktop import |
| Agent settings | Provider, secret, model, governance | Show provider health and whether agent is enabled | Full tool catalog, secret entry, model routing detail | Toggle enabled only after validation, or open desktop settings |
| Agent console | Assisted operations and governed tools | Use read-only checks and import preview summaries | Bulk writes, permission changes, high-risk confirmations | Run low-risk read tools or preview import |

## First View Rules

- Phone first viewport should use a compact management banner, not a dense
  table.
- If a row must be edited, the row must be selected before editable fields
  appear.
- Bulk actions must be hidden, disabled with clear copy, or moved behind a
  desktop-only affordance.
- Filters can exist, but they must be collapsed behind a single reveal.
- Import and mapping workflows should default to desktop; phone may show status
  or preview only.
- High-risk AI, billing, permission, and migration confirmations should name the
  desktop-preferred path even when technically possible on phone.

## Audit Checklist

Use this checklist before changing a desktop-first page:

1. Does the phone first viewport avoid wide tables and batch controls?
2. Does the page identify the selected record before showing edit fields?
3. Are bulk import, billing, permission, and destructive actions absent from the
   primary phone path?
4. Is there a clear route to full desktop management?
5. Are filters, history, audit logs, and secondary settings collapsed?
6. Does the phone page remain useful for quick lookup or selected-record review?
7. Are role and permission limits identical to the desktop API contract?
8. Does the page avoid horizontal overflow at a 390px viewport?

## Verification

Automated page audit remains the release gate for overflow and console errors:

```bash
npm run audit:production-pages
```

Admin mobile governance markers are guarded by:

```bash
npm run smoke:admin-mobile-governance
npm run smoke:admin-mobile-governance:visual
```

The visual guard is part of CI and covers Agent Settings, Agent Console, Users,
Clients/Billing Settings, Warehouses, SKUs, Receiving Code Settings, Receiving
Label Settings, and Migration at a 390px phone viewport.

Manual UAT should sample at least Billing settings, Clients, SKUs, Users, Agent
Settings, Agent Console, Receiving settings, Warehouses, SKUs, and Migration on
phone. The expected result is not full desktop parity. The expected result is a
calm quick-review surface with admin-heavy work collapsed or routed to desktop.
