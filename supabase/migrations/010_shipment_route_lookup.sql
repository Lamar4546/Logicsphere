BEGIN;

ALTER TABLE shipments
  ADD COLUMN IF NOT EXISTS origin_latitude numeric,
  ADD COLUMN IF NOT EXISTS origin_longitude numeric,
  ADD COLUMN IF NOT EXISTS destination_latitude numeric,
  ADD COLUMN IF NOT EXISTS destination_longitude numeric,
  ADD COLUMN IF NOT EXISTS route_geometry jsonb,
  ADD COLUMN IF NOT EXISTS route_distance_meters numeric,
  ADD COLUMN IF NOT EXISTS route_duration_seconds numeric,
  ADD COLUMN IF NOT EXISTS route_lookup_status text;

COMMIT;
