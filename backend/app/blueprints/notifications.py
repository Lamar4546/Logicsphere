from flask import Blueprint, g, jsonify, request
from ..services.jwt import login_required
from ..services.notification_service import deliver
from ..services.supabase_client import get_client

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("/shipment/<shipment_id>")
@login_required
def list_for_shipment(shipment_id):
    rows = get_client().table("notification_log").select("*").eq("organization_id", g.current_user["org"]).eq("shipment_id", shipment_id).order("created_at", desc=True).execute().data
    return jsonify(rows)


@notifications_bp.post("/send")
@login_required
def send():
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    shipment_id, channel = payload.get("shipment_id"), payload.get("channel")
    if not shipment_id or channel not in {"email", "sms", "whatsapp"}:
        return jsonify({"error": "shipment_id and a valid channel are required"}), 400
    db = get_client()
    shipment = db.table("shipments").select("*").eq("id", shipment_id).eq("organization_id", org).single().execute().data
    if not shipment: return jsonify({"error": "Shipment not found"}), 404
    content, subject, communication_id = payload.get("body"), "Shipment update", None
    if payload.get("use_draft"):
        draft = db.table("communications").select("*").eq("organization_id", org).eq("related_entity_id", shipment_id).order("created_at", desc=True).limit(1).execute().data
        if not draft: return jsonify({"error": "No communication draft exists for this shipment"}), 404
        content, subject, communication_id = draft[0]["body"], draft[0].get("subject"), draft[0]["id"]
    if not content: return jsonify({"error": "Provide body or set use_draft"}), 400
    recipient = payload.get("recipient") or shipment.get("customer_contact")
    result = deliver(org, shipment_id, channel, recipient, content, subject=subject, communication_id=communication_id, triggered_by="user")
    return jsonify(result), 200 if result["success"] else 502
