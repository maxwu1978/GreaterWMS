# GreaterWMS CLI Installation

The CLI is a Node.js command-line client for the GreaterWMS API. It supports
the same tenant isolation, role checks, Agent preview/confirmation flow, and
audit operator headers as the web application. It never connects directly to
the database.

## Install

Requirements: Node.js 18 LTS or newer.

```shell
git clone --branch codex/cli-install-info https://github.com/maxwu1978/GreaterWMS.git
cd GreaterWMS
node tools/greaterwms.mjs --help
```

The public machine-readable contract is available without authentication:

```shell
curl -fsSL https://api.maxsmartwms.online/cli/install/
```

The web application exposes the same information from the `CLI Setup` menu
page. AI Agents should read the endpoint before constructing commands instead
of hard-coding an API URL or authentication assumption.

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
