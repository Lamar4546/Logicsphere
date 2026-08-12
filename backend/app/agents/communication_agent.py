"""
Communication Agent — SRS §10.2 step 8, §8.9.

Drafts a customer/supplier communication for a delayed shipment. This is an
ACTION-shaped output but is never auto-sent: it is written to `communications`
with status='draft' and only moves to 'approved' via an explicit human step
(SRS §14.1 Human-in-the-Loop Policy — high-impact actions require approval).
"""
from .base import BaseAgent, AgentOutput
from ..services.supabase_client import get_client


class CommunicationAgent(BaseAgent):
    name = "communication_agent"

    def _execute(
        self,
        organization_id: str,
        shipment: dict,
        recommendation: dict,
        **kwargs,
    ) -> AgentOutput:
        entity_type, entity_id = "shipment", shipment["id"]

        subject = f"Update on shipment {shipment.get('reference_number')}"
        body = (
            f"Hi,\n\n"
            f"We want to flag an update on shipment {shipment.get('reference_number')} "
            f"from {shipment.get('origin')} to {shipment.get('destination')}.\n\n"
            f"{recommendation.get('summary')}\n\n"
            f"Recommended next step: {recommendation.get('recommended_action')}\n\n"
            f"We'll keep you posted as this progresses.\n"
        )

        db = get_client()
        comm = db.table("communications").insert(
            {
                "organization_id": organization_id,
                "related_entity_type": "shipment",
                "related_entity_id": shipment["id"],
                "recommendation_id": recommendation.get("id"),
                "channel": "email",
                "subject": subject,
                "body": body,
                "status": "draft",
            }
        ).execute()

        return AgentOutput(
            kind="action",
            summary=f"Drafted customer update for shipment {shipment.get('reference_number')}.",
            data={"communication_id": comm.data[0]["id"] if comm.data else None},
        )
