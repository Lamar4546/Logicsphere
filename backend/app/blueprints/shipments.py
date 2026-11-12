import logging
import hashlib
import re
import secrets

import requests

from flask import Blueprint, g, jsonify, request
from datetime import datetime, timezone
from ..services.jwt import login_required
from ..services.supabase_client import get_client
from ..services.route_lookup import route_between
from ..services.package_tracking import PackageTrackingError, fetch_tracking, normalize_tracking, register_tracking, tracking_provider, verify_17track_webhook, verify_webhook_signature
from ..agents.central_manager import CentralAILogisticsManager

shipments_bp = Blueprint("shipments", __name__)
public_tracking_bp = Blueprint("public_tracking", __name__)
package_tracking_webhook_bp = Blueprint("package_tracking_webhook", __name__)
central_manager = CentralAILogisticsManager()
log = logging.getLogger(__name__)


def _live_tracking_fields(payload):
    mode = str(payload.get("transport_mode") or "").strip().lower()
    provider = {"truck": "traccar", "ship": "aisstream", "plane": "opensky"}.get(mode)
    live_id = payload.get("live_tracking_id")
    if mode and mode not in {"truck", "ship", "plane"}:
        raise ValueError("transport_mode must be truck, ship, or plane.")
    if live_id is None or str(live_id).strip() == "":
        return {"transport_mode": mode or None, "live_tracking_provider": provider, "live_tracking_id": None}
    live_id = str(live_id).strip()
    if len(live_id) > 128:
        raise ValueError("live_tracking_id must be 128 characters or fewer.")
    if not mode:
        raise ValueError("Choose land, sea, or air before adding a live tracking identifier.")
    if mode == "ship" and not re.fullmatch(r"\d{9}", live_id):
        raise ValueError("Sea tracking requires a 9-digit vessel MMSI.")
    if mode == "plane" and not re.fullmatch(r"[0-9a-fA-F]{6}", live_id):
        raise ValueError("Air tracking requires a 6-character ICAO24 address in hexadecimal.")
    return {"transport_mode": mode, "live_tracking_provider": provider, "live_tracking_id": live_id}


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
            "reference_number,status,mode,transport_mode,eta_current,current_latitude,current_longitude,destination_latitude,destination_longitude,route_geometry,last_event_description,tracking_updated_at,carrier_tracking_updated_at,live_tracking_provider,live_tracking_updated_at,live_tracking_event,tracking_carrier,tracking_status,tracking_location,tracking_events,ai_eta_at,ai_eta_date,carrier_eta_at,carrier_eta_date,ai_eta_source,tracking_source"
        ).eq("public_tracking_token_hash", token_hash).limit(1).execute().data
    except Exception:
        log.exception("Public shipment lookup failed")
        return jsonify({"error": "Shipment tracking is temporarily unavailable."}), 503
    if not rows:
        return jsonify({"error": "This tracking link is invalid or has expired."}), 404
    shipment = rows[0]
    # Carrier payloads can contain recipient phone numbers and full addresses.
    # Public links only expose event details needed to follow shipment progress.
    public_events = []
    for event in (shipment.get("tracking_events") or [])[:30]:
        if not isinstance(event, dict):
            continue
        address = event.get("address") or {}
        location = event.get("location") or ", ".join(
            str(address.get(key)) for key in ("city", "state", "country") if address.get(key)
        )
        translation = event.get("description_translation") or {}
        public_events.append({
            "time": event.get("checkpoint_time") or event.get("time_utc") or event.get("time_iso") or event.get("created_at"),
            "description": event.get("message") or (translation.get("description") if isinstance(translation, dict) else None) or event.get("description"),
            "location": location,
            "status": event.get("tag") or event.get("stage") or event.get("sub_status"),
        })
    shipment["tracking_events"] = public_events
    return jsonify(shipment)


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

    try:
        live_fields = _live_tracking_fields(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if live_fields["transport_mode"]:
        payload.update(live_fields)
        payload.setdefault("mode", {"truck": "road", "ship": "ocean", "plane": "air"}[live_fields["transport_mode"]])

    payload["organization_id"] = g.current_user["org"]
    transport_mode = str(payload.get("transport_mode") or payload.get("mode") or "").lower()
    # OSRM's route endpoint is for road vehicles; never draw a driving route
    # over an ocean or an airline's path.
    non_road_mode = transport_mode in {"plane", "air", "ship", "ocean", "sea"}
    if payload.get("origin") and payload.get("destination") and not non_road_mode:
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


@shipments_bp.post("/package-tracking")
@login_required
def create_package_tracking():
    """Register a parcel tracking number and create its LogiSphere shipment."""
    payload = request.get_json(force=True) or {}
    number = str(payload.get("tracking_number") or "").strip()
    if not number or len(number) > 128:
        return jsonify({"error": "tracking_number is required and must be 128 characters or fewer."}), 400
    carrier_slug = payload.get("carrier_slug")
    if carrier_slug is not None and (not isinstance(carrier_slug, str) or len(carrier_slug) > 100):
        return jsonify({"error": "carrier_slug must be a text courier slug of 100 characters or fewer."}), 400
    for field in ("origin", "destination", "reference_number"):
        if payload.get(field) is not None and not isinstance(payload[field], str):
            return jsonify({"error": f"{field} must be text."}), 400
    try:
        live_fields = _live_tracking_fields(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        existing = get_client().table("shipments").select("*").eq(
            "organization_id", g.current_user["org"]
        ).eq("tracking_number", number).limit(1).execute().data
        if existing:
            if live_fields["live_tracking_id"]:
                update = {**live_fields, "mode": {"truck": "road", "ship": "ocean", "plane": "air"}[live_fields["transport_mode"]]}
                if live_fields["transport_mode"] in {"ship", "plane"}:
                    update.update({"route_geometry": None, "route_distance_meters": None, "route_duration_seconds": None, "route_lookup_status": "not_applicable"})
                changed = get_client().table("shipments").update(update).eq("id", existing[0]["id"]).eq(
                    "organization_id", g.current_user["org"]
                ).execute().data
                return jsonify(changed[0] if changed else existing[0]), 200
            return jsonify(existing[0]), 200
        provider = tracking_provider()
        provider_record = register_tracking(number, carrier_slug)
        # A first lookup often contains richer status and ETA data. Tracking
        # registration still succeeds when the carrier has not scanned it yet.
        try:
            provider_record = fetch_tracking(provider_record["id"], provider)
        except PackageTrackingError:
            log.info("Initial parcel lookup is not ready for tracking %s", number)
        changes = normalize_tracking(
            provider_record,
            fallback_origin=payload.get("origin"),
            fallback_destination=payload.get("destination"),
        )
        now = datetime.now(timezone.utc).isoformat()
        eta = changes.get("eta_current") or payload.get("eta_current")
        shipment = {
            "organization_id": g.current_user["org"],
            "reference_number": str(payload.get("reference_number") or number)[:120],
            "origin": changes.get("origin"),
            "destination": changes.get("destination"),
            "carrier_name": changes.get("tracking_carrier"),
            "mode": {"truck": "road", "ship": "ocean", "plane": "air"}.get(live_fields["transport_mode"]),
            "status": changes.get("status", "planned"),
            "eta_original": eta,
            "eta_current": eta,
            "source_system": provider,
            "tracking_updated_at": now,
            "carrier_tracking_updated_at": now,
            **live_fields,
            **changes,
        }
        result = get_client().table("shipments").insert(shipment).execute()
        if not result.data:
            return jsonify({"error": "The package was registered, but LogiSphere could not save the shipment."}), 502
        return jsonify(result.data[0]), 201
    except PackageTrackingError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    except Exception as exc:
        log.exception("Package tracking registration failed for %s", number)
        return jsonify({"error": f"Could not add package tracking: {exc}"}), 500


@shipments_bp.patch("/<shipment_id>/live-tracking")
@login_required
def configure_live_tracking(shipment_id):
    payload = request.get_json(force=True) or {}
    try:
        fields = _live_tracking_fields(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    mode = fields["transport_mode"]
    changes = {
        **fields,
        "mode": {"truck": "road", "ship": "ocean", "plane": "air"}.get(mode),
    }
    if mode in {"ship", "plane"}:
        changes.update({
            "route_geometry": None,
            "route_distance_meters": None,
            "route_duration_seconds": None,
            "route_lookup_status": "not_applicable",
        })
    result = get_client().table("shipments").update(changes).eq("id", shipment_id).eq(
        "organization_id", g.current_user["org"]
    ).execute()
    if not result.data:
        return jsonify({"error": "Shipment not found for this organization."}), 404
    return jsonify(result.data[0]), 200


@shipments_bp.post("/<shipment_id>/package-tracking/refresh")
@login_required
def refresh_package_tracking(shipment_id):
    db = get_client()
    rows = db.table("shipments").select("*").eq("id", shipment_id).eq(
        "organization_id", g.current_user["org"]
    ).limit(1).execute().data
    if not rows:
        return jsonify({"error": "Shipment not found for this organization."}), 404
    shipment = rows[0]
    provider = shipment.get("tracking_provider")
    if provider not in {"aftership", "17track"} or not shipment.get("provider_tracking_id"):
        return jsonify({"error": "This shipment does not have an external package tracking number."}), 409
    try:
        provider_record = fetch_tracking(shipment["provider_tracking_id"], provider)
        changes = normalize_tracking(
            provider_record,
            fallback_origin=shipment.get("origin"),
            fallback_destination=shipment.get("destination"),
        )
        changes["carrier_name"] = changes.get("tracking_carrier") or shipment.get("carrier_name")
        if not shipment.get("eta_original") and changes.get("eta_current"):
            changes["eta_original"] = changes["eta_current"]
        changes["tracking_updated_at"] = datetime.now(timezone.utc).isoformat()
        changes["carrier_tracking_updated_at"] = changes["tracking_updated_at"]
        result = db.table("shipments").update(changes).eq("id", shipment_id).eq(
            "organization_id", g.current_user["org"]
        ).execute()
        return jsonify(result.data[0] if result.data else {}), 200
    except PackageTrackingError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    except Exception as exc:
        log.exception("Package tracking refresh failed for shipment %s", shipment_id)
        return jsonify({"error": f"Could not refresh package tracking: {exc}"}), 500


@package_tracking_webhook_bp.post("/aftership")
def aftership_tracking_webhook():
    raw_body = request.get_data(cache=True)
    signature = request.headers.get("aftership-hmac-sha256", "")
    if not verify_webhook_signature(raw_body, signature):
        return jsonify({"error": "Invalid AfterShip webhook signature."}), 401
    try:
        body = request.get_json(force=True) or {}
        tracking = body.get("msg") or {}
        provider_id = tracking.get("id")
        if not provider_id:
            return jsonify({"error": "Webhook is missing the tracking ID."}), 400
        db = get_client()
        rows = db.table("shipments").select("id,organization_id,origin,destination").eq(
            "provider_tracking_id", provider_id
        ).limit(1).execute().data
        if not rows:
            # This can happen for a provider verification ping or a tracking
            # registered outside LogiSphere; acknowledge so it is not retried.
            return jsonify({"received": True, "matched": False}), 200
        shipment = rows[0]
        changes = normalize_tracking(
            tracking,
            fallback_origin=shipment.get("origin"),
            fallback_destination=shipment.get("destination"),
        )
        changes["carrier_name"] = changes.get("tracking_carrier")
        changes["tracking_updated_at"] = datetime.now(timezone.utc).isoformat()
        changes["carrier_tracking_updated_at"] = changes["tracking_updated_at"]
        db.table("shipments").update(changes).eq("id", shipment["id"]).eq(
            "organization_id", shipment["organization_id"]
        ).execute()
        return jsonify({"received": True, "matched": True}), 200
    except Exception:
        log.exception("Could not apply AfterShip tracking webhook")
        return jsonify({"error": "Could not apply tracking update."}), 500


@package_tracking_webhook_bp.post("/17track")
def seventeen_track_webhook():
    raw_body = request.get_data(cache=True)
    if not verify_17track_webhook(raw_body, request.headers.get("sign", "")):
        return jsonify({"error": "Invalid 17TRACK webhook signature."}), 401
    try:
        body = request.get_json(force=True) or {}
        if body.get("event") == "TRACKING_STOPPED":
            return jsonify({"received": True, "stopped": True}), 200
        tracking = body.get("data") or {}
        number = tracking.get("number")
        if not number:
            return jsonify({"error": "Webhook is missing the tracking number."}), 400
        tracking["tracking_provider"] = "17track"
        db = get_client()
        rows = db.table("shipments").select("id,organization_id,origin,destination").eq(
            "tracking_number", number
        ).eq("tracking_provider", "17track").limit(1).execute().data
        if not rows:
            return jsonify({"received": True, "matched": False}), 200
        shipment = rows[0]
        changes = normalize_tracking(tracking, fallback_origin=shipment.get("origin"), fallback_destination=shipment.get("destination"))
        changes["carrier_name"] = changes.get("tracking_carrier")
        changes["tracking_updated_at"] = datetime.now(timezone.utc).isoformat()
        changes["carrier_tracking_updated_at"] = changes["tracking_updated_at"]
        db.table("shipments").update(changes).eq("id", shipment["id"]).eq(
            "organization_id", shipment["organization_id"]
        ).execute()
        return jsonify({"received": True, "matched": True}), 200
    except Exception:
        log.exception("Could not apply 17TRACK webhook")
        return jsonify({"error": "Could not apply tracking update."}), 500


@shipments_bp.post("/<shipment_id>/route/refresh")
@login_required
def refresh_route(shipment_id):
    """Resolve a shipment's named route through Nominatim and OSRM."""
    db = get_client()
    rows = db.table("shipments").select("id, origin, destination, mode, transport_mode").eq("id", shipment_id).eq(
        "organization_id", g.current_user["org"]
    ).limit(1).execute().data
    if not rows:
        return jsonify({"error": "Shipment not found for this organization."}), 404
    shipment = rows[0]
    transport_mode = str(shipment.get("transport_mode") or shipment.get("mode") or "").lower()
    if transport_mode in {"plane", "air", "ship", "ocean", "sea"}:
        return jsonify({"error": "Road route planning is only available for land shipments."}), 409
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
        changes["mode"] = {"truck": "road", "ship": "ocean", "plane": "air"}[mode]
        if mode in {"ship", "plane"}:
            changes.update({
                "route_geometry": None,
                "route_distance_meters": None,
                "route_duration_seconds": None,
                "route_lookup_status": "not_applicable",
            })
    source = str(payload.get("tracking_source") or "")[:80]
    if source in {"traccar", "aisstream", "opensky"}:
        changes["live_tracking_provider"] = source
        changes["live_tracking_updated_at"] = changes["tracking_updated_at"]
        if payload.get("last_event_description"):
            changes["live_tracking_event"] = str(payload["last_event_description"])[:500]
    elif payload.get("last_event_description"):
        changes["last_event_description"] = payload["last_event_description"]
    if source:
        changes["tracking_source"] = source
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
