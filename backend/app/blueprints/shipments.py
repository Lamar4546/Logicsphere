import logging

from flask import Blueprint, g, jsonify, request
from datetime import datetime, timezone
from ..services.jwt import login_required
from ..services.supabase_client import get_client
from ..agents.central_manager import CentralAILogisticsManager

shipments_bp = Blueprint("shipments", __name__)
central_manager = CentralAILogisticsManager()
log = logging.getLogger(__name__)


@shipments_bp.get("")
@login_required
def list_shipments():
    organization_id = g.current_user["org"]
    db = get_client()
    try:
        result = (
            db.table("shipments")
            .select("*")
            .eq("organization_id", organization_id)
            .order("created_at", desc=True)
            .execute()
        )
        return jsonify(result.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@shipments_bp.post("")
@login_required
def create_shipment():
    payload = request.get_json(force=True)
    required = ["reference_number"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    payload["organization_id"] = g.current_user["org"]
    db = get_client()
    result = db.table("shipments").insert(payload).execute()
    return jsonify(result.data[0] if result.data else {}), 201


@shipments_bp.post("/<shipment_id>/tracking")
@login_required
def update_tracking(shipment_id):
    """Carrier/GPS adapter endpoint for a live marker update."""
    payload = request.get_json(force=True)
    try:
        latitude, longitude = float(payload["latitude"]), float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "latitude and longitude must be numeric."}), 400
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return jsonify({"error": "Coordinates are outside valid bounds."}), 400

    changes = {
        "current_latitude": latitude,
        "current_longitude": longitude,
        "tracking_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.get("last_event_description"):
        changes["last_event_description"] = payload["last_event_description"]
    if payload.get("eta_current"):
        changes["eta_current"] = payload["eta_current"]
    result = get_client().table("shipments").update(changes).eq("id", shipment_id).eq("organization_id", g.current_user["org"]).execute()
    if not result.data:
        return jsonify({"error": "Shipment not found for this organization."}), 404
    return jsonify(result.data[0])


@shipments_bp.post("/<shipment_id>/evaluate")
@login_required
def evaluate_shipment(shipment_id):
    organization_id = g.current_user["org"]
    try:
        result = central_manager.evaluate_shipment(organization_id, shipment_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        # Return a usable error to the command centre while preserving the
        # complete traceback in the backend log for diagnosis.
        log.exception("Shipment evaluation failed for %s", shipment_id)
        return jsonify({"error": f"Shipment evaluation failed: {exc}"}), 500

    return jsonify(result)
