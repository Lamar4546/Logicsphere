-- Align existing installations with Supabase Auth-backed registration.
-- Passwords live in auth.users, so app_users only stores the application profile.
BEGIN;

ALTER TABLE IF EXISTS app_users
  ALTER COLUMN password_hash DROP NOT NULL;

COMMIT;
