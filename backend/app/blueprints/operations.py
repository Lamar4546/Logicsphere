import csv
import io
import logging

from flask import Blueprint, g, jsonify, request

from ..agents.operations_agent import OperationsAgent
from ..services.jwt import login_required
from ..services.route_lookup import route_between
from ..services.supabase_client import get_client

operations_bp = Blueprint("operations", __name__)
operations_agent = OperationsAgent()
log = logging.getLogger(__name__)


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
            "carrier_assignments": [], "financial_records": [],
        }
        try:
            overview["carrier_assignments"] = db.table("carrier_assignments").select("*").eq("organization_id", org).order("created_at", desc=True).limit(20).execute().data
            overview["financial_records"] = db.table("financial_records").select("*").eq("organization_id", org).order("recorded_at", desc=True).limit(20).execute().data
        except Exception:
            overview["integrations_ready"] = False
        else:
            overview["integrations_ready"] = True
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
