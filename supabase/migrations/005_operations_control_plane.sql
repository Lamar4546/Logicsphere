-- Agent-operated logistics control plane. Run after the existing schema.
BEGIN;

CREATE TABLE IF NOT EXISTS orders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  reference_number text NOT NULL,
  customer_name text,
  origin text,
  destination text,
  status text NOT NULL DEFAULT 'received',
  priority text NOT NULL DEFAULT 'standard',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orders_org_status ON orders(organization_id, status);

CREATE TABLE IF NOT EXISTS delivery_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  order_id uuid REFERENCES orders(id) ON DELETE CASCADE,
  shipment_id uuid REFERENCES shipments(id) ON DELETE SET NULL,
  assigned_driver text,
  route_plan jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'dispatched',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  sku text NOT NULL,
  name text NOT NULL,
  quantity integer NOT NULL DEFAULT 0,
  reorder_point integer NOT NULL DEFAULT 0,
  location text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(organization_id, sku)
);

CREATE TABLE IF NOT EXISTS delivery_proofs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  shipment_id uuid REFERENCES shipments(id) ON DELETE CASCADE,
  recipient_name text,
  signature_url text,
  photo_url text,
  delivered_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS returns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  order_id uuid REFERENCES orders(id) ON DELETE SET NULL,
  reason text,
  status text NOT NULL DEFAULT 'requested',
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE shipments ADD COLUMN IF NOT EXISTS current_latitude numeric;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS current_longitude numeric;
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS tracking_updated_at timestamptz;

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE delivery_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE delivery_proofs ENABLE ROW LEVEL SECURITY;
ALTER TABLE returns ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_org_isolation ON orders FOR ALL USING (organization_id = current_org_id());
CREATE POLICY delivery_tasks_org_isolation ON delivery_tasks FOR ALL USING (organization_id = current_org_id());
CREATE POLICY inventory_items_org_isolation ON inventory_items FOR ALL USING (organization_id = current_org_id());
CREATE POLICY delivery_proofs_org_isolation ON delivery_proofs FOR ALL USING (organization_id = current_org_id());
CREATE POLICY returns_org_isolation ON returns FOR ALL USING (organization_id = current_org_id());
COMMIT;
