# Action-First Page Discipline

This is the current UI baseline for operator-facing warehouse work in MaxSmart WMS.

The intent is simple: every active operational surface should help the operator clear the next blocker with as little reading friction as possible.

## Core Rules

0. Primary Task Contract

- Every mobile workflow page must answer three questions in the first viewport:
  - which object am I handling now
  - what is the current problem or required step
  - which one control moves the work forward
- If the page cannot answer those questions without the operator reading a
  dashboard-like collection of counts, tabs, filters, history, and buttons, the
  mobile surface has failed the contract.
- The current object can be an order, package, task, SKU/location pair, carton,
  or shipment. It must be visible as copyable text when it is a code the
  operator may need to scan, type, or read aloud.

1. One primary action per first screen

- The first screen of a live workflow should answer:
  - what am I working on
  - what is blocked
  - what do I press next
- If a surface is trying to explain the workflow, summarize the queue, and present the action at the same time, it is too heavy.

2. Blocker says the problem, button says the action

- Use compact blocker language.
- Let the main button carry the next move.
- Avoid a second explanatory sentence that repeats what the blocker and button already made obvious.

3. Secondary context must step back

- Template summaries, captured-code management, extra package details, and similar secondary context should stay behind explicit reveals unless the operator is actively using them.
- First screens should not open detailed management panels by default unless they are directly required to clear the current blocker.
- Alternative suggested codes should not compete with the recommended code on
  phones. Show one recommended code by default, make it fully visible and
  copyable, and move other codes behind "Show other codes" or an equivalent
  reveal. Never truncate a code in a way that prevents copying the full value.

4. Do not repeat state across layers

- If a queue chip already says the package is blocked, do not repeat the same state in a second status badge.
- If a header already shows the source or route, do not add the same fact again in a checklist or summary card.
- If a lower section already owns a concept, remove it from the summary above.

5. Empty states should stay quiet

- No-work screens should not behave like dashboards.
- Prefer:
  - one calm primary card
  - one lightweight secondary card
  - one clear next action
- Hide zero-value rails, dense filter bars, and exception boards until the operator explicitly asks for history or all orders.

6. Mobile and desktop share the same discipline

- Mobile is still more operator-first.
- Desktop can show a little more context.
- But both should follow the same order:
  - identity
  - blocker
  - action
  - secondary context on demand

7. Mobile must make the operator do one thing

- The first mobile screen must not behave like a dashboard. It should give the
  operator exactly one recommended action.
- The primary card should answer:
  - what should I do now
  - which order, package, task, or location it applies to
  - what button moves the work forward
- Counts, filters, history, supervisor tools, lifecycle tabs, and exception
  context belong behind a reveal such as "View counts or change queue".
- Do not place competing primary actions in the same mobile viewport. If there
  are two possible actions, choose the operationally safest next one and move
  the other behind secondary context.

8. Blocked mobile states must send the user back to the right place

- If the recommended action cannot be performed, the page must say why in one
  short sentence and provide one clear escape route.
- Examples:
  - missing warehouse setup -> link to the required setup step
  - no inbound work -> link to import/create inbound, or back to dashboard if
    the user cannot create work
  - missing permission -> back to dashboard with an admin-permission message
  - missing dock/staging choice -> focus the dock/staging selector or manual
    code field before showing confirm
- A disabled button alone is not enough on mobile. The blocked state needs an
  explicit next place to go.

9. The mobile primary task should fit in one screen

- Mobile pages should be designed so the current primary task can be understood
  and completed inside one phone viewport whenever the task itself is simple.
- "No scroll" is a target for the primary action, not an absolute ban on
  scrolling. Long lists, history, audit trails, table detail, and optional
  settings may scroll, but they must not be required to understand what to do
  next.
- If the first viewport cannot show the task identity, blocker, input/control,
  feedback, and primary action together, split the flow into smaller steps or
  move secondary context behind a reveal.
- Do not stack multiple workflow steps on one mobile screen when the operator is
  expected to act. One screen should normally contain one step and one primary
  action.

10. Put the active control before supporting information

- On phones, the operator should see the input, scanner, selector, or confirm
  control before dense summaries.
- Suggested values should default to one recommended value. Additional
  suggestions belong behind "Show other..." or an equivalent reveal.
- Validation feedback should appear next to the control that changed, not only
  at the bottom of the page.
- The primary action should remain easy to reach after input. Prefer a compact
  sticky footer or a near-control action when the step would otherwise scroll.

11. Mobile navigation must be explicit and shallow

- Every workflow screen needs a visible Back action that returns to the previous
  operational list, not an ambiguous browser-history dependency.
- Workflows should expose the next correct place when the current step is
  blocked.
- Mobile should hide desktop/back-office actions such as import centers,
  billing setup, deep configuration, and large table management unless the user
  explicitly opens an admin area.

12. Mobile density has three tiers

- Tier 1, always visible: current object, current blocker, one input/control,
  primary action, direct validation feedback.
- Tier 2, collapsed by default: counts, package/order context, optional fields,
  alternative codes, nearby queue items, supervisor notes.
- Tier 3, desktop-first or detail-only: audit history, full tables, bulk
  actions, admin configuration, import/export, billing setup, advanced filters.

13. Text and touch targets must fit physical work

- Button text should name the action, not describe the system.
- Labels should be short enough to scan while holding a phone.
- Tap targets should be at least 44px high, and destructive actions should not
  sit next to the primary confirm action without separation.
- Avoid horizontal scrolling on phones. A production mobile page with visible
  horizontal overflow fails the page review.

14. Exceptions must have a recovery contract

- Any operational error that blocks Receiving, Putaway, Picking, or Shipping
  must resolve into:
  - what happened
  - why the current action cannot continue
  - one primary recovery action
  - one safe escape route back to the operational list
- Repeated, stale, or already-completed work is not a dead-end error. Treat it
  as a state-change recovery: refresh, open the next unfinished object, or send
  the operator back to the correct queue.
- Scanner mismatches should keep the operator in the active work context and
  offer the next safe move, such as rescan the physical code, choose another
  slot, reset the pack check, or return to the work list. Do not let an
  exception recovery button bypass a required physical location or SKU scan.
- Backend messages should be mapped to operator actions instead of displayed as
  raw red text when the error affects a live floor workflow.

15. Successful transitions need feedback and a destination

- Every successful operator mutation should say:
  - what just completed
  - what changed state
  - what the next step is
- Avoid returning silently to an earlier step when the operator may read it as
  "the previous action did not work."
- Examples:
  - Package 1 confirmed. Next: scan Package 2.
  - All packages received. Continue to putaway.
  - Pick confirmed. Next: scan the next assigned task.
  - Pack check complete. Next: capture carrier and tracking.

16. Desktop is management; mobile is execution

- Desktop may own import centers, billing settings, master data management,
  complex filters, bulk actions, and reporting-style tables.
- Mobile may link to those areas, but they should not sit in the primary
  operator path. Put them behind an admin menu, setup link, or secondary reveal.
- A phone page should execute the current warehouse task. A desktop page may
  supervise, compare, configure, and repair.

17. Cards are for actionable objects

- Use cards for work items the operator can select or act on: package, task,
  order, shipment, SKU/location adjustment.
- Do not make every explanatory section a card. Supporting copy, counts,
  history, and setup guidance should usually be plain sections, compact hints,
  or collapsed detail.
- When too many cards appear, the page loses hierarchy. Keep the visually
  strongest card for the object that can be acted on now.

## Applied Baseline

### Receiving

- `/receiving` should act as an action board, not an explanation board.
- `Work queue` is the global splitter.
- `Shift handoff` should only keep true handoff signals.
- `Package dispatch` should focus on blocker-level package actions.
- `ReceivingFlow` first screens should prioritize:
  - current package
  - remaining quantity
  - current blocker
  - primary action
- Receiving is the reference template for the next mobile pass:
  - scan -> dock/staging -> quantity -> confirm
  - after confirm, show completed package identity and the next destination
  - if no package remains, route clearly to putaway instead of silently
    resetting the scan step

### Putaway

- `/putaway` should open on the work, not on a tutorial.
- Active tasks should prioritize:
  - task identity
  - route/source context
  - final-slot choice
  - confirmation
- Checklists should only contain real operator actions.
- On mobile, route filters, alternate suggestions, manual location selection,
  split planning, and task details stay behind reveals. The visible active task
  path is one selected task, one final-slot decision, one physical slot scan,
  and one confirm action.

### Picking

- `/picking` should show the pick list before scanner controls.
- Mobile active pick work should show one selected task at a time.
- Scan feedback belongs beside the active scan or quantity input.
- Recovery prompts hide the normal scan and confirm controls until the operator
  chooses a recovery action.

### Shipping

- Mobile Shipping should stay as two execution steps:
  - pack check
  - carrier handoff
- Pack check owns SKU/carton verification. Carrier handoff owns carrier,
  tracking, and final shipment confirmation.
- Documents, service level, cost, and shipping history are supporting details
  on phone and should not compete with the active step.

### Dashboard

- Mobile Dashboard should not become a miniature supervisor console.
- First viewport priority:
  - next recommended warehouse work
  - why that work matters now
  - direct route to the work
- KPI panels, trend cards, exception boards, and analytics belong behind
  secondary navigation on phone.

### Inventory, Billing, And Master Data

- Inventory mobile should start as lookup/count-adjust execution, not a desktop
  inventory table squeezed onto a phone.
- Billing, clients, SKUs, warehouses, users, imports, and settings are
  desktop-first management areas. Mobile views may support quick lookup or
  selected-record review, but bulk management should stay out of the operator
  path.
- The formal desktop-first phone audit is tracked in
  [docs/22-desktop-first-mobile-admin-audit.md](/Volumes/MaxRelocated/WMS/docs/22-desktop-first-mobile-admin-audit.md).
  New admin-heavy pages should follow that page-level contract before adding
  phone-visible bulk controls.

## Review Checklist

Before shipping a UI change to an operator-facing surface, ask:

1. Does the first screen have one obvious primary action?
2. Is any sentence merely restating what the chips and button already say?
3. Is the same state repeated in more than one layer?
4. Can secondary context move behind an explicit reveal?
5. In an empty state, does the page stay calm instead of trying to look busy?
6. On mobile, can the primary task be completed without scrolling past
   secondary content?
7. If the page must scroll, is the scroll only for optional context or lists?
8. Is there exactly one recommended mobile action and one obvious way back?
9. Are extra suggestions, filters, history, and admin actions collapsed or
   hidden on phones?
10. Does validation appear where the operator just acted?
11. After success, does the page state what completed and where to go next?
12. Are all visible codes complete and copyable, with alternatives collapsed?
13. Are cards reserved for actionable objects instead of every piece of copy?
14. Is the phone view executing work while desktop owns management?

## Verification

- Use production-style walkthrough scripts to validate this baseline, not only local intuition.
- Current action-first sanity coverage lives in:
  - `/Volumes/MaxRelocated/WMS/frontend/scripts/verify-receiving-putaway-action-surfaces.mjs`
