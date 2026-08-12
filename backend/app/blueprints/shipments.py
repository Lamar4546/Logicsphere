from flask import Blueprint, request, jsonify
from ..services.supabase_client import get_client
from ..agents.central_manager import CentralAILogisticsManager

shipments_bp = Blueprint("shipments", __name__)
central_manager = CentralAILogisticsManager()


@shipments_bp.get("")
def list_shipments():
    organization_id = request.args.get("organization_id")
    if not organization_id:
        return jsonify({"error": "organization_id is required"}), 400
    db = get_client()
    result = (
        db.table("shipments")
        .select("*")
        .eq("organization_id", organization_id)
        .order("created_at", desc=True)
        .execute()
    )
    return jsonify(result.data)


@shipments_bp.post("")
def create_shipment():
    """SRS §10.2 step 1: shipment information enters the platform.
    In production this is populated by a TMS/carrier integration sync;
    this endpoint stands in for that ingestion for the demo."""
    payload = request.get_json(force=True)
    required = ["organization_id", "reference_number"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    db = get_client()
    result = db.table("shipments").insert(payload).execute()
    return jsonify(result.data[0] if result.data else {}), 201


@shipments_bp.post("/<shipment_id>/evaluate")
def evaluate_shipment(shipment_id):
    """Runs the Central AI Logistics Manager on a single shipment —
    SRS §10.2 steps 2-6, producing a risk alert + recommendation if warranted."""
    payload = request.get_json(force=True) or {}
    organization_id = payload.get("organization_id") or request.args.get("organization_id")
    if not organization_id:
        return jsonify({"error": "organization_id is required"}), 400

    try:
        result = central_manager.evaluate_shipment(organization_id, shipment_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)
