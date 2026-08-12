from flask import Blueprint, request, jsonify
from ..services import workflow_service

recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.post("/<recommendation_id>/approve")
def approve(recommendation_id):
    """SRS §10.2 step 7 (user approves) -> triggers step 8 (draft communication)."""
    payload = request.get_json(force=True) or {}
    organization_id = payload.get("organization_id")
    reviewed_by = payload.get("reviewed_by")
    if not organization_id or not reviewed_by:
        return jsonify({"error": "organization_id and reviewed_by are required"}), 400

    try:
        result = workflow_service.approve_recommendation(
            organization_id, recommendation_id, reviewed_by, payload.get("notes")
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)


@recommendations_bp.post("/<recommendation_id>/reject")
def reject(recommendation_id):
    payload = request.get_json(force=True) or {}
    organization_id = payload.get("organization_id")
    reviewed_by = payload.get("reviewed_by")
    if not organization_id or not reviewed_by:
        return jsonify({"error": "organization_id and reviewed_by are required"}), 400

    workflow_service.reject_recommendation(
        organization_id, recommendation_id, reviewed_by, payload.get("notes")
    )
    return jsonify({"status": "rejected"})
