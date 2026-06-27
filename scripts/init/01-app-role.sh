#!/bin/sh
# Postgres init script (runs once, on first DB creation). Creates the non-privileged application
# role the app/worker connect as, so Row-Level Security always applies. The password comes from
# GHOSTCAL_APP_DB_PASSWORD in the container environment (never hard-coded).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE ghostcal_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
    PASSWORD '${GHOSTCAL_APP_DB_PASSWORD}';
GRANT USAGE ON SCHEMA public TO ghostcal_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ghostcal_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ghostcal_app;
SQL
