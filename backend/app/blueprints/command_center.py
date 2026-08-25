"""
Command Center — SRS §5.1.

For this thin slice, surfaces the panels needed to demo the shipment delay
workflow: Today, At Risk, AI Recommendations, Pending Approvals.
Full panel set (Tasks, Communications, Performance, Ask LogiSphere) comes
in later slices.
"""
from flask import Blueprint, g, jsonify
from ..services.jwt import login_required
from ..services.supabase_client import get_client

command_center_bp = Blueprint("command_center", __name__)


@command_center_bp.get("/summary")
@login_required
def summary():
    db = get_client()
    organization_id = g.current_user["org"]

    try:
        at_risk_shipments = (
            db.table("shipments")
            .select("*")
            .eq("organization_id", organization_id)
            .eq("status", "at_risk")
            .order("eta_current")
            .execute()
        ).data

        open_alerts = (
            db.table("risk_alerts")
            .select("*")
            .eq("organization_id", organization_id)
            .eq("status", "open")
            .order("detected_at", desc=True)
            .execute()
        ).data

        pending_recommendations = (
            db.table("ai_recommendations")
            .select("*")
            .eq("organization_id", organization_id)
            .eq("status", "pending_approval")
            .order("created_at", desc=True)
            .execute()
        ).data

        pending_communications = (
            db.table("communications")
            .select("*")
            .eq("organization_id", organization_id)
            .eq("status", "draft")
            .order("created_at", desc=True)
            .execute()
        ).data

        # The communication card needs the durable workflow id too. Keeping
        # this server-derived means a page refresh does not break final approval.
        pending_workflows = (
            db.table("workflows")
            .select("id, recommendation_id")
            .eq("organization_id", organization_id)
            .eq("status", "pending")
            .execute()
        ).data
        workflow_by_recommendation = {
            item["recommendation_id"]: item["id"]
            for item in pending_workflows
            if item.get("recommendation_id")
        }
        for communication in pending_communications:
            communication["workflow_id"] = workflow_by_recommendation.get(
                communication.get("recommendation_id")
            )

        return jsonify(
            {
                "today": {
                    "at_risk_count": len(at_risk_shipments),
                    "pending_approvals_count": len(pending_recommendations) + len(pending_communications),
                },
                "at_risk_shipments": at_risk_shipments,
                "open_alerts": open_alerts,
                "ai_recommendations": pending_recommendations,
                "pending_communications": pending_communications,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
