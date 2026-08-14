# Operations Board Role Work Queues

The GreaterWMS dashboard exposes two views for authenticated staff:

- `Active`: work that still requires an action.
- `History`: completed or cancelled work that the role participated in.

The API is `GET /dashboard/operations/`. Use `view=active` or `view=history`; the default is `active`. The response includes:

- `business_status`: the warehouse-facing state, such as `QC_PENDING`, `PUTAWAY_PENDING`, `MATCHED`, `COMPLETED`, or `CANCELLED`.
- `next_action`: the operation that should be performed next for active work.
- `assigned_role` and `assignee_name`: the current owner of the active step.
- `history_roles` and `history_assignees`: roles and named drivers that participated in a completed task.
- `action_route` and `reference`: used by the UI to open the relevant record directly.

## Role visibility

| Role | Active queue | History queue |
| --- | --- | --- |
| Manager / Supervisor | All tenant work | All tenant work |
| Warehouse | Warehouse-owned steps | Work with warehouse participation |
| Inbound | ASN and physical receiving | ASN and receiving history |
| QC | Receiving and ASN review steps | Work with QC participation |
| Driver | Tasks assigned to the driver's exact name | Completed tasks involving that driver's exact name |
| Logistics | Transport coordination and transport history | Transport history |
| Outbound | Outbound warehouse steps | Outbound history |
| StockControl | Warehouse and QC steps | Warehouse-participating history |

Unknown roles receive an empty queue. Filtering is performed on the server, not only in the browser.

## Receiving putaway assignment

After QC accepts quantity and a receiving record enters `PUTAWAY_PENDING`, a Warehouse or Inbound user can assign a driver with:

```http
POST /receiving/putaway/assign/
{
  "receipt_no": "RC-...",
  "driver_name": "Tom"
}
```

The Receiving page exposes the same action. A manager or supervisor may reassign an existing driver. The putaway endpoint enforces the stored assignment, so a different driver cannot complete the task by changing the request payload. If no pre-assignment exists, the first valid putaway operation records the driver atomically as a compatibility path.

## Operating rule

Staff should use the `next_action` shown in the Active view, then refresh the board. Once the process reaches a terminal state, the item moves to History and keeps the final business status and participating roles for review.
