# Platform User Cleanup Runbook

## Scope

The preferred production cleanup keeps exactly one named, active
`platform_admin` account and deactivates every other currently active user
across all tenants. It does not remove user rows or change tenants,
warehouses, inventory, orders, subscriptions, business master data, or audit
records.

The separate singleton hard-delete scope exists for authorized database
maintenance only; it is not the normal test-data cleanup path.

The legacy `non_admin_users` scope remains available for a narrower cleanup:
it deletes only `operator` and `client_viewer` rows and preserves all admin
roles. Use `deactivate_except_platform_admin` for the production account
consolidation described in this runbook.

Unknown or future user roles block the legacy cleanup. The singleton scope
explicitly includes all non-target roles in its delete set, so its preview
must be reviewed for the exact count and preserved email.

## Standard User Management

The **Users** page is the normal account-management workflow. Platform admins
can see users across all active tenants and can create tenant admins, operators,
and client viewers. They can also edit another user's name, job title, role,
operational permissions, and client assignment, as well as activate, disable,
or reset that account's password.

Tenant admins remain limited to operator and client-viewer accounts in their own
tenant. A platform admin cannot use the user-management endpoint to disable or
change the role of the account currently being used. Because the platform admin
is a singleton, there is no second platform admin account to switch to.

Changing a user's role recalculates the allowed permission set on the server.
Client viewers must remain linked to a client in the user's tenant. Disabling
an account takes effect immediately for existing JWT sessions because the live
account row is checked on every authenticated request.

## API Flow

1. A platform admin calls `POST /api/v1/users/cleanup/preview` with:

   ```json
   {
     "scope":"keep_one_platform_admin",
     "keep_platform_admin_email":"wuqingxin1978@icloud.com"
   }
   ```

   For reversible cleanup, call `POST /api/v1/users/deactivation/preview`
   instead with:

   ```json
   {
     "scope":"deactivate_except_platform_admin",
     "keep_platform_admin_email":"wuqingxin1978@icloud.com"
   }
   ```

2. The preview returns the exact deactivation count, the one preserved account,
   a short candidate sample, and a single-use confirmation token. The preview is
   persisted in `agent_evidence` for audit and expires after 30 minutes.

3. After human review, the platform admin calls
   `POST /api/v1/users/deactivation/agent` with the preview token and an
   `X-Idempotency-Key` header.

4. The confirmation recomputes the user set. If any user changed after the
   preview, the confirmation is rejected and a new preview is required.

The authentication dependency checks the live account row on every request, so
deleted or deactivated users cannot continue using an already-issued JWT.

## UI Flow

The platform admin opens **Users**, selects **Preview cleanup**, reviews the
delete count and the exact preserved email, then types:

```text
DEACTIVATE ALL ACTIVE USERS EXCEPT THE NAMED PLATFORM ADMIN
```

The UI then sends the confirmation request. Tenant admins do not see this
control and cannot call the endpoint.

## Recovery And Verification

This is a hard delete of user rows and is not reversible through the UI. Before
confirming production cleanup, verify the preview and retain the evidence id.
After reversible deactivation confirmation:

- refresh the Users page;
- verify the total user count is unchanged;
- verify only the named account remains active;
- verify the remaining account is `wuqingxin1978@icloud.com`, active, and has role `platform_admin`;
- inspect the matching `agent_evidence` row and idempotency result.

The API and bootstrap script reject creating a second platform admin, reject
promoting another user into that role, and reject demoting or deactivating the
sole platform admin. A partial unique database index provides the final race
condition guard after the active-admin migration is applied.

Do not use the older maintenance endpoint for this purpose. It preserves only
the current signed-in user and has a different tenant-data scope.
