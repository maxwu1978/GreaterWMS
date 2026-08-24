# Local WMS Agent Customer Demo Script

This script demonstrates the local WMS agent as a desktop-side operator shell.
It avoids successful production writes and shows the governed preview,
evidence, and confirmation flow.

## Demo Goals

- Show that the agent runs locally and logs in to the customer's WMS account.
- Show that this process owns only the local runtime shell and consumes the
  existing WMS platform API contract.
- Show that model planning can use DeepSeek, Qwen, Kimi, or MiniMax when keys
  are configured, while secrets stay out of prompts, responses, and audit logs.
- Show planner comparison without executing any WMS tool.
- Show that WMS skills are available to guide local operations.
- Show that direct write tools are blocked.
- Show that preview, evidence detail, replay-preview, and failed evidence are
  available before any write.
- Show that high-risk confirmation requires typing the evidence id.

## Setup

1. Start the local agent:

   ```bash
   PYTHONPATH=wms-agent backend/.venv/bin/python -c 'from local_agent.server import main; main()'
   ```

2. Open `http://127.0.0.1:8787`.

3. Log in with a tenant-admin test account. Do not display or narrate the
   password during the demo.

4. Confirm the header shows:

   - current WMS API URL
   - model provider and source
   - configured provider roster
   - loaded WMS skills

## Talk Track

1. Login:
   "The agent is local. It authenticates to WMS first, then stores only a local
   session id in the browser. WMS tokens and model keys are redacted from audit
   views."

2. Read-only operation:
   Ask for an inventory, client, inbound, outbound, or settings lookup. The
   agent should route the request to an enabled read tool or model-assisted
   plan, then execute through the local WMS tool gate.

3. Settings preview:
   Select a settings category. For receiving codes and labels, use the simple
   form fields. Use Advanced JSON only for fields that are not represented in
   the simple form. Click Preview and show the diff/evidence card.

4. Evidence diagnostics:
   Use View evidence, Replay preview, and Failed evidence. Explain that replay
   preview is diagnostic only; it does not rerun a write.

5. Planner comparison:
   Enter the same read request and click Compare planners. Explain that every
   configured local model may suggest a tool, but the local policy adjudicator
   chooses only safe allowed tools and does not execute anything from this view.

6. Direct write block:
   Run or describe a direct import write attempt such as
   `migration.inventory.import`. The local policy rejects it and instructs the
   operator to run a preview first.

7. Strong confirmation:
   For a high-risk card, click Confirm without typing the evidence id. The
   server rejects the attempt. Type the evidence id to show the second
   confirmation step. In production demos, stop before any successful
   stock-changing import confirmation.

## Safe Demo Checks

- Use import preview with sample or intentionally invalid CSV to prove mapping
  and row validation.
- Use evidence detail and replay-preview on the generated evidence id.
- Use failed evidence list to show recovery visibility.
- Do not perform a successful production import confirm until rollback tests are
  complete for mixed-success batches.

## Success Criteria

- The user can log in and see configured model providers without exposed keys.
- The agent can use WMS skills and safe read/preview tools.
- Direct writes are blocked by local policy.
- Confirmation cards include evidence and idempotency context.
- High-risk confirmation requires typing the evidence id.
