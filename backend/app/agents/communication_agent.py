"""
Communication Agent — SRS §10.2 step 8, §8.9.

Prepares a customer/supplier communication for a delayed shipment. The
Central Manager sends routine operational updates automatically; critical or
monetary workflows are sent only after their required human approval.
"""
from .base import BaseAgent, AgentOutput
from ..services.supabase_client import get_client
from ..services.minimax_client import MiniMaxError, chat, is_configured, provider_name


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
        body = self._default_body(shipment, recommendation)
        generated_by = "deterministic_fallback"

        if is_configured():
            try:
                body = chat(
                    [
                        {
                            "role": "system",
                            "content": "Draft a concise, professional shipment-delay update. State only supplied facts. Do not promise compensation, discounts, refunds, revised commitments, or financial terms.",
                        },
                        {
                            "role": "user",
                            "content": f"Reference: {shipment.get('reference_number')}; route: {shipment.get('origin')} to {shipment.get('destination')}; analysis: {recommendation.get('summary')}; operational next step: {recommendation.get('recommended_action')}",
                        },
                    ],
                    temperature=0.2,
                )
                generated_by = provider_name()
            except MiniMaxError:
                pass

        db = get_client()
        comm = db.table("communications").insert(
            {
                "organization_id": organization_id,
                "related_entity_type": "shipment",
                "related_entity_id": shipment["id"],
                "recommendation_id": recommendation.get("id"),
                "channel": "email",
                "recipient": shipment.get("customer_contact"),
                "subject": subject,
                "body": body,
                "status": "draft",
            }
        ).execute()

        return AgentOutput(
            kind="action",
            summary=f"Prepared customer update for shipment {shipment.get('reference_number')}.",
            data={"communication_id": comm.data[0]["id"] if comm.data else None, "generated_by": generated_by},
        )

    def _default_body(self, shipment, recommendation):
        return (
            f"Hi,\n\n"
            f"We want to flag an update on shipment {shipment.get('reference_number')} "
            f"from {shipment.get('origin')} to {shipment.get('destination')}.\n\n"
            f"{recommendation.get('summary')}\n\n"
            f"Recommended next step: {recommendation.get('recommended_action')}\n\n"
            f"We'll keep you posted as this progresses.\n"
        )
