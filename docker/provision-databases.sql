\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I LOGIN', 'filament_manager_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'filament_manager_user') \gexec
ALTER ROLE filament_manager_user PASSWORD :'filament_manager_password';

SELECT format('CREATE ROLE %I LOGIN', 'spoolman_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'spoolman_user') \gexec
ALTER ROLE spoolman_user PASSWORD :'spoolman_password';

SELECT format('CREATE DATABASE %I OWNER %I', 'filament_manager', 'filament_manager_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'filament_manager') \gexec

SELECT format('CREATE DATABASE %I OWNER %I', 'spoolman', 'spoolman_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'spoolman') \gexec

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
