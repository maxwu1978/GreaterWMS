-- Production schema gap patch for the May 9, 2026 WMS release gate.
--
-- Scope:
--   Enable and force RLS on pick_allocations with the standard tenant and
--   platform-admin policies.
--
-- Preconditions:
--   - Render/Postgres backup or PITR readiness has been confirmed in the
--     Render Dashboard.
--   - A trusted operator has rerun the read-only schema checks and confirmed
--     pick_allocations RLS is the remaining production schema gap.
--   - This script is run against the production WMS Postgres database only
--     after explicit operator approval.
--
-- Render CLI note:
--   `render psql` requires --command in non-interactive mode, so this file is
--   the reviewed source SQL. Run the equivalent inline command from
--   docs/10-render-deploy-operations.md, or open an interactive psql session
--   and paste this script.
--
-- Do not include this file in automated app startup or CI jobs.

\set ON_ERROR_STOP on

\echo 'Phase 1/2: enable and force RLS on pick_allocations'
BEGIN;

ALTER TABLE pick_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pick_allocations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON pick_allocations;
DROP POLICY IF EXISTS admin_bypass ON pick_allocations;

CREATE POLICY tenant_isolation ON pick_allocations
    USING (tenant_id::text = current_setting('app.current_tenant_id', true))
    WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true));

CREATE POLICY admin_bypass ON pick_allocations
    USING (current_setting('app.is_platform_admin', true) = 'true');

COMMIT;

\echo 'Phase 2/2: post-patch verification snapshot'
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname = 'ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc'
ORDER BY indexname;

SELECT
    relname,
    relrowsecurity,
    relforcerowsecurity
FROM pg_class
WHERE relname = 'pick_allocations';

SELECT
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'pick_allocations'
ORDER BY policyname;
