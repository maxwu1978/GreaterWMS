# WCS Sandbox Certification Report

Date: 2026-05-09

Scope: Dallas warehouse WCS / AGV sandbox certification after explicit operator
approval for live sandbox certification.

## Result

Status: certified for the approved live sandbox transport, guarded
certification task factory, callback, ready-config, quality-complete,
duplicate-completion callback, and `stepStatus=40` exception callback path.
The vendor field review is complete for the provided WCS API document;
the external infrastructure sign-off is also complete for the current
release/test stage.

The platform-side WMS gate is ready for the Dallas sandbox path:

- test account login succeeded as `tenant_admin` for tenant
  `221274c6-a6cf-49b2-92b8-06d422bbb421`;
- production `/health` returned `status=ok`; the latest factory-based pass ran
  against build `84ee9610a4600dd8b2ca89b7d817acb2c514baff`;
- Dallas warehouse `db096932-cbae-4cbe-8a24-28e05dda6c6c` has WCS config,
  a callback URL, and redacted WCS credentials;
- point mappings validated with 0 issues and 0 warnings;
- the approved `--confirm-import` mapping write completed successfully using
  the same exported Dallas mapping file;
- dispatch preview gate passed for task
  `24d4420e-5110-4cf2-8f38-d63217166a89`;
- ready-config and quality-complete previews built the expected WCS payloads;
- local AGV simulator smoke passed with route rendering, callback statuses
  `20`, `25`, `30`, exchange replay `200`, and a failed-task path;
- public `wms-agv-sandbox` accepted the live WCS transport task and emitted
  production callbacks for `20` and `30`;
- duplicate completion callback was accepted and did not create a duplicate
  putaway inventory transaction;
- fresh exception callback was accepted and moved the sandbox WMS task to the
  expected failed recovery state without inventory movement;
- the guarded certification task factory was re-run without direct SQL and
  produced a completed Dallas sandbox move task;
- live sandbox ready-config and quality-complete calls succeeded.

The first certification pass was blocked because Dallas still pointed to the
placeholder `https://wcs-simulator.invalid`. The follow-up pass deployed the
public AGV simulator sandbox, updated Dallas WCS config to
`https://wms-agv-sandbox.onrender.com`, fixed unauthenticated webhook tenant
context handling, and completed the approved live sandbox path.

## Evidence Summary

- Auth: `auth.whoami` decoded locally from the temporary bearer token.
- Health: production API responded `status=ok`; deployed build
  `5486d341e5a18d142299553f99d401dee8e69222`.
- Schema note: local `backend/.env` currently points `DATABASE_URL` at sqlite,
  so it is not usable as production Postgres schema evidence.
- WCS config: configured for Dallas, access token redacted, callback URL
  present, base URL `https://wms-agv-sandbox.onrender.com`.
- WCS mappings:
  - exported rows: 128;
  - mapped WMS locations: 120;
  - external dock-door points: 8;
  - validation issues: 0;
  - validation warnings: 0;
  - confirm import result: `status=configured`.
- Dispatch preview:
  - gate: `ok=true`;
  - already dispatched: `false`;
  - source point: `DAL-STO-DAL-A-01-01-01-01`;
  - destination point: `DAL-STO-DAL-B-01-01-01-01`;
  - planned endpoint: `POST /task/wlTaskInfo/addTransportTask`;
  - external WCS call: `false`.
- Live sandbox dispatch:
  - task: `24d4420e-5110-4cf2-8f38-d63217166a89`;
  - WCS task ID: `1778278075237001`;
  - source: `DAL-STO-DAL-A-01-01-01-01`;
  - destination: `DAL-STO-DAL-B-01-01-01-01`.
- Production callbacks:
  - `stepStatus=20` returned `200` and moved the binding to `in_progress`;
  - `stepStatus=30` returned `200` and moved the binding to `completed`;
  - duplicate `stepStatus=30` returned `200`, left the binding completed, and
    left exactly one putaway inventory transaction for the inbound reference.
- Exception callback:
  - test WMS task: `23d5d652-4ec0-4575-9f1d-dc6471a10ffe`;
  - WCS task ID: `1778298018550001`;
  - reference: `a0bb44d4-0c3d-45c4-85b6-c6a586a1304b`;
  - source: `DAL-STO-DAL-A-01-01-01-01`;
  - destination: `DAL-STO-DAL-B-01-01-01-01`;
  - sandbox `stepStatus=40` callback returned `200`;
  - binding status: `failed`, last step status `40`, last step name `异常`;
  - WMS task status: `failed`, `retry_count=1`,
    `failure_reason=simulated AGV error`;
  - inventory transactions for the exception reference: `0`.
- Ready-config preview:
  - endpoint: `/task/wlReadyAgvRobot/editReadyConfig`;
  - payload: `wrarSign=DAL-DOCK-27`, `wrarApiSign=1`, `wrarApiNum=1`.
- Quality-complete preview:
  - endpoint: `/QualityComplete`;
  - payload references `WCS-SANDBOX-QC-001`, status `qualified`.
- Bindings:
  - live sandbox binding ID:
    `2a76a0d8-4719-4ccb-adbe-541aeb78f5be`;
  - final binding status: `completed`;
  - final task status: `completed`, assigned to `agv:sim-agv-01`.
- Inventory movement:
  - one `putaway` transaction for reference
    `57f75167-061f-4e5b-93da-96418fa67c60`;
  - quantity change: `5`;
  - destination: `DAL-B-01-01-01-01`.
- Callback replay:
  - pre-dispatch completion and exception replay correctly returned
    "No WCS task binding matches callback";
  - after live dispatch, production callbacks matched the live sandbox binding
    directly.
- Factory-based certification pass:
  - DeepSeek reviewed the certification sequence, required evidence, and hard
    stops; the output was saved to `tmp/deepseek-wcs-certification-plan.json`;
  - dry-run factory preview returned `writes=false` and planned a
    `move/pending` sandbox task;
  - confirmed task: `13b2433f-9ab6-42a5-9193-a8a7c9100972`;
  - reference: `42f1f348-a93e-40ee-8c5c-1a4488151330`;
  - source: `DAL-STO-DAL-A-01-01-01-01`
    (`DAL-A-01-01-01-01`);
  - destination: `DAL-STO-DAL-A-01-02-01-01`
    (`DAL-A-01-02-01-01`);
  - dispatch gate and dispatch preview returned `ok=true`;
  - live sandbox dispatch created WCS task `1778331816600001`, task PSN
    `WCS-SBX-CERT-20260509130334-AC6B87`, binding
    `4feaaec1-23f9-4548-95e8-a84ba2ab76ee`;
  - AGV simulator emitted callback statuses `20`, `25`, `20`, and `30`;
  - final binding status: `completed`, last step status `30`;
  - final WMS task status: `completed`, assigned to `agv:sim-agv-01`;
  - inventory movement: one `move` transaction,
    `1ff79dad-c4ae-4038-9d24-a287965932e7`, quantity `1`, from
    `DAL-A-01-01-01-01` to `DAL-A-01-02-01-01`;
  - callback replay dry-run matched the completed binding and reported
    `would_create_inventory_movement=false`.
- Vendor field review:
  - source document: `AGV/WCS接口API.html`;
  - ready-config path: `/task/wlReadyAgvRobot/editReadyConfig`;
  - ready-config required body fields:
    `wrarSign`, `wrarApiSign`, `wrarApiNum`;
  - quality-complete path: `/QualityComplete`;
  - quality-complete body fields:
    `wtaskstepTid`, `wtaskinfoPsn`, `qualityStatus`,
    `unqualifiedBuffer`, `params`;
  - production preview evidence:
    `tmp/wcs-vendor-field-review-ready-preview.json` and
    `tmp/wcs-vendor-field-review-quality-preview.json`;
  - conclusion: no extra field variant is needed for the provided WCS API
    document. Revisit this only if the live vendor sandbox differs from that
    document.

## Next Required Action

The approved live sandbox path is now certified for normal transport
completion, factory-created certification tasks, and exception recovery.
Remaining follow-up before irreplaceable customer data or sustained production
traffic:

1. create an on-demand logical export if a downloadable archive is required in
   addition to Render PITR;
2. revisit the backend service plan before sustained production traffic or SLA
   commitment;
3. repeat the WCS field review only if the real vendor sandbox contract differs
   from `AGV/WCS接口API.html`.

## 2026-05-08 Follow-up Build

The next build step prepares the project to use the AGV simulator as a public
WCS sandbox when a vendor sandbox is not yet available:

- `agv-simulator` now exposes WCS-compatible vendor paths:
  - `POST /task/wlTaskInfo/addTransportTask`;
  - `POST /task/wlReadyAgvRobot/editReadyConfig`;
  - `POST /QualityComplete`;
  - `POST /loginToken`.
- `npm --prefix agv-simulator run smoke:dallas` covers both the existing local
  simulator paths and the WCS-compatible vendor paths.
- `render.yaml` includes a `wms-agv-sandbox` web service with `/api/health`
  health check.
- `tools/wms.mjs` includes a guarded `wcs config update` command:
  - `--dry-run` previews a redacted config update and validates HTTPS,
    callback URL, and credential presence;
  - `--confirm-config` applies the reviewed update;
  - omitted secrets are preserved, and new secrets should be passed through
    `--access-token-env` or `--password-env`.

This follow-up build is now in use for the certified live sandbox pass:

- Render service `wms-agv-sandbox` is live at
  `https://wms-agv-sandbox.onrender.com`;
- Dallas WCS config now points at that sandbox URL;
- normal transport dispatch, running callback, completion callback, duplicate
  completion callback, exception callback, ready-config, and quality-complete
  have been verified.

## 2026-05-09 Exception Callback Certification

The remaining WCS-specific failure path was certified against the public AGV
sandbox:

- created a fresh non-completed Dallas sandbox WMS move task under tenant
  `221274c6-a6cf-49b2-92b8-06d422bbb421`;
- dispatch preview gate passed with source
  `DAL-STO-DAL-A-01-01-01-01`, destination
  `DAL-STO-DAL-B-01-01-01-01`, and endpoint
  `POST /task/wlTaskInfo/addTransportTask`;
- live dispatch returned `200` and created WCS task `1778298018550001`;
- the simulator failure action emitted `stepStatus=40`;
- WMS accepted the callback, moved the binding to `failed`, moved the task to
  `failed`, set `retry_count=1`, and recorded
  `failure_reason=simulated AGV error`;
- no inventory transaction was created for the exception reference.

Note (resolved in follow-up): this certification task was inserted directly
through the production Postgres console under tenant context because the
application did not yet have a guarded API/CLI for creating a fresh
non-completed WCS certification task with both source and destination
locations. A sandbox certification task factory is now available through
`POST /api/v1/integrations/wcs/certification-tasks/{preview|create}` and
`wms wcs certification task --dry-run|--confirm-create`.

## 2026-05-09 Factory-Based Certification Pass

DeepSeek was invoked to review the next certification sequence and confirmed
the order of operations: dry-run factory task, confirmed factory task,
dispatch gate, dispatch preview, live sandbox dispatch, simulator callbacks,
binding/task verification, inventory movement check, and dry-run callback
replay. Hard stops were kept in place: sandbox only, no direct SQL business
mutation, and no live vendor calls outside the configured AGV simulator.

The pass used the guarded task factory rather than production console inserts:

- dry-run evidence:
  `tmp/wcs-factory-cert-20260509150246-preview.json`;
- confirmed factory task:
  `13b2433f-9ab6-42a5-9193-a8a7c9100972`;
- dispatch gate:
  `ok=true`, source `DAL-STO-DAL-A-01-01-01-01`, destination
  `DAL-STO-DAL-A-01-02-01-01`;
- live sandbox dispatch:
  WCS task `1778331816600001`, binding
  `4feaaec1-23f9-4548-95e8-a84ba2ab76ee`;
- simulator exchange:
  one exchange with four saved callbacks;
- callback statuses:
  `20`, `25`, `20`, `30`;
- final WMS state:
  binding `completed`, task `completed`, AGV unit `sim-agv-01`;
- inventory evidence:
  one `move` transaction for reference
  `42f1f348-a93e-40ee-8c5c-1a4488151330`;
- callback replay dry-run:
  matched the completed binding and did not plan a duplicate inventory
  movement;
- simulator smoke:
  `npm --prefix agv-simulator run smoke:dallas` passed with route rendering,
  WCS callbacks, exchange replay `200`, ready-config, quality-complete, and
  failed-task coverage.

## 2026-05-09 Vendor Field Review

The WCS ready-config and quality-complete payloads were compared against the
provided `AGV/WCS接口API.html` contract:

- `/task/wlReadyAgvRobot/editReadyConfig` requires `wrarSign`,
  `wrarApiSign`, and `wrarApiNum`.
- `/QualityComplete` accepts `wtaskstepTid`, `wtaskinfoPsn`,
  `qualityStatus`, `unqualifiedBuffer`, and `params`.
- The production preview commands returned `writes=false` and the same field
  names:
  - ready-config body:
    `{"wrarSign":"DAL-DOCK-27","wrarApiSign":"1","wrarApiNum":"1"}`;
  - quality-complete body:
    `{"wtaskinfoPsn":"WCS-SBX-CERT-20260509130334-AC6B87","qualityStatus":"合格","params":{"source":"vendor-field-review"}}`.

Conclusion: the current platform payloads match the provided WCS API document.
No adapter field variant is required until a live vendor sandbox proves a
different contract.

## 2026-05-09 Infrastructure And Final Gate

The external infrastructure signoff is accepted for the current release/test
stage:

- Render API recovery status for `WMS-VM`: `AVAILABLE`, with
  `startsAt=2026-05-05T09:00:08Z`;
- logical export: `dpg-d7akc4fkijhs73dp4ukg-a/2026-05-09T15:10Z`,
  created at `2026-05-09T15:10:00Z`;
- restore owner: current Render account `Max Wu <wuqxmark@gmail.com>`;
- accepted release/test-stage plan: backend `free` one-instance service with
  Render Postgres `basic_256mb`;
- production `alembic_version`: `015`.

Final gate after signoff:

- production health returned `status=ok` on build
  `84ee9610a4600dd8b2ca89b7d817acb2c514baff`;
- latest `main` CI remained green;
- production agent smoke passed with `failures=[]`;
- AGV simulator Dallas smoke passed, including route rendering, WCS callback
  statuses, exchange replay `200`, ready-config, quality-complete, and
  failed-task coverage.
