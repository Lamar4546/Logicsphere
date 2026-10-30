BEGIN;

CREATE TABLE IF NOT EXISTS fleet_vehicles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  vehicle_reference text NOT NULL,
  driver_name text,
  capacity_kg numeric(12,2) NOT NULL CHECK (capacity_kg > 0),
  compartment_count integer NOT NULL CHECK (compartment_count BETWEEN 1 AND 60),
  dock_label text,
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'loading', 'dispatched', 'maintenance')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, vehicle_reference)
);

CREATE TABLE IF NOT EXISTS fleet_vehicle_loads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  vehicle_id uuid NOT NULL REFERENCES fleet_vehicles(id) ON DELETE CASCADE,
  shipment_id uuid NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
  slot_code text NOT NULL,
  weight_kg numeric(12,2) NOT NULL CHECK (weight_kg > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (vehicle_id, slot_code),
  UNIQUE (shipment_id)
);

CREATE INDEX IF NOT EXISTS idx_fleet_vehicles_org_status ON fleet_vehicles(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_fleet_vehicle_loads_org_vehicle ON fleet_vehicle_loads(organization_id, vehicle_id);
ALTER TABLE fleet_vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE fleet_vehicle_loads ENABLE ROW LEVEL SECURITY;
CREATE POLICY fleet_vehicles_org_isolation ON fleet_vehicles FOR ALL USING (organization_id = current_org_id());
CREATE POLICY fleet_vehicle_loads_org_isolation ON fleet_vehicle_loads FOR ALL USING (organization_id = current_org_id());

COMMIT;
