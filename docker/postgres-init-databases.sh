#!/usr/bin/env bash
set -euo pipefail

filament_manager_password="$(< /run/filament-manager-bootstrap/filament_manager_db_password)"
spoolman_password="$(< /run/filament-manager-bootstrap/spoolman_db_password)"

psql \
  --set=ON_ERROR_STOP=1 \
  --set=filament_manager_password="$filament_manager_password" \
  --set=spoolman_password="$spoolman_password" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE filament_manager_user LOGIN PASSWORD %L CONNECTION LIMIT 30', :'filament_manager_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'filament_manager_user')\gexec

SELECT format('CREATE ROLE spoolman_user LOGIN PASSWORD %L CONNECTION LIMIT 20', :'spoolman_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'spoolman_user')\gexec

SELECT 'CREATE DATABASE filament_manager OWNER filament_manager_user ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'filament_manager')\gexec

SELECT 'CREATE DATABASE spoolman OWNER spoolman_user ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'spoolman')\gexec

REVOKE ALL ON DATABASE filament_manager FROM PUBLIC;
REVOKE ALL ON DATABASE spoolman FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE filament_manager TO filament_manager_user;
GRANT CONNECT, TEMPORARY ON DATABASE spoolman TO spoolman_user;

\connect filament_manager
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO filament_manager_user;

\connect spoolman
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO spoolman_user;
SQL
