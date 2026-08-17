# GreaterWMS CLI Installation

The CLI is a Node.js command-line client for the GreaterWMS API. It supports
the same tenant isolation, role checks, Agent preview/confirmation flow, and
audit operator headers as the web application. It never connects directly to
the database.

## Install

Requirements: Node.js 18 LTS or newer.

```shell
mkdir -p greaterwms-cli && cd greaterwms-cli
curl -fsSL https://api.maxsmartwms.online/cli/download/ -o greaterwms.mjs
chmod +x greaterwms.mjs
node greaterwms.mjs --help
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force greaterwms-cli | Out-Null
Set-Location greaterwms-cli
Invoke-WebRequest https://api.maxsmartwms.online/cli/download/ -OutFile greaterwms.mjs
node greaterwms.mjs --help
```

The public machine-readable contract is available without authentication:

```shell
curl -fsSL https://api.maxsmartwms.online/cli/install/
```

The CLI file itself is available at
`https://api.maxsmartwms.online/cli/download/`. The web application exposes the
same information from the `CLI Setup` menu page. AI Agents should read the
endpoint before constructing commands instead of hard-coding an API URL or
authentication assumption.

## Login

Administrator login uses the administrator username and password:

```shell
node tools/greaterwms.mjs login --env production --name ADMIN
```

Warehouse, QC, driver, manager, and other staff accounts use their staff name
and check code directly. They do not need an administrator to inject an OpenID:

```shell
node tools/greaterwms.mjs login --env production --staff --name STAFF
```

For automation, provide the check code through `GREATERWMS_CHECK_CODE`. The
CLI never writes the password or check code to disk. The opaque session is
stored at `~/.config/greaterwms/session.json` with mode `0600`.

Check the active role and session target:

```shell
node tools/greaterwms.mjs auth status --json
```

## Operating rules

Read commands can be run after login. Any write command must first be run with
`--dry-run`; execute only after reviewing the server preview and repeating with
`--confirm` plus the returned confirmation token and an idempotency key. Role
permissions are enforced by the server, not by hiding commands in the CLI.

Examples:

```shell
node tools/greaterwms.mjs dashboard-operations list --env production --json
node tools/greaterwms.mjs receiving list --env production --json
node tools/greaterwms.mjs sku list --env production --json
```

For Pack List, QC, receiving, transport, and outbound payloads, use the
workflow-specific references in `docs/pack-list-cli.md`,
`docs/inbound-process-and-exception-logic.md`, and `docs/outbound-cli.md`.

## Outbound Test Suite

Warehouse operators can run the local outbound guard suite without changing
any WMS data:

```shell
node tools/outbound-cli-test-suite.mjs
node tools/outbound-cli-test-suite.mjs --catalog
```

For one disposable delivery note, live mode reads the order and requests
server previews only. It never confirms a write:

```shell
GREATERWMS_TOKEN=... node tools/outbound-cli-test-suite.mjs \
  --live --env test --dn-id 123 --dn-code DN-TEST-001 \
  --sku SKU-01 --qty 1 --driver Tom --staging-bin STAGE-LEFT-01
```

Use a disposable test tenant. A blocked preview is useful when it returns a
clear `Next action`; do not pass `--execute`, because confirmed writes must be
reviewed and run one by one with the normal confirmation token and idempotency
key workflow.

## Inbound Test Suite

Warehouse operators can run the local inbound guard suite without changing any
WMS data:

```shell
node tools/inbound-cli-test-suite.mjs
node tools/inbound-cli-test-suite.mjs --catalog
```

For a disposable test ASN, live mode performs read-only checks and server
previews only:

```shell
GREATERWMS_TOKEN=... node tools/inbound-cli-test-suite.mjs \
  --live --env test --asn-id 123 --asn-code ASN-TEST-001
```

Confirmed writes are intentionally not automated by the suite. Review each
preview and use the normal `--confirm`, `--confirmation-token`, and
`--idempotency-key` workflow on a disposable tenant.

For the Node simulation runner, requests have a 30-second timeout and at most
three exponential-backoff retries by default. Override them when diagnosing a
slow test service:

```shell
node tools/wms-sim-node.mjs --api https://greaterwms-v2-test3-sn.onrender.com \
  --user SIM-TENANT --pass '<password>' --day 0 \
  --timeout-ms 30000 --max-retries 3
```

The simulator records these values in its result JSON and stops with a
structured retry-limit error instead of retrying forever.
