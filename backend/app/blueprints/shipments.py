import logging
import hashlib
import secrets

import requests

from flask import Blueprint, g, jsonify, request
from datetime import datetime, timezone
from ..services.jwt import login_required
from ..services.supabase_client import get_client
from ..services.route_lookup import route_between
from ..agents.central_manager import CentralAILogisticsManager

shipments_bp = Blueprint("shipments", __name__)
public_tracking_bp = Blueprint("public_tracking", __name__)
central_manager = CentralAILogisticsManager()
log = logging.getLogger(__name__)


@shipments_bp.post("/<shipment_id>/public-tracking-link")
@login_required
def create_public_tracking_link(shipment_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = get_client().table("shipments").update({"public_tracking_token_hash": token_hash}).eq(
        "id", shipment_id
    ).eq("organization_id", g.current_user["org"]).execute()
    if not result.data:
        return jsonify({"error": "Shipment not found for this organization."}), 404
    return jsonify({"tracking_path": f"/track/{token}", "reference_number": result.data[0].get("reference_number")}), 201


@public_tracking_bp.get("/<token>")
def public_tracking(token):
    if len(token) < 32 or len(token) > 100:
        return jsonify({"error": "This tracking link is invalid or has expired."}), 404
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    try:
        rows = get_client().table("shipments").select(
            "reference_number,status,origin,destination,eta_current,current_latitude,current_longitude,route_geometry,last_event_description,tracking_updated_at"
        ).eq("public_tracking_token_hash", token_hash).limit(1).execute().data
    except Exception:
        log.exception("Public shipment lookup failed")
        return jsonify({"error": "Shipment tracking is temporarily unavailable."}), 503
    if not rows:
        return jsonify({"error": "This tracking link is invalid or has expired."}), 404
    return jsonify(rows[0])


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
            # Cancelled orders are retained for audit, but they must not show
            # up as live, trackable work in the Command Center.
            .neq("status", "cancelled")
            .order("created_at", desc=True)
            .execute()
        )
        # Current cancellations directly set the linked shipment's status to
        # cancelled, which the query above excludes without relying on a
        # PostgREST relationship that might not exist before migration 008.
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
    if payload.get("origin") and payload.get("destination"):
        try:
            route = route_between(payload["origin"], payload["destination"])
            if route:
                payload.update(route)
            else:
                payload["route_lookup_status"] = "not_found"
        except Exception:
            # Location enrichment must never prevent an operator or an
            # integration from creating a shipment.
            log.exception("Route lookup failed for shipment %s", payload.get("reference_number"))
            payload["route_lookup_status"] = "unavailable"
    db = get_client()
    result = db.table("shipments").insert(payload).execute()
    return jsonify(result.data[0] if result.data else {}), 201


@shipments_bp.post("/<shipment_id>/route/refresh")
@login_required
def refresh_route(shipment_id):
    """Resolve a shipment's named route through Nominatim and OSRM."""
    db = get_client()
    rows = db.table("shipments").select("id, origin, destination").eq("id", shipment_id).eq(
        "organization_id", g.current_user["org"]
    ).limit(1).execute().data
    if not rows:
        return jsonify({"error": "Shipment not found for this organization."}), 404
    shipment = rows[0]
    if not shipment.get("origin") or not shipment.get("destination"):
        return jsonify({"error": "Origin and destination are required to plan a route."}), 400
    try:
        route = route_between(shipment["origin"], shipment["destination"])
    except requests.RequestException:
        log.exception("Route refresh failed for %s", shipment_id)
        route = None
    if not route:
        db.table("shipments").update({"route_lookup_status": "unavailable"}).eq("id", shipment_id).execute()
        return jsonify({"error": "Route services could not resolve this journey. Try again later."}), 502
    result = db.table("shipments").update(route).eq("id", shipment_id).eq("organization_id", g.current_user["org"]).execute()
    return jsonify(result.data[0] if result.data else {}), 200


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
    for field in ("current_altitude", "current_heading"):
        if payload.get(field) is None:
            continue
        try:
            value = float(payload[field])
        except (TypeError, ValueError):
            return jsonify({"error": f"{field} must be numeric."}), 400
        if field == "current_altitude" and not -1000 <= value <= 100000:
            return jsonify({"error": "Altitude is outside the supported range in meters."}), 400
        if field == "current_heading" and not 0 <= value < 360:
            return jsonify({"error": "Heading must be between 0 and 360 degrees."}), 400
        changes[field] = value
    if payload.get("transport_mode"):
        mode = str(payload["transport_mode"]).lower()
        if mode not in {"plane", "ship", "truck"}:
            return jsonify({"error": "transport_mode must be plane, ship, or truck."}), 400
        changes["transport_mode"] = mode
    if payload.get("tracking_source"):
        changes["tracking_source"] = str(payload["tracking_source"])[:80]
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
