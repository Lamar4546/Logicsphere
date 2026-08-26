BEGIN;

-- Bring earlier Operations Console orders into the same Control Tower model.
INSERT INTO shipments (
  organization_id, order_id, reference_number, origin, destination, status, source_system
)
SELECT
  o.organization_id, o.id, o.reference_number, o.origin, o.destination, 'planned', 'order_dispatch_backfill'
FROM orders o
LEFT JOIN shipments s ON s.order_id = o.id
WHERE s.id IS NULL
ON CONFLICT (order_id) WHERE order_id IS NOT NULL DO NOTHING;

-- Connect already-created delivery tasks to their matching shipment.
UPDATE delivery_tasks d
SET shipment_id = s.id
FROM shipments s
WHERE d.order_id = s.order_id
  AND d.organization_id = s.organization_id
  AND d.shipment_id IS NULL;

COMMIT;
