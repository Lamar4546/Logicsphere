"""
Central AI Logistics Manager — SRS §6.2, §10.2.

"Shall collect signals from specialized agents, prioritize issues, combine
relevant operational context, generate or coordinate recommendations, route
actions to human approval when required, and coordinate approved workflows."

This module autonomously completes routine shipment-delay work. A human is
only asked to approve a critical risk or a monetary commitment.
"""
from datetime import datetime, timezone
import logging

from ..services.supabase_client import get_client
from .transportation_agent import TransportationAgent
from .risk_agent import RiskAgent
from .communication_agent import CommunicationAgent
from ..autonomy.policy_engine import PolicyEngine
from ..autonomy.execution_engine import ExecutionEngine
from ..services.notification_service import deliver

log = logging.getLogger(__name__)


class CentralAILogisticsManager:
    name = "central_ai_logistics_manager"

    def __init__(self):
        self.transportation_agent = TransportationAgent()
        self.risk_agent = RiskAgent()
        self.communication_agent = CommunicationAgent()
        self.policy = PolicyEngine()
        # execution engine will be instantiated per request with the DB client

    def evaluate_shipment(self, organization_id: str, shipment_id: str) -> dict:
        """
        Runs SRS §10.2 steps 2-7 for a single shipment:
          2. Transportation Agent evaluates shipment status.
          3. Risk Agent evaluates delay indicators.
          4. Central AI Logistics Manager prioritizes the issue.
          5. System displays the shipment as at risk (risk_agent writes this).
          6. AI prepares an explanation and recommended next actions.
          7. Routine actions complete autonomously; exceptional actions wait
             for a human approval.

        Returns a dict the API can hand straight to the frontend; also
        persists a risk alert and an auditable workflow outcome.
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

        action = self._action_for_severity(severity, shipment_id)
        policy_result = self.policy.evaluate(organization_id, action)
        action_result = None
        if policy_result["requires_approval"]:
            self._write_audit_safely(db, {
                    "organization_id": organization_id,
                    "actor_type": "agent",
                    "actor_id": self.name,
                    "event_type": "human_approval_required",
                    "entity_type": "shipment",
                    "entity_id": shipment_id,
                    "detail": {"action": action, "policy": policy_result},
            })
            # This is an audit/status entry only: no customer message is sent
            # until a dispatcher has approved the critical or monetary action.
            try:
                db.table("notification_log").insert(
                    {
                        "organization_id": organization_id,
                        "shipment_id": shipment_id,
                        "channel": shipment.get("preferred_contact_channel", "email"),
                        "recipient": shipment.get("customer_contact"),
                        "content": "Customer update is pending dispatcher approval.",
                        "status": "pending_approval",
                        "triggered_by": "system",
                    }
                ).execute()
            except Exception:
                # Deployments which have not yet applied the notification
                # migration must still be able to evaluate critical cases.
                pass
        else:
            action_result = self._complete_autonomous_workflow(
                organization_id, shipment, recommendation, action
            )

        return {
            "shipment": shipment,
            "transport_observation": transport_output.to_dict(),
            "risk": risk_output.to_dict(),
            "recommendation": recommendation,
            "autonomous_action_result": action_result,
            "policy": policy_result,
        }

    def _action_for_severity(self, severity, shipment_id):
        actions = {
            "low": "MONITOR_SHIPMENT",
            "medium": "SEND_CUSTOMER_UPDATE",
            "high": "ESCALATE_CARRIER",
            # Rerouting / expediting can create a carrier charge.
            "critical": "BOOK_CARRIER",
        }
        return {"action": actions[severity], "shipment_id": shipment_id, "risk_severity": severity}

    def _complete_autonomous_workflow(self, organization_id, shipment, recommendation, action):
        """Execute and persist a routine, non-financial logistics workflow."""
        db = get_client()
        now = datetime.now(timezone.utc).isoformat()
        execution = ExecutionEngine(db).execute(organization_id, action)
        steps = [{"step": "autonomous_action_executed", "detail": execution, "at": now}]

        communication_id = None
        if action["action"] in {"SEND_CUSTOMER_UPDATE", "ESCALATE_CARRIER"}:
            communication = self.communication_agent.run(
                organization_id=organization_id, entity_type="shipment", entity_id=shipment["id"],
                shipment=shipment, recommendation=recommendation,
            )
            communication_id = communication.data.get("communication_id")
            if communication_id:
                try:
                    communication_row = db.table("communications").select("subject, body").eq("id", communication_id).eq("organization_id", organization_id).single().execute().data
                    delivery = deliver(
                        organization_id, shipment["id"], shipment.get("preferred_contact_channel", "email"),
                        shipment.get("customer_contact"), communication_row.get("body", ""), subject=communication_row.get("subject"),
                        communication_id=communication_id, triggered_by="system",
                    )
                except Exception as exc:
                    delivery = {"success": False, "error": f"Notification delivery could not start: {exc}"}
                if delivery["success"]:
                    db.table("communications").update({"status": "sent"}).eq("id", communication_id).eq("organization_id", organization_id).execute()
                steps.append({"step": "notification_delivery", "communication_id": communication_id, "status": "sent" if delivery["success"] else "failed", "at": now})

        db.table("ai_recommendations").update({"status": "approved"}).eq("id", recommendation["id"]).eq("organization_id", organization_id).execute()
        workflow = db.table("workflows").insert({
            "organization_id": organization_id, "workflow_type": "shipment_delay", "entity_type": "shipment",
            "entity_id": shipment["id"], "recommendation_id": recommendation["id"], "status": "completed",
            "steps_log": steps, "started_at": now, "completed_at": now,
        }).execute()
        self._write_audit_safely(db, {
            "organization_id": organization_id, "actor_type": "agent", "actor_id": self.name,
            "event_type": "autonomous_workflow_completed", "entity_type": "shipment", "entity_id": shipment["id"],
            "detail": {"action": action, "communication_id": communication_id},
        })
        return {"status": "completed", "workflow_id": workflow.data[0]["id"] if workflow.data else None, "communication_id": communication_id}

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

        self._write_audit_safely(db, {
                "organization_id": organization_id,
                "actor_type": "agent",
                "actor_id": self.name,
                "event_type": "recommendation_created",
                "entity_type": "shipment",
                "entity_id": shipment["id"],
                "detail": {"recommendation_id": rec.data[0]["id"]},
        })

        return rec.data[0] if rec.data else None

    @staticmethod
    def _write_audit_safely(db, event):
        """Audit is important, but a schema/RLS mismatch must not turn a
        safe decision into a 500 for the dispatcher."""
        try:
            db.table("audit_events").insert(event).execute()
        except Exception:
            log.exception("Unable to write audit event %s", event.get("event_type"))
