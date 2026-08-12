"""
Central AI Logistics Manager — SRS §6.2, §10.2.

"Shall collect signals from specialized agents, prioritize issues, combine
relevant operational context, generate or coordinate recommendations, route
actions to human approval when required, and coordinate approved workflows."

This module implements the Shipment Delay Workflow end to end (steps 1-7 of
SRS §10.2 run automatically; steps 8-11 happen once a human approves —
see workflows blueprint / execute_approved_workflow below).
"""
from ..services.supabase_client import get_client
from .transportation_agent import TransportationAgent
from .risk_agent import RiskAgent
from .communication_agent import CommunicationAgent


class CentralAILogisticsManager:
    name = "central_ai_logistics_manager"

    def __init__(self):
        self.transportation_agent = TransportationAgent()
        self.risk_agent = RiskAgent()
        self.communication_agent = CommunicationAgent()

    def evaluate_shipment(self, organization_id: str, shipment_id: str) -> dict:
        """
        Runs SRS §10.2 steps 2-7 for a single shipment:
          2. Transportation Agent evaluates shipment status.
          3. Risk Agent evaluates delay indicators.
          4. Central AI Logistics Manager prioritizes the issue.
          5. System displays the shipment as at risk (risk_agent writes this).
          6. AI prepares an explanation and recommended next actions.
          7. (Authorized user reviews the recommendation — happens in the UI.)

        Returns a dict the API can hand straight to the frontend; also
        persists a risk alert (if applicable) and a recommendation to
        ai_recommendations for the human-approval step.
        """
        db = get_client()
        shipment = (
            db.table("shipments")
            .select("*")
            .eq("id", shipment_id)
            .eq("organization_id", organization_id)
            .single()
            .execute()
        ).data
        if not shipment:
            raise ValueError("Shipment not found for this organization.")

        transport_output = self.transportation_agent.run(
            organization_id=organization_id,
            entity_type="shipment",
            entity_id=shipment_id,
            shipment=shipment,
        )

        risk_output = self.risk_agent.run(
            organization_id=organization_id,
            entity_type="shipment",
            entity_id=shipment_id,
            shipment=shipment,
            transport_observation=transport_output.to_dict(),
        )

        severity = risk_output.data.get("severity")
        if severity is None:
            return {
                "shipment": shipment,
                "transport_observation": transport_output.to_dict(),
                "risk": risk_output.to_dict(),
                "recommendation": None,
            }

        recommendation = self._build_recommendation(
            organization_id, shipment, transport_output, risk_output
        )

        return {
            "shipment": shipment,
            "transport_observation": transport_output.to_dict(),
            "risk": risk_output.to_dict(),
            "recommendation": recommendation,
        }

    def _build_recommendation(self, organization_id, shipment, transport_output, risk_output):
        """SRS §10.2 step 6 + §14.2 explainability: separate facts from
        predictions from the recommendation itself."""
        delay_hours = transport_output.data.get("delay_hours")
        severity = risk_output.data.get("severity")

        action_by_severity = {
            "low": "Monitor the shipment; no customer notification needed yet.",
            "medium": "Notify the customer proactively and confirm updated ETA with carrier.",
            "high": "Notify the customer immediately, escalate to carrier, and check downstream inventory impact.",
            "critical": "Escalate to ops manager, notify customer with revised commitments, and evaluate reroute/expedite options.",
        }
        recommended_action = action_by_severity.get(severity, "Review shipment manually.")

        summary = (
            f"Shipment {shipment.get('reference_number')} is running "
            f"{delay_hours}h behind its original ETA and has been classified as "
            f"{severity.upper()} risk. {transport_output.data.get('last_event_description') or ''}".strip()
        )

        db = get_client()
        rec = db.table("ai_recommendations").insert(
            {
                "organization_id": organization_id,
                "entity_type": "shipment",
                "entity_id": shipment["id"],
                "risk_alert_id": risk_output.data.get("risk_alert_id"),
                "generated_by": self.name,
                "summary": summary,
                "recommended_action": recommended_action,
                "facts": [
                    f"Original ETA vs current ETA delta: {delay_hours}h",
                    f"Origin: {shipment.get('origin')}, Destination: {shipment.get('destination')}",
                ],
                "predictions": [f"Risk severity: {severity}"],
                "confidence": risk_output.confidence,
                "status": "pending_approval",
            }
        ).execute()

        db.table("audit_events").insert(
            {
                "organization_id": organization_id,
                "actor_type": "agent",
                "actor_id": self.name,
                "event_type": "recommendation_created",
                "entity_type": "shipment",
                "entity_id": shipment["id"],
                "detail": {"recommendation_id": rec.data[0]["id"]},
            }
        ).execute()

        return rec.data[0] if rec.data else None
