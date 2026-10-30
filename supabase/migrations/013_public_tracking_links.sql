-- Store only hashes for capability-style customer tracking links. The raw
-- token is returned once to the authenticated operator who requests a link.
ALTER TABLE shipments
  ADD COLUMN IF NOT EXISTS public_tracking_token_hash text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shipments_public_tracking_token_hash
  ON shipments(public_tracking_token_hash)
  WHERE public_tracking_token_hash IS NOT NULL;
