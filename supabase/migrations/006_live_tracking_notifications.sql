BEGIN;

ALTER TABLE shipments ADD COLUMN IF NOT EXISTS customer_contact text;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS preferred_contact_channel text NOT NULL DEFAULT 'email';

CREATE TABLE IF NOT EXISTS notification_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  shipment_id uuid NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
  communication_id uuid REFERENCES communications(id) ON DELETE SET NULL,
  channel text NOT NULL CHECK (channel IN ('sms', 'whatsapp', 'email')),
  recipient text,
  content text NOT NULL,
  status text NOT NULL CHECK (status IN ('sent', 'failed', 'pending_approval')),
  provider_message_id text,
  error text,
  triggered_by text NOT NULL CHECK (triggered_by IN ('system', 'user')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notification_log_shipment ON notification_log(shipment_id, created_at DESC);
ALTER TABLE notification_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY notification_log_org_isolation ON notification_log FOR ALL USING (organization_id = current_org_id());
COMMIT;
