from flask import Blueprint, g, request, jsonify
from ..services import workflow_service
from ..services.jwt import login_required
from ..services.supabase_client import get_client

workflows_bp = Blueprint("workflows", __name__)


@workflows_bp.post("/<workflow_id>/approve-communication")
@login_required
def approve_communication(workflow_id):
    payload = request.get_json(force=True) or {}
    communication_id = payload.get("communication_id")
    approved_by = g.current_user["sub"]

    if not communication_id:
        return jsonify({"error": "communication_id is required"}), 400

    try:
        result = workflow_service.approve_communication_and_execute(
            g.current_user["org"], workflow_id, communication_id, approved_by
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)


@workflows_bp.get("/<workflow_id>")
@login_required
def get_workflow(workflow_id):
    db = get_client()
    organization_id = g.current_user["org"]
    result = (
        db.table("workflows")
        .select("*")
        .eq("id", workflow_id)
        .eq("organization_id", organization_id)
        .single()
        .execute()
    )
    return jsonify(result.data)
