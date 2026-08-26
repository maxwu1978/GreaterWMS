#!/usr/bin/env python3
"""Repository-level entry point for the canonical frontend table guard."""

from pathlib import Path
from runpy import run_path


CANONICAL_GUARD = Path(__file__).resolve().parents[1] / "templates" / "scripts" / "verify_legacy_table_contract.py"


if __name__ == "__main__":
    run_path(str(CANONICAL_GUARD), run_name="__main__")
