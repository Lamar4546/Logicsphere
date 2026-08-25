from flask import Blueprint, g, request, jsonify
from ..services import workflow_service
from ..services.jwt import login_required

recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.post("/<recommendation_id>/approve")
@login_required
def approve(recommendation_id):
    payload = request.get_json(force=True) or {}
    reviewed_by = g.current_user["sub"]

    try:
        result = workflow_service.approve_recommendation(
            g.current_user["org"], recommendation_id, reviewed_by, payload.get("notes")
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)


@recommendations_bp.post("/<recommendation_id>/reject")
@login_required
def reject(recommendation_id):
    payload = request.get_json(force=True) or {}
    reviewed_by = g.current_user["sub"]

    workflow_service.reject_recommendation(
        g.current_user["org"], recommendation_id, reviewed_by, payload.get("notes")
    )
    return jsonify({"status": "rejected"})
