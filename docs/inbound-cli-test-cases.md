# Inbound CLI Test Case Set

This is the warehouse-operator acceptance set for the GreaterWMS CLI. It is
based on the current inbound workflow, not on a hypothetical interface. The
cases cover pre-arrival, arrival, unloading, receiving, QC, exceptions,
putaway, roles, duplicate handling, and recovery.

## Safety Rules

- Run the local guard suite first:

  ```bash
  node tools/inbound-cli-test-suite.mjs
  ```

- Use a disposable test tenant for live testing. Live mode performs reads and
  server previews only; it does not confirm writes:

  ```bash
  GREATERWMS_TOKEN=... node tools/inbound-cli-test-suite.mjs \
    --live --env test --asn-id 123 --asn-code ASN-TEST-001 --sku 702-S --qty 1
  ```

- Every write must follow `dry-run -> review -> confirm` with the server's
  `confirmation_token` and a stable `idempotency-key`.
- A rejected command must not change ASN status, inventory, staging state, SN
  state, or Pack List history.
- The suite must never use a real customer ASN for confirmed writes.

## Operator Cases

| ID | Situation | CLI action | Expected result | Next operator action |
| --- | --- | --- | --- | --- |
| IN-001 | New email or Pack List arrives | `asn list --query` by container/order/customer | Existing active ASN is found or no match is returned | Reuse one ASN; create only when no active match exists |
| IN-002 | No existing ASN | `asn create --data ... --dry-run` | Preview shows one ASN and no inventory change | Review customer, container, SKU references, then confirm |
| IN-003 | Duplicate container/order | ASN preview or confirm is rejected | No second active ASN is created | Open the existing ASN and continue there |
| IN-004 | ASN lacks supplier and container reference | `asn create --data '{}'` | CLI rejects locally with a required-reference message | Supply a trusted supplier or container reference |
| IN-005 | Pack List contains customer SKU not internal SKU | `packlist import --dry-run` | Preview reports mapping/reconciliation exception | Map to an internal SKU; do not invent a match |
| IN-006 | Pack List has no ETA | `packlist import` | ASN remains `Pre Arrival`; ETA is `Not Provided` | Reserve capacity only if needed |
| IN-007 | Customer later sends ETA | `asn eta --id ... --dry-run` | ETA updates without inventory or physical arrival | Use ETA for scheduling; keep ASN pre-arrival |
| IN-008 | Customer changes ETA | Repeat `asn eta` with new time | Latest ETA is visible and event history is retained | Recheck the unloading plan |
| IN-009 | Email has conflicting delivery addresses | No physical inbound command | CLI cannot independently confirm the external address | Hold in review; confirm address/Dock with customer before dispatch |
| IN-010 | Need to reserve staging before arrival | `asn reserve-staging --dry-run` | Valid Stage-left/Stage-right capacity becomes previewable as `Reserved` | Confirm only the required package/load-unit slots |
| IN-011 | Not enough staging capacity | `asn reserve-staging --dry-run` | Server rejects reservation with capacity guidance | Choose another valid stage or reschedule; do not overbook |
| IN-012 | Truck arrives without ETA | `asn arrival --dry-run` | Actual arrival can be recorded while ETA remains unknown | Record arrival, then start unloading |
| IN-013 | Unloading requested before arrival | `asn unload-start --dry-run` | Server rejects because physical arrival is not confirmed | Mark arrival first |
| IN-014 | Missing or inactive unloading driver | `asn unload-start --dry-run` | Server rejects driver assignment | List driver records and assign an active driver |
| IN-015 | Invalid staging slot or wrong slot count | `asn unload-start --dry-run` | Server rejects invalid/insufficient staging | Use the exact package/load-unit count and valid stage slots |
| IN-016 | Unloading completes | `asn unload-finish --dry-run` | ASN moves to receiving only after physical placement | Keep staging occupied during QC and putaway |
| IN-017 | Receiving record has no active stage | `receiving create --dry-run` or `receiving qc --dry-run` | CLI/server rejects missing staging location | Repair/assign the active stage before QC |
| IN-018 | Exact quantity received | `asn receive --dry-run` or receiving flow | Received quantity equals expected; no quantity exception | Continue to QC/putaway |
| IN-019 | Shortage | Receiving with actual < expected | Shortage is recorded; only actual physical quantity can be put away | Resolve with customer approval or hold/reopen |
| IN-020 | More quantity | Receiving with actual > expected | More QTY exception is recorded | Confirm customer disposition before putaway of excess |
| IN-021 | Wrong SKU | QC/inspection import | Wrong SKU exception is open | Hold or reject; do not put away as the expected SKU |
| IN-022 | Duplicate SN scan | `inspection import --dry-run` | Duplicate SN is reported as an exception, not extra physical quantity | Review scan and resolve the duplicate |
| IN-023 | Missing expected SN | `inspection import --dry-run` | Missing SN exception is reported | Rescan or use approved `WAIVE_MISSING` with a note |
| IN-024 | Unexpected SN | `inspection import --dry-run` | Unexpected SN exception is reported | Verify Pack List/customer data or hold the unit |
| IN-025 | Damaged unit | QC workbook with damage/result | Damage exception is open and evidence/note is retained | Move to damage/repair/hold bin; do not normal-putaway |
| IN-026 | QC workbook is received instead of Pack List | `inspection import --dry-run` | QC evidence is imported as inspection data, not a Pack List | Keep Pack List status separate |
| IN-027 | Pack List arrives after receiving | `packlist import --late-reference --dry-run` | Late reference is stored as a revision without overwriting QC history | Confirm only after reviewing reconciliation |
| IN-028 | Pack List imported but not confirmed | `packlist list` / `packlist confirm --dry-run` | Status is `PENDING` / review required | Confirm or replace explicitly |
| IN-029 | Open serial/quantity exception | `serial exceptions --asn-code ...` | All unresolved exceptions are listed | Resolve each with action, note, and location where required |
| IN-030 | Resolve exception without note | `serial resolve --dry-run` | Server rejects incomplete decision | Add an auditable QC note |
| IN-031 | Repair or quarantine decision | `serial resolve ... REPAIR_REWORK/HOLD_QUARANTINE` | Resolution requires a valid non-staging location | Move the physical unit, then re-inspect |
| IN-032 | Missing-SN waiver | `serial resolve ... WAIVE_MISSING` | Waiver is recorded with note; no physical move is attempted | Recheck quantity and customer approval |
| IN-033 | Unresolved exception before putaway | `asn putaway --dry-run` | Affected quantity is blocked | Resolve, hold, repair, or reject first |
| IN-034 | Putaway without driver | `asn putaway --dry-run` | Server rejects missing driver | Assign a valid putaway driver |
| IN-035 | Putaway to staging bin | `asn putaway --dry-run` with Stage bin | Server rejects staging bin as final storage | Select an inventory storage bin |
| IN-036 | Putaway quantity exceeds accepted remainder | `asn putaway --dry-run` | Server rejects over-quantity | Query receiving/putaway remainder and retry with valid quantity |
| IN-037 | Driver changes mid-ASN | Putaway with a different driver | Server rejects driver mismatch | Continue with the assigned driver or manager reassignment flow |
| IN-038 | Partial putaway | Put away less than accepted quantity | ASN remains in progress; staging remains occupied | Continue remaining eligible quantity |
| IN-039 | Final putaway | Put away all accepted/approved physical quantity | ASN completes and staging is released | Verify stock, final bin, and event history |
| IN-040 | Repeat confirmation after network retry | Same command and idempotency key | No duplicate inventory/SN/staging effect | Query the result before retrying with a new key |
| IN-041 | Expired confirmation token | Confirm with old token | Server rejects without mutation | Run a new dry-run and use its token |
| IN-042 | Non-warehouse role attempts warehouse write | CLI with QC/driver token | Permission error; no mutation | Use the role responsible for the step |
| IN-043 | Wrong tenant ASN/SKU/bin | Read or preview with another tenant's id | Not found/permission rejection; no cross-tenant data | Verify login environment and tenant scope |
| IN-044 | Customer address conflict unresolved | Attempt arrival/unloading | Operationally blocked by review; no driver/AGV dispatch | Resolve the external address first; CLI has no email-confirmation action |
| IN-045 | Need to see why a record is blocked | `asn get`, `packlist list`, `serial exceptions`, `asn events` | Current state and audit trail are visible | Follow the returned next action, not the legacy tab name |

## Current CLI Coverage

### Supported end to end

- Find/list/get ASN, Pack List, staging slots, receiving records, drivers, and
  event history.
- Create an ASN and ASN detail through guarded Agent preview/confirmation.
- Import, replace, confirm, and late-reference Pack Lists.
- Set ETA, mark physical arrival, reserve staging, start/finish unloading,
  receive quantities, inspect SN/QC workbooks, resolve exceptions, and put away
  accepted quantities.
- Handle shortage, overage, wrong SKU, duplicate/missing/unexpected SN, damage,
  repair, quarantine, rejection, and partial putaway through the documented
  command set.
- Prevent duplicate writes through confirmation tokens and idempotency keys.

### Supported with an explicit business stop

- Customer/container/address conflicts: the CLI can preserve the ASN planning
  context and ETA, but it cannot independently confirm an external address or
  send the customer appointment email. The operator must resolve the conflict
  outside the WMS before arrival/unloading.
- Pre-arrival driver scheduling: the unloading driver is validated when
  unloading starts. There is no separate inbound appointment/driver assignment
  command before physical arrival.
- Customer SKU mapping: the AI Agent or warehouse operator must map the
  customer SKU to an internal SKU before importing the normalized Pack List.

### Required failure-message standard

Every rejected case must tell the operator:

1. What was rejected.
2. Whether any state changed. For preview and validation failures, it must say
   that no mutation occurred.
3. The exact next safe command or manual action.

The CLI now appends a `Next action:` line for common authentication, dry-run,
ASN reference, Pack List, staging, driver, arrival, SN/QC, putaway, permission,
and not-found failures.

## Acceptance Criteria

- Local guard suite passes with no network access.
- All live previews either return a valid confirmation plan or a specific
  business rejection with a next action.
- No rejected preview or confirmed retry changes inventory, SN count, staging
  occupancy, ASN status, or Pack List history.
- Exact, short, over, wrong-SKU, SN, damage, late-Pack-List, partial-putaway,
  driver, and capacity cases are visible on the ASN list and dashboard.
- The same case executed through CLI and the corresponding UI shows the same
  ASN code, customer abbreviation, ETA, staging, exception, and next action.
