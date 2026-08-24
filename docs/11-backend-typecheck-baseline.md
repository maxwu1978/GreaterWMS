# Backend Typecheck Baseline

## Current Gate

CI now runs `mypy app/ --ignore-missing-imports` as a required backend gate.

The backend is not yet strict-typed end to end. The current baseline keeps mypy
useful by checking typed bodies and configuration while suppressing the legacy
error classes that currently dominate the report. Before this baseline, strict
mypy produced hundreds of findings across endpoint annotations, generic
container types, optional tenant IDs, and SQLAlchemy dynamic attributes.

## Suppressed Debt Classes

The baseline suppresses these categories in `backend/pyproject.toml`:

- missing endpoint/function annotations
- bare `dict`, `list`, and `tuple` generics
- `Any` return/call noise from untyped libraries and PDF helpers
- optional string plumbing in older service constructors
- SQLAlchemy dynamic attribute and assignment noise

## Tightening Path

Handle the debt in small slices:

1. Add return annotations to one endpoint module at a time.
2. Type shared request/response helpers before service internals.
3. Replace bare containers with concrete aliases where the shape is reused.
4. Remove one disabled error code only after `uv run mypy app/ --ignore-missing-imports`
   passes without that suppression.

## Tightening Completed

- 2026-04-26: `operator` and `comparison-overlap` were removed from the
  disabled error-code list after both passed across `app/`.
