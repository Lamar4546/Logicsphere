-- Migration: remove foreign key constraint from app_users.id to auth.users(id)
-- This makes `app_users` independent so the application can manage local users.
-- Run as a privileged DB user (service role) or via Supabase SQL editor.

BEGIN;

ALTER TABLE IF EXISTS app_users
  DROP CONSTRAINT IF EXISTS app_users_id_fkey;

COMMIT;
