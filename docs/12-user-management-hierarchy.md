# User Management Hierarchy

## Roles

- `platform_admin`: system super admin. Can inspect and manage users across all
  tenant companies.
- `tenant_admin`: company admin. Owns the company workspace but cannot create
  or promote other super admins.
- `operator`: company child user for warehouse execution.
- `client_viewer`: company child user for client portal access.

## Management Rules

- Super admins can view all tenant users and create tenant-scoped users for a
  selected company.
- Company admins can manage only child users inside their own company:
  `operator` and `client_viewer`.
- Company admins cannot create, disable, reset, or promote `platform_admin` or
  `tenant_admin` accounts.
- Operators and client viewers cannot manage users, even if a stale or manually
  inserted permission includes `users.manage`.
- Permissions are clamped by role. Child users cannot receive company-admin or
  system-wide user-management authority through direct API payloads.

## Agent Permission Inheritance

The agent must inherit the caller's effective permissions. An agent run is never
a separate superuser path and must pass the same role clamp that normal UI and
API requests use.

The agent adds one extra tool gate on top of normal permissions:

1. the tenant has enabled the tool in Agent Settings
2. the caller has the required WMS permission after role clamping
3. the tool risk allows the requested surface and confirmation state
4. the backend endpoint performs the same tenant and permission checks as the UI

The detailed tool and confirmation contract lives in
[06-agent-console-spec.md](06-agent-console-spec.md#agent-operation-contract).

## Audit Command

Run the production access-control audit from `frontend`:

```bash
npm run audit:access-control
```

The audit creates a temporary `Access Audit ...` tenant, verifies the role
boundaries below, and then deletes the temporary audit tenant:

- Platform admin can see tenant user records across workspaces.
- Tenant admin can see only its own tenant users.
- Tenant admin cannot create `tenant_admin` or `platform_admin` users.
- Operator permission payloads are clamped and cannot retain `users.manage` or
  `billing.manage`.
- Client viewer permission payloads are clamped to `portal.view` and one
  assigned client.
- Operator and client viewer cannot access user management or tenant-admin
  billing settings.
- Client viewer can still access its portal dashboard and filtered inventory.
- Cleanup preserves `PLATFORM` and `GREENECOPO` operational rows.

## 2026-05-02 Audit Result

Command:

```bash
npm run audit:access-control
npm run uat:production:cleanup
```

Result: passed.

Verified outcomes:

- Temporary access audit tenant was created and then deleted.
- Tenant admin list was scoped to its own tenant.
- Tenant admin was blocked from creating `tenant_admin` and `platform_admin`.
- Operator permissions were clamped to `receiving.execute`.
- Client viewer permissions were clamped to `portal.view`.
- Operator and client viewer were blocked from `/users/` and tenant-admin
  billing settings.
- Operator could read operational inventory.
- Client viewer could read filtered inventory and open the portal dashboard.
- Platform admin could see the audit tenant users before cleanup.
- Cleanup deleted `1` temporary audit tenant and `5` tenant-scoped rows.
- Preserved operational rows deleted: `0`.
- Final cleanup dry-run confirmed test tenant candidates `0`, test rows `0`,
  and preserved operational rows `0`.

## Bootstrap

Create the first super admin from a trusted backend shell:

```bash
cd backend
PLATFORM_ADMIN_EMAIL=owner@example.com \
PLATFORM_ADMIN_PASSWORD='use-a-strong-password' \
uv run python scripts/create_platform_admin.py
```

The script stores super admins under a host tenant named `PLATFORM` because the
current `users` table is tenant-scoped. The `platform_admin` role is what grants
cross-company access at login.
