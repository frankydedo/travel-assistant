-- One Postgres instance, separate databases (ADR-0014). The app database is created by POSTGRES_DB.
CREATE DATABASE keycloak;
CREATE DATABASE langfuse;

-- Read-only role for the pgweb inspection UI: the reviewer can look at bookings and inventory, never change
-- them (only the application code writes). Tables are created later by the migrations as "travel".
CREATE ROLE travel_readonly LOGIN PASSWORD 'travel_readonly';
GRANT CONNECT ON DATABASE travel TO travel_readonly;
GRANT USAGE ON SCHEMA public TO travel_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE travel IN SCHEMA public GRANT SELECT ON TABLES TO travel_readonly;
