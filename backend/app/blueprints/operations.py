import csv
import base64
import binascii
import io
import logging
import math
import re

from flask import Blueprint, g, jsonify, request

from ..agents.operations_agent import OperationsAgent
from ..agents.risk_agent import DELAY_THRESHOLDS_HOURS
from ..autonomy.policy_engine import PolicyEngine
from ..services.jwt import login_required
from ..services.minimax_client import MiniMaxError, chat, is_configured, provider_name
from ..services.route_lookup import route_between
from ..services.supabase_client import get_client

operations_bp = Blueprint("operations", __name__)
operations_agent = OperationsAgent()
policy_engine = PolicyEngine()
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
            "shipments": db.table("shipments").select("id, order_id, reference_number, status, origin, destination").eq("organization_id", org).order("created_at", desc=True).limit(100).execute().data,
            "delivery_tasks": db.table("delivery_tasks").select("*").eq("organization_id", org).order("created_at", desc=True).limit(20).execute().data,
            "delivery_proofs": db.table("delivery_proofs").select("id, shipment_id, recipient_name, delivered_at").eq("organization_id", org).order("delivered_at", desc=True).limit(50).execute().data,
            "inventory": db.table("inventory_items").select("*").eq("organization_id", org).order("updated_at", desc=True).limit(50).execute().data,
            "returns": db.table("returns").select("*").eq("organization_id", org).order("created_at", desc=True).limit(20).execute().data,
            "carrier_assignments": [], "financial_records": [], "order_events": [],
            "fleet_vehicles": [], "fleet_vehicle_loads": [], "fleet_planning_ready": False,
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
        try:
            overview["fleet_vehicles"] = db.table("fleet_vehicles").select("*").eq("organization_id", org).order("created_at", desc=True).limit(100).execute().data
            overview["fleet_vehicle_loads"] = db.table("fleet_vehicle_loads").select("*").eq("organization_id", org).limit(500).execute().data
            overview["fleet_planning_ready"] = True
        except Exception:
            pass
        return jsonify(overview)
    except Exception as exc:
        return jsonify({"error": f"Operations tables unavailable. Apply migration 005_operations_control_plane.sql. Detail: {exc}"}), 503


@operations_bp.get("/rules")
@login_required
def list_system_rules():
    """Expose the active deterministic risk and approval policy to operators."""
    return jsonify({
        "delay_thresholds_hours": DELAY_THRESHOLDS_HOURS,
        "action_policy": policy_engine.describe_rules(),
    })


@operations_bp.post("/delivery-proofs")
@login_required
def record_delivery_proof():
    """Record real recipient/signature evidence and close the linked delivery."""
    payload, org, db = request.get_json(force=True) or {}, g.current_user["org"], get_client()
    shipment_id = payload.get("shipment_id")
    recipient = str(payload.get("recipient_name") or "").strip()
    signature = str(payload.get("signature_data_url") or "")
    photo = str(payload.get("photo_data_url") or "") or None
    if not shipment_id or not recipient or len(recipient) > 160:
        return jsonify({"error": "A shipment and recipient name are required."}), 400

    def valid_image_data_url(value, required=False):
        if not value:
            return not required
        match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", value)
        if not match or len(value) > 1_500_000:
            return False
        try:
            base64.b64decode(match.group(2), validate=True)
            return True
        except (ValueError, binascii.Error):
            return False

    if not valid_image_data_url(signature, required=True) or not valid_image_data_url(photo):
        return jsonify({"error": "Signature and photo must be PNG/JPEG images under 1.5 MB."}), 400

    task_id = payload.get("task_id")
    if task_id:
        tasks = db.table("delivery_tasks").select("id, shipment_id, order_id").eq("id", task_id).eq("organization_id", org).limit(1).execute().data
        if not tasks or str(tasks[0].get("shipment_id")) != str(shipment_id):
            return jsonify({"error": "Delivery task and shipment do not match this organization."}), 404
        task = tasks[0]
    else:
        task = None

    shipment = db.table("shipments").select("id, order_id").eq("id", shipment_id).eq("organization_id", org).limit(1).execute().data
    if not shipment:
        return jsonify({"error": "Shipment not found for this organization."}), 404
    proof = db.table("delivery_proofs").insert({
        "organization_id": org,
        "shipment_id": shipment_id,
        "recipient_name": recipient,
        "signature_url": signature,
        "photo_url": photo,
    }).execute().data[0]
    db.table("shipments").update({"status": "delivered"}).eq("id", shipment_id).eq("organization_id", org).execute()
    if task:
        db.table("delivery_tasks").update({"status": "delivered"}).eq("id", task_id).eq("organization_id", org).execute()
    order_id = (task or shipment[0]).get("order_id")
    if order_id:
        db.table("orders").update({"status": "delivered"}).eq("id", order_id).eq("organization_id", org).execute()
    return jsonify({"proof": proof, "message": "Proof recorded and linked delivery marked delivered."}), 201


@operations_bp.post("/fleet-vehicles")
@login_required
def create_fleet_vehicle():
    payload = request.get_json(silent=True) or {}
    reference = str(payload.get("vehicle_reference") or "").strip()
    driver = str(payload.get("driver_name") or "").strip() or None
    dock = str(payload.get("dock_label") or "").strip() or None
    try:
        capacity = float(payload.get("capacity_kg"))
        compartments = int(payload.get("compartment_count"))
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid vehicle capacity and compartment count."}), 400
    if not reference or len(reference) > 80 or not math.isfinite(capacity) or capacity <= 0 or compartments < 1 or compartments > 60:
        return jsonify({"error": "A vehicle reference, positive capacity, and 1–60 compartments are required."}), 400
    vehicle = get_client().table("fleet_vehicles").insert({
        "organization_id": g.current_user["org"], "vehicle_reference": reference,
        "driver_name": driver, "capacity_kg": capacity, "compartment_count": compartments,
        "dock_label": dock,
    }).execute().data[0]
    return jsonify({"vehicle": vehicle}), 201


@operations_bp.post("/fleet-vehicles/<vehicle_id>/loads")
@login_required
def assign_shipment_to_vehicle(vehicle_id):
    payload = request.get_json(silent=True) or {}
    org = g.current_user["org"]
    shipment_id = payload.get("shipment_id")
    slot_code = str(payload.get("slot_code") or "").strip().upper()
    try:
        weight = float(payload.get("weight_kg"))
    except (TypeError, ValueError):
        return jsonify({"error": "Enter the cargo weight in kilograms."}), 400
    db = get_client()
    vehicle_rows = db.table("fleet_vehicles").select("*").eq("id", vehicle_id).eq("organization_id", org).limit(1).execute().data
    if not vehicle_rows:
        return jsonify({"error": "Vehicle not found."}), 404
    vehicle = vehicle_rows[0]
    if vehicle.get("status") not in {"available", "loading"}:
        return jsonify({"error": "This vehicle is not available for loading."}), 409
    slot_number = int(slot_code[1:]) if len(slot_code) > 1 and slot_code[0] == "A" and slot_code[1:].isdigit() else 0
    if not shipment_id:
        return jsonify({"error": "Select a shipment to assign."}), 400
    if slot_number < 1 or slot_number > int(vehicle["compartment_count"]):
        return jsonify({"error": "Choose an available slot on this vehicle."}), 400
    if not math.isfinite(weight) or weight <= 0:
        return jsonify({"error": "Cargo weight must be greater than zero."}), 400
    shipment_rows = db.table("shipments").select("id, status").eq("id", shipment_id).eq("organization_id", org).limit(1).execute().data
    if not shipment_rows or str(shipment_rows[0].get("status", "")).lower() in {"delivered", "cancelled"}:
        return jsonify({"error": "Choose an active shipment belonging to this organization."}), 404
    loads = db.table("fleet_vehicle_loads").select("weight_kg").eq("vehicle_id", vehicle_id).eq("organization_id", org).execute().data
    if sum(float(load.get("weight_kg") or 0) for load in loads) + weight > float(vehicle["capacity_kg"]):
        return jsonify({"error": "This load would exceed the vehicle's rated capacity."}), 409
    try:
        result = db.table("fleet_vehicle_loads").insert({
            "organization_id": org, "vehicle_id": vehicle_id, "shipment_id": shipment_id,
            "slot_code": slot_code, "weight_kg": weight,
        }).execute()
    except Exception:
        log.exception("Could not assign shipment to fleet vehicle")
        return jsonify({"error": "The slot or shipment is already assigned. Refresh the load plan and try again."}), 409
    db.table("fleet_vehicles").update({"status": "loading"}).eq("id", vehicle_id).eq("organization_id", org).execute()
    return jsonify({"load": result.data[0]}), 201


@operations_bp.delete("/fleet-loads/<load_id>")
@login_required
def remove_fleet_load(load_id):
    org = g.current_user["org"]
    db = get_client()
    existing = db.table("fleet_vehicle_loads").select("vehicle_id").eq("id", load_id).eq("organization_id", org).limit(1).execute().data
    if not existing:
        return jsonify({"error": "Load assignment not found."}), 404
    vehicle_id = existing[0]["vehicle_id"]
    result = db.table("fleet_vehicle_loads").delete().eq("id", load_id).eq("organization_id", org).execute()
    if not result.data:
        return jsonify({"error": "Load assignment not found."}), 404
    still_loaded = db.table("fleet_vehicle_loads").select("id").eq("vehicle_id", vehicle_id).eq("organization_id", org).limit(1).execute().data
    if not still_loaded:
        db.table("fleet_vehicles").update({"status": "available"}).eq("id", vehicle_id).eq("organization_id", org).execute()
    return jsonify({"message": "Shipment removed from the vehicle load plan."})


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
