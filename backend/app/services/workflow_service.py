"""
Executes the exceptional-path workflow once a human has reviewed a
critical or monetary recommendation:
  8. Communication Agent prepares supplier/customer communication if required.
  9. User approves or edits the communication/action.
  10. Approved workflow executes.
  11. System records the event and outcome.

Routine workflows are completed by the Central AI Logistics Manager. This
module is deliberately limited to the human-gated exceptions.
"""
from datetime import datetime, timezone
from .supabase_client import get_client
from ..agents.communication_agent import CommunicationAgent
from ..autonomy.execution_engine import ExecutionEngine
from .notification_service import deliver


def approve_recommendation(organization_id: str, recommendation_id: str, reviewed_by: str, notes: str | None = None):
    """Approve an exception and complete its remaining work automatically."""
    db = get_client()

    rec = (
        db.table("ai_recommendations")
        .select("*")
        .eq("id", recommendation_id)
        .eq("organization_id", organization_id)
        .single()
        .execute()
    ).data
    if not rec:
        raise ValueError("Recommendation not found for this organization.")

    db.table("ai_recommendations").update(
        {
            "status": "approved",
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "review_notes": notes,
        }
    ).eq("id", recommendation_id).execute()

    shipment = (
        db.table("shipments")
        .select("*")
        .eq("id", rec["entity_id"])
        .single()
        .execute()
    ).data

    comm_agent = CommunicationAgent()
    comm_output = comm_agent.run(
        organization_id=organization_id,
        entity_type="shipment",
        entity_id=shipment["id"],
        shipment=shipment,
        recommendation=rec,
    )

    now = datetime.now(timezone.utc).isoformat()
    is_critical = any("critical" in str(item).lower() for item in (rec.get("predictions") or []))
    action_result = None
    if is_critical:
        # The approval authorizes the commercial expedite decision. The
        # execution itself stays inside the controlled execution boundary.
        action_result = ExecutionEngine(db).execute(
            organization_id,
            {"action": "BOOK_CARRIER", "shipment_id": shipment["id"], "risk_severity": "critical"},
        )

    communication_id = comm_output.data.get("communication_id")
    delivery = None
    if communication_id:
        communication = db.table("communications").select("subject, body").eq("id", communication_id).eq("organization_id", organization_id).single().execute().data
        delivery = deliver(
            organization_id, shipment["id"], shipment.get("preferred_contact_channel", "email"),
            shipment.get("customer_contact"), communication.get("body", ""), subject=communication.get("subject"),
            communication_id=communication_id, triggered_by="user",
        )
        if delivery["success"]:
            db.table("communications").update(
                {"status": "sent", "approved_by": reviewed_by, "approved_at": now}
            ).eq("id", communication_id).eq("organization_id", organization_id).execute()

    workflow = db.table("workflows").insert(
        {
            "organization_id": organization_id,
            "workflow_type": "shipment_delay",
            "entity_type": "shipment",
            "entity_id": shipment["id"],
            "recommendation_id": recommendation_id,
            "status": "completed",
            "steps_log": [
                {"step": "exception_approved", "by": reviewed_by, "at": now},
                {"step": "approved_action_executed", "detail": action_result, "at": now},
                {"step": "notification_delivery", "detail": delivery, "at": now},
            ],
            "started_at": now,
            "completed_at": now,
        }
    ).execute()

    db.table("audit_events").insert(
        {
            "organization_id": organization_id,
            "actor_type": "user",
            "actor_id": reviewed_by,
            "event_type": "recommendation_approved",
            "entity_type": "shipment",
            "entity_id": shipment["id"],
            "detail": {"recommendation_id": recommendation_id},
        }
    ).execute()

    return {
        "recommendation_id": recommendation_id,
        "workflow_id": workflow.data[0]["id"] if workflow.data else None,
        "communication": comm_output.to_dict(),
        "notification": delivery,
        "status": "completed",
    }


def reject_recommendation(organization_id: str, recommendation_id: str, reviewed_by: str, notes: str | None = None):
    db = get_client()
    db.table("ai_recommendations").update(
        {
            "status": "rejected",
            "reviewed_by": reviewed_by,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "review_notes": notes,
        }
    ).eq("id", recommendation_id).eq("organization_id", organization_id).execute()

    db.table("audit_events").insert(
        {
            "organization_id": organization_id,
            "actor_type": "user",
            "actor_id": reviewed_by,
            "event_type": "recommendation_rejected",
            "detail": {"recommendation_id": recommendation_id, "notes": notes},
        }
    ).execute()


def approve_communication_and_execute(organization_id: str, workflow_id: str, communication_id: str, approved_by: str):
    """Step 9 (user approves communication) -> step 10 (workflow executes)
    -> step 11 (record event and outcome)."""
    db = get_client()

    workflow = (
        db.table("workflows")
        .select("*")
        .eq("id", workflow_id)
        .eq("organization_id", organization_id)
        .single()
        .execute()
    ).data
    if not workflow:
        raise ValueError("Workflow not found for this organization.")

    communication = (
        db.table("communications")
        .select("id, recommendation_id, status")
        .eq("id", communication_id)
        .eq("organization_id", organization_id)
        .single()
        .execute()
    ).data
    if not communication:
        raise ValueError("Communication not found for this organization.")
    if communication.get("recommendation_id") != workflow.get("recommendation_id"):
        raise ValueError("Communication does not belong to this workflow.")
    if workflow.get("status") != "pending" or communication.get("status") != "draft":
        raise ValueError("Workflow or communication has already been processed.")

    db.table("communications").update(
        {
            "status": "approved",
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", communication_id).eq("organization_id", organization_id).execute()

    steps_log = workflow.get("steps_log") or []
    steps_log.append(
        {
            "step": "communication_approved_and_sent",
            "by": approved_by,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )

    db.table("workflows").update(
        {
            "status": "completed",
            "started_at": workflow.get("started_at") or datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "steps_log": steps_log,
        }
    ).eq("id", workflow_id).execute()

    # In this thin slice, "sending" is simulated (status set to 'sent').
    # A real send integration (email/SMS provider) plugs in here.
    db.table("communications").update({"status": "sent"}).eq("id", communication_id).execute()

    db.table("audit_events").insert(
        {
            "organization_id": organization_id,
            "actor_type": "user",
            "actor_id": approved_by,
            "event_type": "workflow_executed",
            "entity_type": workflow["entity_type"],
            "entity_id": workflow["entity_id"],
            "detail": {"workflow_id": workflow_id, "communication_id": communication_id},
        }
    ).execute()

    return {"workflow_id": workflow_id, "status": "completed"}
