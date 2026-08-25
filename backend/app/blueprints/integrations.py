from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from ..services.integration_service import import_records, push
from ..services.jwt import login_required
from ..services.supabase_client import get_client

integrations_bp = Blueprint("integrations", __name__)


@integrations_bp.get("/connections")
@login_required
def list_connections():
    rows = get_client().table("integration_connections").select(
        "id, code, name, base_url, auth_env_key, enabled, created_at"
    ).eq("organization_id", g.current_user["org"]).order("code").execute().data
    return jsonify(rows)


@integrations_bp.post("/connections")
@login_required
def save_connection():
    """Configure a provider URL; its secret remains server-only in an env var."""
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    code, name, base_url = payload.get("code"), payload.get("name"), payload.get("base_url")
    if code not in {"carrier", "erp", "wms"} or not name or not base_url:
        return jsonify({"error": "code (carrier, erp, or wms), name, and base_url are required."}), 400
    if not str(base_url).startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return jsonify({"error": "base_url must use HTTPS (localhost is allowed for testing)."}), 400
    row = get_client().table("integration_connections").upsert({
        "organization_id": org, "code": code, "name": name, "base_url": base_url.rstrip("/"),
        "auth_env_key": payload.get("auth_env_key") or None, "enabled": bool(payload.get("enabled", True)),
    }, on_conflict="organization_id,code").execute().data
    return jsonify(row[0] if row else {}), 201


@integrations_bp.post("/carrier-assignments")
@login_required
def create_carrier_assignment():
    """Prepare a delivery assignment. Monetary quotes require approval."""
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    if not payload.get("carrier_name") or not (payload.get("shipment_id") or payload.get("order_id")):
        return jsonify({"error": "carrier_name and shipment_id or order_id are required."}), 400
    has_cost = payload.get("quoted_amount") is not None
    assignment = get_client().table("carrier_assignments").insert({
        "organization_id": org, "shipment_id": payload.get("shipment_id"), "order_id": payload.get("order_id"),
        "carrier_name": payload["carrier_name"], "service_level": payload.get("service_level"), "driver_reference": payload.get("driver_reference"),
        "status": "pending_approval" if has_cost else "ready_to_dispatch", "request_payload": payload,
    }).execute().data
    return jsonify(assignment[0] if assignment else {}), 201


@integrations_bp.post("/carrier-assignments/<assignment_id>/dispatch")
@login_required
def dispatch_carrier_assignment(assignment_id):
    """Execute a user-confirmed, non-LLM carrier booking/assignment."""
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    if payload.get("confirm") is not True:
        return jsonify({"error": "Set confirm: true to dispatch this carrier assignment."}), 400
    db = get_client()
    rows = db.table("carrier_assignments").select("*").eq("id", assignment_id).eq("organization_id", org).execute().data
    if not rows:
        return jsonify({"error": "Carrier assignment not found."}), 404
    assignment = rows[0]
    if assignment["status"] not in {"ready_to_dispatch", "pending_approval"}:
        return jsonify({"error": f"Assignment cannot be dispatched from {assignment['status']}."}), 409
    result = push(org, "carrier", "assignments", assignment["request_payload"])
    changes = {"status": "dispatched" if result["success"] else "failed", "response_payload": result.get("data"), "error": result.get("error")}
    if result["success"]:
        changes["dispatched_at"] = datetime.now(timezone.utc).isoformat()
        changes["external_assignment_id"] = (result.get("data") or {}).get("id") or (result.get("data") or {}).get("assignment_id")
    updated = db.table("carrier_assignments").update(changes).eq("id", assignment_id).execute().data
    return jsonify({"assignment": updated[0] if updated else assignment, "delivery": result}), 200 if result["success"] else 502


@integrations_bp.post("/sync")
@login_required
def sync_records():
    """Ingest real WMS inventory or ERP financial records from an adapter."""
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    code, resource, records = payload.get("integration"), payload.get("resource"), payload.get("records")
    if not isinstance(records, list):
        return jsonify({"error": "records must be an array."}), 400
    try:
        result = import_records(org, code, resource, records)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result), 200 if result["success"] else 502
