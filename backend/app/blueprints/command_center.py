"""
Command Center — SRS §5.1.

For this thin slice, surfaces the panels needed to demo the shipment delay
workflow: Today, At Risk, AI Recommendations, Pending Approvals.
Full panel set (Tasks, Communications, Performance, Ask LogiSphere) comes
in later slices.
"""
from flask import Blueprint, request, jsonify
from ..services.supabase_client import get_client

command_center_bp = Blueprint("command_center", __name__)


@command_center_bp.get("/summary")
def summary():
    organization_id = request.args.get("organization_id")
    if not organization_id:
        return jsonify({"error": "organization_id is required"}), 400

    db = get_client()

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
