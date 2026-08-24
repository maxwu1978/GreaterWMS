# WMS Figma Design System v1

## Status

- Figma file: https://www.figma.com/design/EgmC0PmzGCccExylTDQ3Zb
- Code token bridge: `frontend/src/shared/design/wmsDesignTokens.ts`
- Current scope: foundations, page patterns, mobile workflow rules, and component backlog.
- 2026-05-03 setup: Figma foundation variables, text styles, card shadow style, v1 documentation pages, and component pages for `WMS/DataTable`, `WMS/StatusBadge`, `WMS/Button`, `WMS/FilterPill`, `WMS/ScanPanel`, `WMS/MetricTile`, `WMS/MobileFlowGuide`, `WMS/TaskCard`, `WMS/FormField`, and `WMS/AppShell` were created.
- 2026-05-03 adoption status: plan items 1 and 2 are complete for documentation/design-system ownership. The mobile-first WMS page language is documented here and in `docs/09-action-first-page-discipline.md`, and Figma is now the shared design source for foundations, reusable page patterns, mobile workflow rules, and component handoff.
- 2026-05-03 mobile UAT reference: page `16 Mobile UAT Flow / 2026-05-03` was added to the Figma file. It captures the six phone-screen rules, canonical mobile screen stack, implementation mapping, module priority, and acceptance checklist.

This is the first shared design source for WMS interface decisions. Production behavior, permissions, workflow status rules, API contracts, and validation still live in the application code and backend. Figma is the source for layout language, visual hierarchy, interaction intent, and handoff specs.

## Why Figma Is Being Added

The current WMS UI has grown organically in Tailwind classes. The strongest language is already visible in Receiving, Putaway, Inventory, Billing, and Client management:

- Warm workbench background with white or soft cream surfaces.
- Dark ink primary actions.
- Pill-shaped filters, chips, and status badges.
- Rounded table shell with numbered rows and mobile card rows.
- Step-based mobile flows for scan-heavy warehouse work.
- Dense operational pages where lists lead and detail opens after selection.

Figma gives us a place to standardize these decisions before applying them across desktop, iPad, and phone.

## Foundation Tokens

These tokens are mirrored from current code and should be used before inventing new colors or spacing.

| Token | Value | Use |
| --- | --- | --- |
| `color/ink` | `#13212c` | Text, primary buttons, selected pills |
| `color/page` | `#f2efe8` | App background |
| `color/surface` | `#ffffff` | Main cards and tables |
| `color/surface-soft` | `#f7f4ee` | Table headers, filters, quiet panels |
| `color/surface-warm` | `#fbf8f2` | Mobile detail cells and empty states |
| `color/muted-text` | `#61717d` | Secondary copy |
| `color/subtle-text` | `#7f8d98` | Eyebrows and helper labels |
| `color/border` | `#e3ddd2` | Default card border |
| `color/action` | `#24507a` | Active workflow steps and secondary emphasis |
| `color/success` | `#28543b` | Done, active, paid, valid |
| `color/warning` | `#91621a` | Pending, needs action |
| `color/danger` | `#9b452a` | Error, voided, blocked |
| `color/accent` | `#f7bf45` | Logo and light operational highlight |

## Page Language

Use these patterns as the default before creating page-specific layouts.

| Pattern | Rule |
| --- | --- |
| Workbench page | Hero summary, segmented tabs or filters, numbered table/list, focused detail panel only after selection. |
| Mobile workflow | One current task per screen, clear back action, visible step guide, scan/action area near the top, details collapsed below. |
| Table list | Reuse the WMS table shell: row number, sortable/filterable headers, compact rows on desktop, stacked cards on mobile. |
| Detail view | Start with order/task identity, then current action, then supporting details. Avoid showing every field before the operator needs it. |
| Settings page | Directory table selects the record. Edit panels remain read-only until a row is selected or in edit mode. |

## Mobile-First WMS Page Language

The current WMS page language is action-first and mobile-first. Desktop pages may expose more queue and supervisor context, but they should still follow the same ordering as phone and iPad operator flows:

1. Orient the operator with breadcrumb, page identity, and current order/task.
2. Show the active blocker or live queue lane.
3. Put the scan, form field, or confirmation action before secondary context.
4. Keep counts in chips or compact tiles when they guide the next action.
5. Move history, audit, optional package detail, and supervisor tools behind explicit reveals.
6. Keep empty states quiet: one primary action, one clear reason, no duplicate guidance blocks.

Receiving is the reference implementation for this language. Putaway, Picking, Shipping, Inventory, Dashboard, Login, and the app shell have adopted the same direction: compact mobile headers, list-first queues, current-step panels, full-width primary actions where appropriate, and overflow guards for filter and table surfaces. The 2026-05-03 mobile-flow pass adds compact phone queue cards for Inventory, Picking, and Shipping, and tightens the shared table/task/flow primitives so secondary details collapse behind explicit reveals; production adoption is confirmed only after the new frontend deployment and production gate pass.

## Component Backlog

Build these Figma components in this order. Do not start with a full shadcn migration.

1. `WMS/DataTable` - v1 Figma page created; React map: `frontend/src/shared/components/DataTable.tsx`.
2. `WMS/StatusBadge` - v1 Figma page created; React map: `frontend/src/shared/components/StatusBadge.tsx`.
3. `WMS/Button` - v1 Figma page created; React map: `frontend/src/shared/components/ActionButton.tsx`.
4. `WMS/FilterPill` - v1 Figma page created; React map: `frontend/src/shared/components/Pill.tsx`.
5. `WMS/MetricTile` - v1 Figma page created; React map: `frontend/src/shared/components/MetricTile.tsx`.
6. `WMS/MobileFlowGuide` - v1 Figma page created; React map: `frontend/src/shared/components/MobileFlowGuide.tsx`.
7. `WMS/ScanPanel` - v1 Figma page created; React map: `frontend/src/scanner/BarcodeScanner.tsx`.
8. `WMS/TaskCard` - v1 Figma page created; React map: `frontend/src/shared/components/TaskCard.tsx`.
9. `WMS/FormField` - v1 Figma page created; React map: `frontend/src/shared/components/FormField.tsx`.
10. `WMS/AppShell` - v1 Figma page created; React map: `frontend/src/shared/components/Layout.tsx`.

## Mobile Priority

The current mobile issue is not only width overflow. Several pages are still desktop-first. For mobile WMS work, every flow should answer these questions in order:

1. Where am I?
2. What task is active?
3. What must I scan or confirm now?
4. What happens after this step?
5. How do I go back to the work list?

Receiving should be treated as the reference pattern. Putaway, Picking, Shipping, and Billing follow after the shared mobile components are defined.

Recommended mobile implementation order:

1. Picking order preparation - mobile list-first pattern is now in production.
2. Shipping handoff - current-step-first mobile action panel is now in production.
3. Receiving queue - mobile next-action card, compact order cards, and horizontally contained filter pills are now in production.
4. Putaway queue - mobile task cards and compact queue counters are now in production.
5. Inventory focus - mobile current-scope panel and compact exception cards are now in production.
6. Dashboard - mobile next-floor-action entry is now in production.
7. Login and app shell - mobile header, language switcher, breadcrumb, and sign-in spacing have overflow guards.

## Figma To Code Workflow

1. Update tokens in Figma only after confirming they match or intentionally change `wmsDesignTokens`.
2. Create or update the Figma component.
3. Map the component to the existing React component or create a new shared component.
4. Verify in the browser at desktop, iPad, and phone widths.
5. Update this document when a new pattern becomes official.

## Figma Adoption Gate

Figma adoption is considered live for the current release baseline when these are true:

- Token names and visual intent match `frontend/src/shared/design/wmsDesignTokens.ts`.
- Each component page names the matching React component or intentionally records that the component is design-only backlog.
- Mobile workflow examples follow the action-first rules above.
- New page work starts from an existing workbench, table, detail, settings, or mobile workflow pattern instead of inventing a one-off language.
- Browser evidence still comes from the application. Figma documents intent; production remains the validation source.

## Code-Side Shared UI Primitives

The first low-risk primitives live in `frontend/src/shared/components`:

- `EmptyStatePanel` - extracted from the shared table empty state.
- `ActionButton` - primary/secondary/success/danger operational buttons.
- `MetricTile` - operational counters with optional route target; first production use is the dashboard summary strip.
- `Pill` - filter/status/count pill shell. Use the default `button` mode for interactive filters and `as="span"` for static chips.
- `TaskCard` - compact selectable task/list card for receiving, putaway, picking, and shipping queues. It intentionally keeps business state outside the primitive.
- `FormField` - generic label/help/error wrapper for text, select, and textarea controls.
- `Eyebrow` - standard uppercase section label.

Adopt these gradually in Putaway, Picking, Shipping, and Billing before touching the high-density Receiving files.

## Next Figma Build Steps

The v1 file now contains `00 Cover`, `01 Foundations`, `02 Page Patterns`, `03 Mobile Workflows`, `04 Components Backlog`, `05 Code Mapping`, `06 Components / DataTable`, `07 Components / StatusBadge`, `08 Components / Button`, `09 Components / FilterPill`, `10 Components / ScanPanel`, `11 Components / MetricTile`, `12 Components / MobileFlowGuide`, `13 Components / TaskCard`, `14 Components / FormField`, `15 Components / AppShell`, and `16 Mobile UAT Flow / 2026-05-03`. Continue in this order:

1. Continue replacing static chips with `Pill as="span"` only where the label/count shape already matches the primitive.
2. Apply `TaskCard` to remaining low-risk queue cards before touching deep receiving flow internals.
3. Introduce `FormField` gradually in settings forms and auth forms after the mobile layout is stable.
4. Continue replacing remaining local metric-card helpers with `MetricTile`, especially admin setup and planner summary areas.
5. Run desktop, iPad, and phone screenshots before changing Billing and Client management again.

## Boundaries

- Do not put business workflow state in Figma as a source of truth.
- Do not use Figma to bypass API or permission design.
- Do not import shadcn wholesale unless the WMS table, scan, and task-flow patterns are preserved.
- Do not create a new one-off page style when an existing workbench, table, or mobile workflow pattern fits.
