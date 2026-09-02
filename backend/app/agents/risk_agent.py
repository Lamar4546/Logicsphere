"""
Risk Agent — SRS §10.2 step 3, §8.11.

Takes the Transportation Agent's observation and turns it into a PREDICTION /
risk classification. Writes a risk_alerts row when threshold is crossed —
this is the "system displays the shipment as at risk" step (§10.2 step 5).
"""
from .base import BaseAgent, AgentOutput
from ..services.supabase_client import get_client
from ..services.minimax_client import MiniMaxError, chat_json, is_configured, provider_name

# Thresholds are a starting configuration, not a hardcoded business rule —
# SRS §5.3 calls for these to be "configurable according to customer policies"
# in the full product. Fine as constants for this thin slice.
DELAY_THRESHOLDS_HOURS = {
    "low": 2,
    "medium": 6,
    "high": 24,
    "critical": 72,
}


class RiskAgent(BaseAgent):
    name = "risk_agent"

    def _execute(
        self, organization_id: str, shipment: dict, transport_observation: dict, **kwargs
    ) -> AgentOutput:
        entity_type, entity_id = "shipment", shipment["id"]
        delay_hours = transport_observation.get("data", {}).get("delay_hours")

        severity = self._classify(delay_hours)

        if severity is None:
            return AgentOutput(
                kind="prediction",
                summary=f"Shipment {shipment.get('reference_number')} shows no material delay risk.",
                data={"severity": None, "delay_hours": delay_hours},
            )

        ai_reasoning = self._reason_about_delay(shipment, delay_hours, severity)
        db = get_client()
        alert = db.table("risk_alerts").insert(
            {
                "organization_id": organization_id,
                "entity_type": "shipment",
                "entity_id": shipment["id"],
                "risk_type": "delay",
                "severity": severity,
                "status": "open",
                "description": (
                    f"Shipment {shipment.get('reference_number')} is delayed "
                    f"{delay_hours}h against original ETA "
                    f"({shipment.get('origin')} → {shipment.get('destination')})."
                ),
                "detected_by": self.name,
            }
        ).execute()

        db.table("shipments").update({"status": "at_risk"}).eq(
            "id", shipment["id"]
        ).execute()

        return AgentOutput(
            kind="prediction",
            summary=(
                f"Shipment {shipment.get('reference_number')} classified as "
                f"{severity.upper()} delay risk."
            ),
            data={
                "severity": severity,
                "delay_hours": delay_hours,
                "risk_alert_id": alert.data[0]["id"] if alert.data else None,
                "ai_reasoning": ai_reasoning,
                "ai_provider": provider_name() if ai_reasoning else "deterministic_fallback",
            },
            confidence=self._confidence_for(severity),
        )

    def _classify(self, delay_hours):
        if delay_hours is None or delay_hours <= 0:
            return None
        if delay_hours >= DELAY_THRESHOLDS_HOURS["critical"]:
            return "critical"
        if delay_hours >= DELAY_THRESHOLDS_HOURS["high"]:
            return "high"
        if delay_hours >= DELAY_THRESHOLDS_HOURS["medium"]:
            return "medium"
        if delay_hours >= DELAY_THRESHOLDS_HOURS["low"]:
            return "low"
        return None

    def _confidence_for(self, severity):
        # Simple heuristic for the thin slice — larger, clearer delays get
        # higher confidence. Replace with a calibrated model later.
        return {"low": 0.6, "medium": 0.75, "high": 0.85, "critical": 0.95}[severity]

    def _reason_about_delay(self, shipment, delay_hours, severity):
        """Ask MiniMax for operational context, never for the safety decision.

        Deterministic thresholds remain the authority for risk severity so a
        model response cannot reduce a safety gate or create a financial action.
        """
        if not is_configured():
            return None
        try:
            result = chat_json(
                [
                    {
                        "role": "system",
                        "content": "You are a logistics risk analyst. Return concise JSON with keys operational_reasoning and customer_impact. Do not recommend purchases, bookings, or financial commitments.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Shipment {shipment.get('reference_number')} is {delay_hours} hours late, "
                            f"from {shipment.get('origin')} to {shipment.get('destination')}. "
                            f"Deterministic severity is {severity}. Last event: {shipment.get('last_event_description') or 'not available'}."
                        ),
                    },
                ]
            )
            return {
                "operational_reasoning": str(result.get("operational_reasoning", ""))[:1000],
                "customer_impact": str(result.get("customer_impact", ""))[:600],
            }
        except MiniMaxError:
            # The workflow remains available with deterministic reasoning if
            # the model is unavailable or returns invalid JSON.
            return None
