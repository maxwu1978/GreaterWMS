# WMS Agent

WMS Agent is the local governed operator shell for MaxSmart WMS. It runs on the
user's computer, requires WMS login before any WMS tool is available, and calls
the governed WMS Agent APIs with the authenticated user's bearer token.

The installed desktop launcher opens a native WMS Agent client window. The local
HTTP service runs behind that client; users should not need to open a browser or
terminal to operate it.

The agent does not store WMS passwords and never executes writes from chat text
such as "yes" or "go ahead". Writes require WMS preview evidence and a
confirmation card.

## Install On macOS

1. Unzip `wms-agent-0.1.0-macos.zip`.
2. Open `wms-agent/install/macos/install.command`.
3. Use the generated desktop launcher: `WMS Agent.app`.

The installer creates:

- app files in `~/Library/Application Support/WMS Agent`
- config at `~/Library/Application Support/WMS Agent/.env`
- a desktop client launcher that starts or wakes the local service

## Install On Windows

1. Unzip `wms-agent-0.1.0-windows.zip`.
2. Open `wms-agent\install\windows\Install WMS Agent.cmd`.
3. Use the generated desktop launcher: `WMS Agent.cmd`.

The installer creates:

- app files in `%LOCALAPPDATA%\WMS Agent`
- config at `%LOCALAPPDATA%\WMS Agent\.env`
- a desktop client launcher that starts or wakes the local service

Python 3.12 or newer is required on both platforms.

## Configuration

The default WMS API is production:

```text
https://api.maxsmartwms.online
```

Optional model planning can be configured in the installed `.env` file:

```bash
WMS_LOCAL_AGENT_MODEL_PROVIDER=deepseek
WMS_LOCAL_AGENT_MODEL_BASE_URL=https://api.deepseek.com/v1
WMS_LOCAL_AGENT_MODEL_NAME=deepseek-chat
WMS_LOCAL_AGENT_MODEL_API_KEY=...
```

If no model is configured, the local agent uses the deterministic safe router.
Model-suggested tools are accepted only when they are present in the tenant's
WMS `allowed_tools` list.

## Build Install Archives

From the repository root:

```bash
node wms-agent/scripts/build-installers.mjs
```

The archives are written to:

```text
dist/wms-agent/
```

## Developer Run

From the repository root:

```bash
node tools/local-agent.mjs start
```

or from this folder:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
wms-local-agent
```

Then open:

```text
http://127.0.0.1:8787
```

## Verification

Run the local smoke:

```bash
node tools/local-agent.mjs smoke
```

Verify the Dallas blueprint draft flow against the current AGV/CAD review
artifacts:

```bash
node wms-agent/scripts/verify-dallas-blueprint-flow.mjs
```

Run optional live dry-run checks only when a limited test WMS user is available:

```bash
LOCAL_AGENT_TEST_EMAIL=...
LOCAL_AGENT_TEST_PASSWORD=...
PYTHONPATH=wms-agent backend/.venv/bin/python wms-agent/scripts/verify_live_dry_run.py
```

Without credentials, the live dry-run script exits successfully and reports the
skip instead of touching production data.

## Ownership Boundary

WMS Agent is a consumer of the WMS platform contract. It may call documented WMS
APIs and render local workflow around them, but it must not define platform
capabilities.

WMS Agent owns:

- local login/session UX
- local provider and multi-model planning orchestration
- local skill loading, selection explanation, and prompt context
- local policy adjudication for model-suggested tools
- local UI, audit, redaction, confirmation cards, and demo scripts
- local wrappers around already documented WMS platform endpoints

Out of scope:

- creating backend `/api/v1/agent` endpoints
- changing platform tool catalogs, capability metadata, or write gates
- changing platform database models, migrations, or import semantics
- changing the WMS web Agent Console
