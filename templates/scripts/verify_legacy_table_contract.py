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

    print("GreaterWMS table contract passed: Dashboard and Mail2Task share the canonical q-table implementation.")


if __name__ == "__main__":
    main()
