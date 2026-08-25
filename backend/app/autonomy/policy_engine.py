from typing import Any


class PolicyEngine:
    """Simple policy engine for the thin slice.

    Routine operational actions are autonomous. Human approval is reserved
    for critical situations and any action that creates a financial commitment.

    Returns a dict: {"allowed": bool, "reason": str, "requires_approval": bool}
    """

    def evaluate(self, organization_id: str, action: dict[str, Any]) -> dict:
        act = action.get("action")
        severity = action.get("risk_severity")
        amount = action.get("amount")

        if severity == "critical":
            return {"allowed": True, "reason": "critical_risk_requires_approval", "requires_approval": True}

        if act in {"CREATE_PO", "BOOK_CARRIER"} or amount is not None:
            return {"allowed": True, "reason": "financial_commitment_requires_approval", "requires_approval": True}

        if act in {"MONITOR_SHIPMENT", "REQUEST_ETA_UPDATE", "SEND_CUSTOMER_UPDATE", "ESCALATE_CARRIER"}:
            return {"allowed": True, "reason": "routine_operational_action", "requires_approval": False}

        return {"allowed": False, "reason": "unknown_action", "requires_approval": True}
