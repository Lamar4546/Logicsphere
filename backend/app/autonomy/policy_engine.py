from typing import Any


class PolicyEngine:
    """Simple policy engine for the thin slice.

    Routine operational actions are autonomous. Human approval is reserved
    for critical situations and any action that creates a financial commitment.

    Returns a dict: {"allowed": bool, "reason": str, "requires_approval": bool}
    """

    COMMITMENT_ACTIONS = frozenset({"CREATE_PO", "BOOK_CARRIER"})
    ROUTINE_ACTIONS = frozenset({"MONITOR_SHIPMENT", "REQUEST_ETA_UPDATE", "SEND_CUSTOMER_UPDATE", "ESCALATE_CARRIER"})

    @classmethod
    def describe_rules(cls) -> dict:
        return {
            "human_approval": [
                "Critical severity actions require human approval.",
                "Purchase orders, carrier bookings, and any action with a financial amount require human approval.",
            ],
            "autonomous_actions": sorted(cls.ROUTINE_ACTIONS),
            "unknown_action": "Blocked and held for review.",
        }

    def evaluate(self, organization_id: str, action: dict[str, Any]) -> dict:
        act = action.get("action")
        severity = action.get("risk_severity")
        amount = action.get("amount")

        if severity == "critical":
            return {"allowed": True, "reason": "critical_risk_requires_approval", "requires_approval": True}

        if act in self.COMMITMENT_ACTIONS or amount is not None:
            return {"allowed": True, "reason": "financial_commitment_requires_approval", "requires_approval": True}

        if act in self.ROUTINE_ACTIONS:
            return {"allowed": True, "reason": "routine_operational_action", "requires_approval": False}

        return {"allowed": False, "reason": "unknown_action", "requires_approval": True}
