# Generated Export Artifacts

This directory is for local generated review artifacts. The binary/image/CAD
outputs are intentionally not committed; regenerate them from source when a
fresh customer or vendor handoff is needed.

## Dallas AGV Layout V2

Customer/vendor review artifacts currently generated here:

- `dallas-agv-layout-v2-review.html`
- `dallas-agv-layout-v2-review.png`
- `dallas-agv-layout-v2-review.pdf`
- `dallas-agv-layout-v2-cad.dxf`
- `dallas-rack-detail-v1-review.html`
- `dallas-rack-detail-v1-review.png`
- `dallas-rack-detail-v1-review.pdf`
- `dallas-rack-detail-v1-cad.dxf`

Agent/backend verification artifacts:

- `dallas-local-agent-blueprint-draft.json`
- `dallas-local-agent-blueprint-review.png`
- `dallas-backend-wcs-validate-only-summary.json`

## Regeneration

Run from the repository root:

```bash
npm --prefix agv-simulator run cad:dallas
npm --prefix agv-simulator run cad:dallas:rack
npm --prefix agv-simulator run review:dallas
node wms-agent/scripts/verify-dallas-blueprint-flow.mjs
cd backend && uv run python scripts/verify_dallas_blueprint_validate_only.py
```

For CAD/DXF closure rules, use `docs/37-cad-layout-export-standard.md`.
For AGV planning rules, use `docs/36-agv-planning-standard.md`.
