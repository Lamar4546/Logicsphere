BEGIN;

ALTER TABLE shipments
  ADD COLUMN IF NOT EXISTS carrier_name text,
  ADD COLUMN IF NOT EXISTS tracking_number text,
  ADD COLUMN IF NOT EXISTS tracking_provider text,
  ADD COLUMN IF NOT EXISTS provider_tracking_id text,
  ADD COLUMN IF NOT EXISTS tracking_carrier text,
  ADD COLUMN IF NOT EXISTS tracking_status text,
  ADD COLUMN IF NOT EXISTS tracking_location text,
  ADD COLUMN IF NOT EXISTS tracking_events jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS carrier_eta_at timestamptz,
  ADD COLUMN IF NOT EXISTS carrier_eta_date date,
  ADD COLUMN IF NOT EXISTS ai_eta_at timestamptz,
  ADD COLUMN IF NOT EXISTS ai_eta_date date,
  ADD COLUMN IF NOT EXISTS ai_eta_source text;

CREATE INDEX IF NOT EXISTS idx_shipments_org_tracking_number
  ON shipments (organization_id, tracking_number)
  WHERE tracking_number IS NOT NULL;

COMMIT;
