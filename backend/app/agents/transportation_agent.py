"""
Transportation Agent — SRS §10.2 step 2.

Deterministic, rule-based evaluation for this slice (no ML model needed yet —
SRS §21 Open Product Decisions defers "exact AI model providers" to later).
Produces an OBSERVATION: is this shipment behind schedule, and by how much.
"""
from datetime import datetime, timezone
from .base import BaseAgent, AgentOutput


class TransportationAgent(BaseAgent):
    name = "transportation_agent"

    def _execute(self, organization_id: str, shipment: dict, **kwargs) -> AgentOutput:
        entity_type, entity_id = "shipment", shipment["id"]

        eta_current = shipment.get("eta_current")
        eta_original = shipment.get("eta_original")
        status = shipment.get("status")

        if not eta_current or not eta_original:
            return AgentOutput(
                kind="observation",
                summary=f"Shipment {shipment.get('reference_number')} has incomplete ETA data.",
                data={"delay_hours": None, "has_complete_eta": False},
            )

        eta_current_dt = _parse(eta_current)
        eta_original_dt = _parse(eta_original)
        delay_hours = round((eta_current_dt - eta_original_dt).total_seconds() / 3600, 1)

        summary = (
            f"Shipment {shipment.get('reference_number')} is currently "
            f"{'on schedule' if delay_hours <= 0 else f'{delay_hours}h behind original ETA'}."
        )

        return AgentOutput(
            kind="observation",
            summary=summary,
            data={
                "delay_hours": delay_hours,
                "status": status,
                "origin": shipment.get("origin"),
                "destination": shipment.get("destination"),
                "last_event_description": shipment.get("last_event_description"),
            },
        )


def _parse(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
