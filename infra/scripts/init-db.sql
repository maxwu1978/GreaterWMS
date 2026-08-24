-- Initialize database for multi-tenant WMS with Row-Level Security

-- Create application role (restricted — subject to RLS)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'wms_app') THEN
        CREATE ROLE wms_app LOGIN PASSWORD 'wms_app';
    END IF;
END
$$;

-- Grant connect
GRANT CONNECT ON DATABASE wms TO wms_app;

-- The wms (superuser) role is used for migrations and admin queries (bypasses RLS).
-- The wms_app role is used by the application (subject to RLS).

-- Allow the app to read/write all tables in public schema
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO wms_app;
GRANT USAGE ON SCHEMA public TO wms_app;

-- Allow the app to set session-level variables for RLS
-- (app.current_tenant_id and app.is_platform_admin)
