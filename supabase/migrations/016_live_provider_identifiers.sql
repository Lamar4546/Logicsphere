BEGIN;

ALTER TABLE shipments
  ADD COLUMN IF NOT EXISTS live_tracking_id text,
  ADD COLUMN IF NOT EXISTS live_tracking_provider text,
  ADD COLUMN IF NOT EXISTS live_tracking_updated_at timestamptz,
  ADD COLUMN IF NOT EXISTS live_tracking_event text,
  ADD COLUMN IF NOT EXISTS carrier_tracking_updated_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_shipments_org_live_tracking
  ON shipments (organization_id, transport_mode, live_tracking_id)
  WHERE live_tracking_id IS NOT NULL;

COMMIT;
