import csv
import io
import logging

from flask import Blueprint, g, jsonify, request

from ..agents.operations_agent import OperationsAgent
from ..services.jwt import login_required
from ..services.minimax_client import MiniMaxError, chat, is_configured, provider_name
from ..services.route_lookup import route_between
from ..services.supabase_client import get_client

operations_bp = Blueprint("operations", __name__)
operations_agent = OperationsAgent()
log = logging.getLogger(__name__)


def _record_order_event(db, org, order_id, event_type, details):
    """Write an audit event when the optional audit migration is installed."""
    try:
        db.table("order_events").insert({
            "organization_id": org, "order_id": order_id, "event_type": event_type,
            "details": details, "created_by": g.current_user["sub"],
        }).execute()
    except Exception:
        log.warning("Could not write order audit event; apply migration 011_order_change_audit.sql")


@operations_bp.get("/overview")
@login_required
def overview():
    db, org = get_client(), g.current_user["org"]
    try:
        overview = {
            "orders": db.table("orders").select("*").eq("organization_id", org).order("created_at", desc=True).limit(20).execute().data,
            "delivery_tasks": db.table("delivery_tasks").select("*").eq("organization_id", org).order("created_at", desc=True).limit(20).execute().data,
            "inventory": db.table("inventory_items").select("*").eq("organization_id", org).order("updated_at", desc=True).limit(50).execute().data,
            "returns": db.table("returns").select("*").eq("organization_id", org).order("created_at", desc=True).limit(20).execute().data,
            "carrier_assignments": [], "financial_records": [], "order_events": [],
        }
        try:
            overview["carrier_assignments"] = db.table("carrier_assignments").select("*").eq("organization_id", org).order("created_at", desc=True).limit(20).execute().data
            overview["financial_records"] = db.table("financial_records").select("*").eq("organization_id", org).order("recorded_at", desc=True).limit(20).execute().data
        except Exception:
            overview["integrations_ready"] = False
        else:
            overview["integrations_ready"] = True
        try:
            overview["order_events"] = db.table("order_events").select("*").eq("organization_id", org).order("created_at", desc=True).limit(30).execute().data
        except Exception:
            pass
        return jsonify(overview)
    except Exception as exc:
        return jsonify({"error": f"Operations tables unavailable. Apply migration 005_operations_control_plane.sql. Detail: {exc}"}), 503


def _create_order_and_shipment(db, org, data):
    """Shared by manual order creation and CSV import. Creates the order,
    then the linked shipment row so Control Tower sees it immediately.
    Returns (created_dict, error_message)."""
    reference_number = (data.get("reference_number") or "").strip()
    if not reference_number:
        return None, "reference_number is required"

    order = db.table("orders").insert({
        "organization_id": org,
        "reference_number": reference_number,
        "customer_name": (data.get("customer_name") or "").strip() or None,
        "origin": (data.get("origin") or "").strip() or None,
        "destination": (data.get("destination") or "").strip() or None,
        "priority": (data.get("priority") or "standard").strip().lower(),
    }).execute().data[0]

    route_data = {}
    if order.get("origin") and order.get("destination"):
        try:
            route_data = route_between(order["origin"], order["destination"]) or {"route_lookup_status": "not_found"}
        except Exception:
            # A public map outage must not prevent order intake or dispatch.
            log.exception("Route lookup failed for order %s", reference_number)
            route_data = {"route_lookup_status": "unavailable"}

    try:
        shipment = db.table("shipments").insert({
            "organization_id": org,
            "order_id": order["id"],
            "reference_number": order["reference_number"],
            "origin": order.get("origin"),
            "destination": order.get("destination"),
            "status": "planned",
            "source_system": "order_dispatch",
            **route_data,
        }).execute().data[0]
    except Exception as exc:
        # Avoid leaving a hidden order behind if the linking migration has not
        # been applied or the shipment insert is rejected.
        db.table("orders").delete().eq("id", order["id"]).eq("organization_id", org).execute()
        if "order_id" in str(exc):
            return None, "Order-to-shipment linking needs migration 008_order_shipment_link.sql."
        raise

    return {"order": order, "shipment": shipment}, None


@operations_bp.post("/orders")
@login_required
def create_order():
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    db = get_client()

    created, error = _create_order_and_shipment(db, org, payload)
    if error:
        return jsonify({"error": error}), 400

    result = operations_agent.run(
        org, entity_type="order", entity_id=created["order"]["id"],
        operation="dispatch_order", entity=created["order"], shipment_id=created["shipment"]["id"],
    )
    return jsonify({
        "order": created["order"],
        "shipment": created["shipment"],
        "agent_result": result.to_dict(),
    }), 201


@operations_bp.patch("/orders/<order_id>")
@login_required
def update_order(order_id):
    """Update operational fields after dispatch and keep linked work aligned."""
    payload, org, db = request.get_json(force=True) or {}, g.current_user["org"], get_client()
    rows = db.table("orders").select("*").eq("id", order_id).eq("organization_id", org).limit(1).execute().data
    if not rows:
        return jsonify({"error": "Order not found for this organization."}), 404
    current = rows[0]
    if current.get("status") == "cancelled":
        return jsonify({"error": "Cancelled orders cannot be changed."}), 409

    allowed = {"customer_name", "origin", "destination", "priority"}
    changes = {key: (str(payload[key]).strip() or None) for key in allowed if key in payload}
    if "priority" in changes and changes["priority"] not in {"standard", "urgent"}:
        return jsonify({"error": "Priority must be standard or urgent."}), 400
    if not changes:
        return jsonify({"error": "Provide at least one editable order field."}), 400

    updated_order = db.table("orders").update(changes).eq("id", order_id).eq("organization_id", org).execute().data[0]
    shipment_changes = {key: changes[key] for key in ("origin", "destination") if key in changes}
    if shipment_changes:
        route_data = {}
        if updated_order.get("origin") and updated_order.get("destination"):
            try:
                route_data = route_between(updated_order["origin"], updated_order["destination"]) or {"route_lookup_status": "not_found"}
            except Exception:
                log.exception("Route refresh failed for edited order %s", order_id)
                route_data = {"route_lookup_status": "unavailable"}
        shipment_changes.update(route_data)
        db.table("shipments").update(shipment_changes).eq("order_id", order_id).eq("organization_id", org).execute()
        tasks = db.table("delivery_tasks").select("id, route_plan").eq("order_id", order_id).eq("organization_id", org).execute().data
        for task in tasks:
            route_plan = {**(task.get("route_plan") or {}), "origin": updated_order.get("origin"), "destination": updated_order.get("destination")}
            db.table("delivery_tasks").update({"route_plan": route_plan}).eq("id", task["id"]).execute()

    _record_order_event(db, org, order_id, "order_updated", {"before": {key: current.get(key) for key in changes}, "after": changes})
    return jsonify({"order": updated_order, "message": "Order and linked shipment details updated. Confirm carrier changes separately if already sent externally."})


@operations_bp.delete("/orders/<order_id>")
@login_required
def cancel_order(order_id):
    """Remove an order from active operations by cancelling, never erasing dispatch history."""
    payload, org, db = request.get_json(silent=True) or {}, g.current_user["org"], get_client()
    if payload.get("confirmation") != "CANCEL":
        return jsonify({"error": "Type CANCEL to confirm removing this order from active operations."}), 400
    rows = db.table("orders").select("id, reference_number, status").eq("id", order_id).eq("organization_id", org).limit(1).execute().data
    if not rows:
        return jsonify({"error": "Order not found for this organization."}), 404
    order = rows[0]
    db.table("orders").update({"status": "cancelled"}).eq("id", order_id).eq("organization_id", org).execute()
    shipment_result = db.table("shipments").update({"status": "cancelled"}).eq("order_id", order_id).eq("organization_id", org).execute()
    db.table("delivery_tasks").update({"status": "cancelled"}).eq("order_id", order_id).eq("organization_id", org).execute()
    if not shipment_result.data:
        log.warning("Cancelled order %s has no linked shipment. Apply migration 008_order_shipment_link.sql to link orders and tracking.", order_id)
    _record_order_event(db, org, order_id, "order_cancelled", {"previous_status": order.get("status")})
    return jsonify({"message": f"{order['reference_number']} was cancelled and removed from active dispatch. The audit history was retained."})


@operations_bp.post("/assistant")
@login_required
def ask_operations_assistant():
    """Return MiniMax advice without allowing conversational side effects."""
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    message = str(payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Enter a question for the AI assistant."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Keep questions under 2,000 characters."}), 400

    db = get_client()
    orders = db.table("orders").select("reference_number, status, origin, destination, priority").eq("organization_id", org).order("created_at", desc=True).limit(12).execute().data
    inventory = db.table("inventory_items").select("sku, name, quantity, reorder_point").eq("organization_id", org).limit(20).execute().data
    context = {"recent_orders": orders, "inventory": inventory}
    if not is_configured():
        return jsonify({
            "reply": "Hugging Face has not been configured on this backend yet. An administrator must add HF_TOKEN in the hosting service’s environment settings, then redeploy. I will not make changes from chat.",
            "provider": "deterministic_fallback", "provider_status": "not_configured",
        })
    try:
        reply = chat([
            {"role": "system", "content": "You are LogiSphere's logistics operations assistant. Give concise operational feedback using the supplied workspace facts. You may explain, prioritise, and suggest next steps, but you cannot create, edit, cancel, dispatch, spend money, or communicate externally. State when human approval is required for money or critical exceptions."},
            {"role": "user", "content": f"Workspace facts: {context}\n\nUser question: {message}"},
        ], temperature=0.35)
        return jsonify({"reply": reply.strip(), "provider": provider_name(), "provider_status": "ready"})
    except MiniMaxError:
        log.exception("MiniMax operations assistant request failed")
        return jsonify({
            "reply": "The configured AI provider did not respond. Check the Render service logs for the Hugging Face request failure, then try again. I will not make changes from chat.",
            "provider": "deterministic_fallback", "provider_status": "request_failed",
        })


@operations_bp.post("/orders/import")
@login_required
def import_orders_csv():
    """Bulk-create orders (and their linked shipments) from an uploaded CSV.
    Expected columns (case-insensitive, extras ignored):
    reference_number, customer_name, origin, destination, priority
    """
    org = g.current_user["org"]

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Send multipart/form-data with a 'file' field."}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "File must be a .csv"}), 400

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
        reader = csv.DictReader(stream)
    except Exception as e:
        return jsonify({"error": f"Could not parse CSV: {e}"}), 400

    if not reader.fieldnames:
        return jsonify({"error": "CSV has no header row."}), 400

    db = get_client()
    created_references, errors = [], []

    for row_num, raw_row in enumerate(reader, start=2):  # row 1 is the header
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        created, error = _create_order_and_shipment(db, org, row)
        if error:
            errors.append({"row": row_num, "error": error})
            continue

        try:
            operations_agent.run(
                org, entity_type="order", entity_id=created["order"]["id"],
                operation="dispatch_order", entity=created["order"], shipment_id=created["shipment"]["id"],
            )
        except Exception:
            log.exception("Agent dispatch failed for imported order (row %s)", row_num)
            errors.append({"row": row_num, "error": "Order created, but agent dispatch failed. Check logs."})

        created_references.append(created["order"]["reference_number"])

    status = 201 if created_references else 400
    return jsonify({
        "imported": len(created_references),
        "failed": len(errors),
        "created_references": created_references,
        "errors": errors,
    }), status


@operations_bp.post("/inventory")
@login_required
def upsert_inventory():
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    if not payload.get("sku") or not payload.get("name"):
        return jsonify({"error": "sku and name are required"}), 400
    item = get_client().table("inventory_items").upsert({
        "organization_id": org, "sku": payload["sku"], "name": payload["name"], "quantity": int(payload.get("quantity", 0)),
        "reorder_point": int(payload.get("reorder_point", 0)), "location": payload.get("location"),
    }, on_conflict="organization_id,sku").execute().data[0]
    result = operations_agent.run(org, entity_type="inventory_item", entity_id=item["id"], operation="inventory_review", entity=item)
    return jsonify({"item": item, "agent_result": result.to_dict()}), 201


@operations_bp.post("/returns")
@login_required
def create_return():
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    return_case = get_client().table("returns").insert({"organization_id": org, "order_id": payload.get("order_id"), "reason": payload.get("reason")}).execute().data[0]
    result = operations_agent.run(org, entity_type="return", entity_id=return_case["id"], operation="process_return", entity=return_case)
    return jsonify({"return": return_case, "agent_result": result.to_dict()}), 201
