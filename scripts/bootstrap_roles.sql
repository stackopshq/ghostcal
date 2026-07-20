-- One-time provisioning of the application database role.
--
-- The app connects as a NON-superuser, NON-BYPASSRLS role so Row-Level Security always applies.
-- Migrations run as the owner/admin role; this role only gets DML on its tables.
--
-- Run once as the admin/owner role, passing the password as a psql variable (never hard-coded):
--   psql "$ADMIN_URL" -v app_password="$GHOSTCAL_APP_DB_PASSWORD" -f scripts/bootstrap_roles.sql

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
    CREATE ROLE ghostcal_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

ALTER ROLE ghostcal_app PASSWORD :'app_password';

GRANT USAGE ON SCHEMA public TO ghostcal_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ghostcal_app;

-- Future tables created by the admin role are auto-granted to the app role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ghostcal_app;

-- Re-assert append-only on the audit log, LAST.
--
-- The blanket GRANT above says ON ALL TABLES, and this script is idempotent and re-runnable — it
-- is how the app role's password gets rotated. Running it after the migrations therefore hands
-- UPDATE and DELETE back on `audit_events` and quietly destroys the one property that makes an
-- audit log worth keeping: that whoever wants an entry gone cannot remove it. No error, no failing
-- test, nothing to notice. So take them away again here, after the grant that would restore them.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'audit_events') THEN
    REVOKE UPDATE, DELETE ON audit_events FROM ghostcal_app;
  END IF;
END
$$;
