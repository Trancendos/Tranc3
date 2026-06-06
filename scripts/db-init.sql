-- scripts/db-init.sql
-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Creates extensions and the settings_db user/schema if needed.
-- Alembic migrations (run by db-migrate service) create all tables.

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Ensure the tranc3 role has full privileges on the database
GRANT ALL PRIVILEGES ON DATABASE tranc3 TO tranc3;
