# GreaterWMS Simulation Runner

`wms-sim-node.mjs` is an isolated-tenant workflow simulator for GreaterWMS. It is not a production data migration tool.

## Safety rules

- `--api` is required; the runner never defaults to a live API.
- The account name must start with `SIM-` or `SIM_`.
- A production host matching `*.maxsmartwms.online` additionally requires `--confirm-production-sim`.
- Cleanup additionally requires `--confirm-cleanup`.
- Storage bins and master-data names are scoped to the current run. The runner never deletes rows by a broad `SIM` prefix.
- A cleanup result is not considered successful if live staging assignments or undeletable workflow/audit rows remain. Use a disposable SIM tenant when the API does not expose deletion endpoints.

## Examples

Create an isolated tenant and run the smoke suite:

```bash
node tools/simulation/wms-sim-node.mjs \
  --api https://api.maxsmartwms.online \
  --register \
  --user SIM-TENANT-01 \
  --pass '<strong-password>' \
  --day 0 \
  --confirm-production-sim
```

Prepare an isolated tenant without creating workflow records:

```bash
node tools/simulation/wms-sim-node.mjs \
  --api https://api.maxsmartwms.online \
  --register-only \
  --user SIM-TENANT-01 \
  --pass '<strong-password>' \
  --confirm-production-sim
```

`/register/` seeds the platform's demo master data by design. `--register-only`
stops immediately after the new Admin login, so it creates no ASN, receiving,
outbound, inspection, or inventory workflow records. The preparation check must
therefore verify both facts: demo master data may exist, but workflow counts and
staging assignments must be zero before a simulation starts.

Run later days in the same SIM tenant:

```bash
node tools/simulation/wms-sim-node.mjs \
  --api https://api.maxsmartwms.online \
  --user SIM-TENANT-01 \
  --pass '<strong-password>' \
  --days 1,2,3 \
  --confirm-production-sim
```

To exercise the QC acceptance workbook path, add `--inspection-file <xlsx>`. The file is sent through preview -> confirm and is not stored by the runner.

Cleanup is explicit and reports failure when the API cannot remove workflow/audit data:

```bash
node tools/simulation/wms-sim-node.mjs \
  --api https://api.maxsmartwms.online \
  --user SIM-TENANT-01 \
  --pass '<strong-password>' \
  --day 0 \
  --cleanup \
  --confirm-cleanup \
  --confirm-production-sim
```

The process exits non-zero when a scenario, role audit, invariant check, or cleanup check fails. Results are written to `sim-results-<run>.json`.
