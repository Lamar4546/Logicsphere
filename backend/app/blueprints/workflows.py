from flask import Blueprint, request, jsonify
from ..services import workflow_service
from ..services.supabase_client import get_client

workflows_bp = Blueprint("workflows", __name__)


@workflows_bp.post("/<workflow_id>/approve-communication")
def approve_communication(workflow_id):
    """SRS §10.2 step 9 (user approves communication) -> step 10 (execute) ->
    step 11 (record event and outcome)."""
    payload = request.get_json(force=True) or {}
    organization_id = payload.get("organization_id")
    communication_id = payload.get("communication_id")
    approved_by = payload.get("approved_by")
    if not all([organization_id, communication_id, approved_by]):
        return jsonify({"error": "organization_id, communication_id and approved_by are required"}), 400

    try:
        result = workflow_service.approve_communication_and_execute(
            organization_id, workflow_id, communication_id, approved_by
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)


@workflows_bp.get("/<workflow_id>")
def get_workflow(workflow_id):
    organization_id = request.args.get("organization_id")
    if not organization_id:
        return jsonify({"error": "organization_id is required"}), 400
    db = get_client()
    result = (
        db.table("workflows")
        .select("*")
        .eq("id", workflow_id)
        .eq("organization_id", organization_id)
        .single()
        .execute()
    )
    return jsonify(result.data)
