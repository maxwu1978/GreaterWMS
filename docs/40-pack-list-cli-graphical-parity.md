# Pack List CLI And Graphical Parity

The Pack List intake is intentionally one governed backend operation with two
operator surfaces:

| Surface | Preview | Confirm | Business effect |
| --- | --- | --- | --- |
| CLI | `POST /api/v1/agent/packlists/preview` | `POST /api/v1/agent/packlists/agent` | Save pre-arrival Pack List and expected packages only |
| Receiving page | Same endpoint | Same endpoint | Same as CLI |

Both surfaces send the same canonical payload:

- `source_text` and `file_name`
- optional `order_number`, `client_code`, and `warehouse_code` overrides
- `source_type=customer_pack_list`
- `create_inbound_if_missing`

The preview is the control point. It resolves customer and internal SKU
records, rejects duplicate source files and package codes, keeps `package_code`
separate from `serial_number`, warns when SN is absent, and leaves ETA unset.
Confirmation requires the preview token and a new `X-Idempotency-Key`.

The regression test is
`backend/tests/regressions/test_pack_list_import.py::test_cli_and_graphical_pack_list_operations_have_the_same_preview_and_state`.
It compares the CLI-shaped service preview with the graphical endpoint preview,
then confirms once and verifies:

- normalized rows and source checksum are identical;
- two package rows remain two package identifiers;
- SN count is zero when SN was not supplied;
- ETA remains null and the inbound order remains `expected`;
- inventory is unchanged and receiving is not started.

The comparison does not write production data. Deploying the feature requires
Alembic revision `021` before the new endpoints or graphical import panel are
used.
