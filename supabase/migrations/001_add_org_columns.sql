-- Migration: add optional organization columns to match application schema
-- Adds `industry` and `country` to `organizations` if they do not already exist.
-- Run this as a privileged DB user (service role) or via supabase SQL editor.

BEGIN;

ALTER TABLE IF EXISTS organizations
  ADD COLUMN IF NOT EXISTS industry text;

ALTER TABLE IF EXISTS organizations
  ADD COLUMN IF NOT EXISTS country text;

COMMIT;
