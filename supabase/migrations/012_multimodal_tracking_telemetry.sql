-- Additional optional fields accepted by the authenticated carrier/GPS
-- tracking endpoint. Existing integrations can continue sending lat/lon only.
ALTER TABLE shipments
  ADD COLUMN IF NOT EXISTS current_altitude numeric,
  ADD COLUMN IF NOT EXISTS current_heading numeric,
  ADD COLUMN IF NOT EXISTS transport_mode text,
  ADD COLUMN IF NOT EXISTS tracking_source text;

ALTER TABLE shipments
  ADD CONSTRAINT shipments_transport_mode_check
  CHECK (transport_mode IS NULL OR transport_mode IN ('plane', 'ship', 'truck'));
