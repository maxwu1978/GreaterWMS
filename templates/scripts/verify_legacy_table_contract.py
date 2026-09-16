#!/usr/bin/env python3
"""Fail fast when legacy operational pages stop using the shared GreaterWMS table."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SHARED_TABLE = SRC / "components" / "GreaterWmsOperationsTable.vue"
OPERATIONAL_PAGES = {
    "Dashboard": SRC / "pages" / "dashboard" / "operationsBoard.vue",
    "Mail2Task": SRC / "pages" / "sourceIntake.vue",
}

REQUIRED_SHARED_MARKERS = (
    'class="operations-board__table"',
    'table-class="operations-board__grid"',
    "dense",
    "flat",
    "bordered",
    'separator="horizontal"',
    "hide-bottom",
)

FORBIDDEN_PAGE_MARKERS = (
    "<q-table",
    "table-layout:",
    ".operations-board__table >>>",
    ".operations-board__table .q-table",
    ".source-intake-table table",
    ".source-intake-table th",
    ".source-intake-table td",
)

MAIL2TASK_REQUIRED_MARKERS = (
    'v-slot:body-cell-time',
    'v-slot:body-cell-flow',
    'source-intake-kpis',
    'Management snapshot ·',
    'Management view',
    'Mail flow',
    'emails</span>',
    'executiveMetricItems',
    "label: 'Due / Event'",
    "label: 'Owner / WMS'",
    "label: 'Flow'",
    'last_mail_at',
)

MAIL2TASK_FORBIDDEN_MARKERS = (
    "label: 'Sent / Recv'",
    "label: 'Source'",
    "label: 'Task / Mail'",
    'body-cell-received_at',
    'body-cell-source',
    'GM view · 总经理视角',
    'Mail direction · 邮件方向',
    '外部服务方发件',
    '台达客户发件',
    '内部协调',
    '封</span>',
)


def fail(message):
    raise SystemExit(f"GreaterWMS table contract failed: {message}")


def read(path):
    if not path.is_file():
        fail(f"missing file: {path}")
    return path.read_text(encoding="utf-8")


def main():
    shared = read(SHARED_TABLE)
    for marker in REQUIRED_SHARED_MARKERS:
        if marker not in shared:
            fail(f"shared table is missing required marker: {marker}")

    for page_name, page_path in OPERATIONAL_PAGES.items():
        page = read(page_path)
        if "GreaterWmsOperationsTable" not in page:
            fail(f"{page_name} does not reference GreaterWmsOperationsTable")
        if "<greater-wms-operations-table" not in page:
            fail(f"{page_name} does not render the shared table component")
        for marker in FORBIDDEN_PAGE_MARKERS:
            if marker in page:
                fail(f"{page_name} contains a private table definition or table rule: {marker}")

    mail2task = read(OPERATIONAL_PAGES['Mail2Task'])
    for marker in MAIL2TASK_REQUIRED_MARKERS:
        if marker not in mail2task:
            fail(f"Mail2Task is missing the canonical schedule/flow marker: {marker}")
    for marker in MAIL2TASK_FORBIDDEN_MARKERS:
        if marker in mail2task:
            fail(f"Mail2Task contains a legacy time/source marker: {marker}")

    print("GreaterWMS table contract passed: Dashboard and Mail2Task share the canonical q-table implementation.")


if __name__ == "__main__":
    main()
