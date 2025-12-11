-- Fix PostgreSQL permissions for llhama_usr role
-- Run this as a PostgreSQL admin (superuser) to grant necessary permissions

-- Connect to the llhama database first: psql -U postgres -d llhama

-- Grant usage on all sequences to llhama_usr
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO llhama_usr;
GRANT CREATE ON SCHEMA public TO llhama_usr;

-- Grant sequence permissions explicitly
GRANT USAGE, SELECT ON SEQUENCE users_id_seq TO llhama_usr;
GRANT USAGE, SELECT ON SEQUENCE events_id_seq TO llhama_usr;

-- Make these permissions default for future sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO llhama_usr;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT INSERT, UPDATE, DELETE ON TABLES TO llhama_usr;

-- Set search_path for llhama_usr
ALTER USER llhama_usr SET search_path TO public;

-- Commit the changes
COMMIT;
