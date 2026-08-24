# Real Customer Onboarding Runbook

Use this runbook before loading irreplaceable customer data or turning a
warehouse plan into a persistent WMS/WCS configuration.

> Current-entrypoint warning (2026-08-24): the import and WCS CLI examples
> preserved later in this historical runbook reference tools/wms.mjs, which is
> not present in the current checkout. Do not execute those examples. Use the
> platform Agent API through the governed local agent or MCP adapter, and keep
> the same preview, evidence, confirmation, permission, idempotency, backup,
> and rollback gates.

## Current Closure Baseline

- Dallas AGV layout v2 is closed for the approved test tenant:
  - 108 WMS storage locations;
  - 108 AGV-accessible storage locations;
  - 119 WCS mapped items;
  - 108 storage WCS points;
  - 11 external WCS points;
  - 0 unmapped locations;
  - 0 non-AGV mapped items.
- Production backend health was verified on build
  `99af518e7a3e4d08a8de94ae54d43edaaee24e18`.
- The documentation-only closure commit `6a35ee8` passed CI.
- Render PITR was previously confirmed as available for the production
  database, and an on-demand logical export was created on 2026-05-09:
  `dpg-d7akc4fkijhs73dp4ukg-a/2026-05-09T15:10Z`.

## Intake Files

Collect real customer data with the templates in
`docs/templates/customer-onboarding/`:

- `warehouse-layout-intake.csv`
- `client-sku-master.csv`
- `inbound-orders.csv`
- `outbound-orders.csv`
- `inventory-snapshot.csv`
- `wcs-point-mappings.csv`

Keep source drawings, customer PDFs, Excel files, and email attachments outside
the repo unless the customer has explicitly approved storing them here.

## Sequence

1. Backup gate.
   - Confirm Render PITR is still available.
   - If a downloadable/off-platform archive is required, create or download an
     on-demand Render logical export before loading real customer records.
   - Record export id, timestamp, restore owner, and storage location in
     `docs/project-plan.md`.

2. Layout gate.
   - Read `docs/36-agv-planning-standard.md` before drafting any warehouse
     layout.
   - Read `docs/37-cad-layout-export-standard.md` before producing customer or
     vendor CAD/PDF output.
   - Preserve original building/zone dimensions in the dimension ledger.
   - Split AGV drive lanes, connector lanes, dock doors, wait points, chargers,
     and safety zones from storage zones.
   - Do not create WMS storage locations for dock doors or AGV-only areas.

3. Blueprint gate.
   - Generate or update the warehouse blueprint draft.
   - Run local review/CAD exports:

```bash
npm --prefix agv-simulator run cad:dallas
npm --prefix agv-simulator run cad:dallas:rack
npm --prefix agv-simulator run review:dallas
node wms-agent/scripts/verify-dallas-blueprint-flow.mjs
```

   - Run backend validate-only comparison:

```bash
cd backend && uv run python scripts/verify_dallas_blueprint_validate_only.py
```

4. Persistent apply gate.
   - Use `backend/scripts/apply_dallas_blueprint_live.py`.
   - New warehouse path requires:

```bash
WMS_DALLAS_APPLY_CONFIRM=ALLOW_DALLAS_BLUEPRINT_WRITE \
WMS_DALLAS_IMPORT_CONFIRM=ALLOW_DALLAS_WCS_MAPPING_IMPORT \
uv run python scripts/apply_dallas_blueprint_live.py
```

   - Existing `DAL` warehouse path additionally requires:

```bash
WMS_DALLAS_ALLOW_EXISTING_WAREHOUSE=true
```

   - Known Dallas layout-v2 legacy A-zone cleanup additionally requires:

```bash
WMS_DALLAS_EXISTING_CLEANUP_CONFIRM=ALLOW_DALLAS_EXISTING_LAYOUT_CLEANUP
```

5. Master data and order import gate.
   - Load or verify clients and SKUs first.
   - Run inbound, outbound, and inventory previews through the governed Agent
     API using the local agent or MCP adapter. There is no generic platform CLI
     in the current checkout.

   - Only confirm an import after row errors are zero, mapping is reviewed, and
     the operator provides an explicit approval plus idempotency key.

6. WCS/AGV operations gate.
   - Export and validate WCS mappings through the documented
     /api/v1/integrations/wcs endpoints or an approved Agent/MCP wrapper.
   - Configure WCS and create certification tasks in dry-run mode before any
     dispatch. Do not use the retired tools/wms.mjs examples from older
     versions of this runbook.

7. Release/capacity gate.
   - Run local release gates before commit.
   - Confirm GitHub CI success after push.
   - Confirm production `/health` is `ok`.
   - Revisit Render backend plan before sustained production traffic or any
     SLA commitment; the current free one-instance backend is accepted for
     release/test only.

## Agent Operating Rule

Other model agents should treat this runbook as the outer plan and the CLI/API
contracts as the execution boundary. They may run read-only commands and
preview commands, but any persistent write must come from a reviewed preview,
confirmation token, explicit operator approval, and idempotency key.
