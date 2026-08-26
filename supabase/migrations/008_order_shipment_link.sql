BEGIN;

-- An order becomes a trackable shipment as soon as the dispatch agent accepts
-- it. This is intentionally nullable for carrier-imported shipments that did
-- not originate as an in-app order.
ALTER TABLE shipments
  ADD COLUMN IF NOT EXISTS order_id uuid REFERENCES orders(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shipments_one_per_order
  ON shipments(order_id) WHERE order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_shipments_org_order
  ON shipments(organization_id, order_id);

COMMIT;
