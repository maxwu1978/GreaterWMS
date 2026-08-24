# WMS UI Language Rules

These rules keep warehouse pages clear, action-first, and testable. They apply
to operator flows first, then to admin and desktop management pages.

## Core Contract

Every operator page must answer three questions before it explains anything
else:

- What am I handling?
- Where am I in the task?
- Which action moves me forward?

Mobile pages should show one current object, one current problem, one primary
action, and one recovery path. Desktop pages may include more context, but the
main action and status language must stay consistent.

## Glossary

| Concept | Use | Avoid |
| --- | --- | --- |
| Inbound order | Inbound order | receiving work, live receiving |
| Package | Package | package work |
| Dock or staging | Dock, staging location | source staging |
| Putaway | Putaway | putaway handoff when an action is clearer |
| Picking | Picking | pick work |
| Shipping | Shipping | carrier handoff when tracking or ship is clearer |
| Work queue | Queue, list | workbench |
| Current task | Current task | focus, focused work |
| Completed | Completed | done state, finished state |

## Buttons

Button text names the action only. It should not explain the whole reason.

Good:

- Scan package
- Choose dock
- Confirm receipt
- Print label
- Return to list

Avoid:

- Open next matching package
- Move straight into the next inbound check
- Review carrier handoff and shipment context

Rules:

- Button text should be 28 characters or fewer.
- Use verbs first: Scan, Choose, Confirm, Print, Return, Open, Refresh.
- Do not combine two actions in one button label.

## Status And Action Words

Keep state words separate from action words.

Status words:

- Ready
- Receiving
- Staged
- Blocked
- Completed

Action words:

- Start receiving
- Continue
- Print label
- Return to list
- Refresh tasks

## Errors

Errors must include a recovery path. Use this structure:

What happened: This package was already received.

What to do next: Scan the next package or return to the receiving list.

Rules:

- Say what blocked the task.
- Say what the user should do next.
- Provide at least one safe exit: retry, refresh, scan again, open next,
  return to list, or go to settings.

## Mobile Copy

Mobile text should be shorter than desktop copy.

- Mobile title: 48 characters or fewer.
- Button text: 28 characters or fewer.
- Put history, counts, alternate codes, audit records, and details behind
  disclosure controls.
- Do not expose internal-only terms on mobile operator pages.

## Review Checklist

Ask these five questions before merging a page change:

- Can a user know the next step from the title and button alone?
- Is the sentence written from the warehouse operator's point of view?
- Does every blocked state tell the user where to go next?
- Can the copy be cut by 30% and stay clear?
- Does the phone first screen ask the user to do only one thing?

## Automated Checks

The frontend `check:ui-language` script enforces the first layer of these
rules:

- required language-rules documentation sections and glossary terms exist
- operator UI copy does not introduce blocked internal terms
- mobile titles stay short
- button labels stay action-sized
- recovery copy includes at least one next action

Run it before UI changes, before UAT, and in CI:

```bash
npm run check:ui-language
```
