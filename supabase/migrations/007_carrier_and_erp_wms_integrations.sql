BEGIN;

CREATE TABLE IF NOT EXISTS integration_connections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  code text NOT NULL CHECK (code IN ('carrier', 'erp', 'wms')),
  name text NOT NULL,
  base_url text NOT NULL,
  auth_env_key text,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, code)
);

CREATE TABLE IF NOT EXISTS carrier_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  shipment_id uuid REFERENCES shipments(id) ON DELETE SET NULL,
  order_id uuid REFERENCES orders(id) ON DELETE SET NULL,
  carrier_name text NOT NULL,
  service_level text,
  driver_reference text,
  external_assignment_id text,
  status text NOT NULL CHECK (status IN ('pending_approval', 'ready_to_dispatch', 'dispatched', 'failed', 'cancelled')) DEFAULT 'ready_to_dispatch',
  request_payload jsonb NOT NULL DEFAULT '{}',
  response_payload jsonb,
  error text,
  dispatched_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS financial_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  external_id text NOT NULL,
  document_number text,
  record_type text NOT NULL,
  amount numeric,
  currency text NOT NULL DEFAULT 'USD',
  status text,
  source_payload jsonb NOT NULL DEFAULT '{}',
  recorded_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, external_id)
);

CREATE TABLE IF NOT EXISTS integration_sync_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  integration_code text NOT NULL,
  direction text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  resource text NOT NULL,
  status text NOT NULL CHECK (status IN ('success', 'failed')),
  record_count integer NOT NULL DEFAULT 0,
  detail jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_carrier_assignments_org_status ON carrier_assignments(organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_integration_sync_log_org ON integration_sync_log(organization_id, created_at DESC);

ALTER TABLE integration_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE carrier_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration_sync_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY integration_connections_org_isolation ON integration_connections FOR ALL USING (organization_id = current_org_id());
CREATE POLICY carrier_assignments_org_isolation ON carrier_assignments FOR ALL USING (organization_id = current_org_id());
CREATE POLICY financial_records_org_isolation ON financial_records FOR ALL USING (organization_id = current_org_id());
CREATE POLICY integration_sync_log_org_isolation ON integration_sync_log FOR ALL USING (organization_id = current_org_id());

COMMIT;
