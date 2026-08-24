-- Production Alembic provenance stamp for the May 9, 2026 WMS release gate.
--
-- Scope:
--   Mark the production database Alembic revision as 015 after the checked
--   schema, index, and RLS gaps have been resolved by targeted production DDL.
--
-- Why this is a stamp, not an upgrade:
--   Production was partially startup-healed while alembic_version stayed at
--   003. Replaying historical migrations 004-015 can re-run DDL against
--   existing objects. This script records provenance only after guarded
--   verification.
--
-- Preconditions:
--   - Render/Postgres backup or PITR readiness has been confirmed.
--   - Production schema/index/RLS gate reports no missing gaps.
--   - Operator explicitly approves the Alembic stamp write.
--
-- Render CLI note:
--   `render psql` requires --command in non-interactive mode, so this file is
--   the reviewed source SQL. Run the equivalent inline command from
--   docs/10-render-deploy-operations.md, or open an interactive psql session
--   and paste this script.

\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    current_versions text[];
    missing_indexes text[];
    rls_failures text[];
BEGIN
    SELECT COALESCE(array_agg(version_num::text ORDER BY version_num), ARRAY[]::text[])
    INTO current_versions
    FROM alembic_version;

    IF current_versions = ARRAY['015']::text[] THEN
        RAISE NOTICE 'alembic_version is already 015; stamp is a no-op.';
        RETURN;
    END IF;

    IF current_versions <> ARRAY['003']::text[] THEN
        RAISE EXCEPTION 'Refusing to stamp: expected alembic_version {003} or {015}, found %', current_versions;
    END IF;

    WITH required_indexes(name, alias) AS (
        VALUES
            ('ix_agent_evidence_tenant_action_status'::text, NULL::text),
            ('ix_agent_evidence_tenant_id', NULL),
            ('ix_agent_evidence_tenant_payload', NULL),
            ('ix_handling_units_tenant_order', NULL),
            ('ix_idempotency_tenant_operation', NULL),
            ('ix_idempotency_records_tenant_id', NULL),
            ('ix_inbound_order_lines_tenant_order', NULL),
            ('ix_inbound_orders_tenant_created', NULL),
            ('ix_inbound_orders_tenant_status_created', NULL),
            ('ix_inbound_packages_tenant_order_status', NULL),
            ('ix_inventory_tenant_live_metrics', NULL),
            ('ix_inventory_tenant_live_order', NULL),
            ('ix_inventory_tenant_warehouse_live_metrics', NULL),
            ('ix_inventory_tenant_warehouse_location_sku', NULL),
            ('ix_inventory_tenant_warehouse_sku', NULL),
            ('ix_inventory_transactions_tenant_reference', NULL),
            ('ix_invoices_tenant_client_created', NULL),
            ('ix_invoices_tenant_created', NULL),
            ('ix_invoices_tenant_status_created', NULL),
            ('ix_outbound_order_lines_tenant_order', NULL),
            ('ix_outbound_order_lines_tenant_sku_order', NULL),
            ('ix_outbound_orders_tenant_created', NULL),
            ('ix_outbound_orders_tenant_pick_readiness_created_desc', NULL),
            ('ix_outbound_orders_tenant_shipping_readiness_created_desc', NULL),
            ('ix_outbound_orders_tenant_status_created', NULL),
            ('ix_outbound_orders_tenant_warehouse_created', NULL),
            ('ix_outbound_orders_tenant_warehouse_pick_readiness_created_desc', NULL),
            (
                'ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc',
                'ix_outbound_orders_tenant_warehouse_shipping_readiness_created_'
            ),
            ('ix_outbound_orders_tenant_warehouse_status_created', NULL),
            ('ix_pick_allocations_order_id', NULL),
            ('ix_pick_allocations_order_line_id', NULL),
            ('ix_pick_allocations_task_id', NULL),
            ('ix_pick_allocations_tenant_id', NULL),
            ('ix_receiving_labels_tenant_order_status', NULL),
            ('ix_receiving_observed_codes_tenant_order', NULL),
            ('ix_tasks_tenant_queue', NULL),
            ('ix_tasks_tenant_reference', NULL),
            ('ix_tasks_tenant_status_type_priority_created', NULL),
            ('ix_wcs_bindings_tenant_psn', NULL),
            ('ix_wcs_bindings_tenant_status', NULL),
            ('ix_wcs_task_bindings_tenant_id', NULL),
            ('uq_agent_evidence_token', NULL),
            ('uq_idempotency_tenant_key', NULL),
            ('uq_tasks_inbound_putaway_handling_unit', NULL),
            ('uq_wcs_binding_tenant_task', NULL),
            ('uq_wcs_binding_tenant_wcs_task', NULL)
    )
    SELECT COALESCE(array_agg(name ORDER BY name), ARRAY[]::text[])
    INTO missing_indexes
    FROM required_indexes r
    WHERE NOT EXISTS (
        SELECT 1
        FROM pg_indexes i
        WHERE i.schemaname = 'public'
          AND (i.indexname = r.name OR i.indexname = r.alias)
    );

    IF array_length(missing_indexes, 1) IS NOT NULL THEN
        RAISE EXCEPTION 'Refusing to stamp: missing required indexes %', missing_indexes;
    END IF;

    WITH required_rls(relname) AS (
        VALUES
            ('agent_evidence'::text),
            ('idempotency_records'),
            ('locations'),
            ('pick_allocations'),
            ('tasks'),
            ('wcs_task_bindings'),
            ('zones')
    )
    SELECT COALESCE(array_agg(r.relname ORDER BY r.relname), ARRAY[]::text[])
    INTO rls_failures
    FROM required_rls r
    LEFT JOIN pg_class c ON c.relname = r.relname
    WHERE NOT COALESCE(c.relrowsecurity, false)
       OR NOT COALESCE(c.relforcerowsecurity, false);

    IF array_length(rls_failures, 1) IS NOT NULL THEN
        RAISE EXCEPTION 'Refusing to stamp: RLS is not enabled/forced for %', rls_failures;
    END IF;

    UPDATE alembic_version
    SET version_num = '015';
END $$;

COMMIT;

SELECT version_num FROM alembic_version ORDER BY version_num;
