from typing import Any


class ExecutionEngine:
    """Executes approved actions against external systems or internal services.

    For the thin slice, this will mostly update DB state or simulate external
    API calls. The ExecutionEngine should be the only component that performs
    side effects in response to AI-approved actions.
    """

    def __init__(self, db_client):
        self.db = db_client

    def execute(self, organization_id: str, action: dict[str, Any]) -> dict[str, Any]:
        act = action.get("action")
        if act == "CREATE_PO":
            # Simulate creating a purchase order record
            po = self.db.table("purchase_orders").insert({
                "organization_id": organization_id,
                "amount": action.get("amount"),
                "supplier_id": action.get("supplier_id"),
                "created_at": action.get("created_at"),
            }).execute()
            return {"status": "ok", "po": po.data[0] if po.data else None}

        if act == "BOOK_CARRIER":
            # This is the boundary where the carrier-booking provider is
            # called. It is reached only after human approval.
            return {"status": "ok", "action": act, "mode": "approved_execution"}

        if act in {"MONITOR_SHIPMENT", "REQUEST_ETA_UPDATE", "SEND_CUSTOMER_UPDATE", "ESCALATE_CARRIER"}:
            # These actions are intentionally non-financial. Provider API
            # integrations plug in here; recording the action makes the demo
            # deterministic and preserves an auditable execution boundary.
            return {"status": "ok", "action": act, "mode": "autonomous"}

        return {"status": "error", "error": "unknown_action"}
