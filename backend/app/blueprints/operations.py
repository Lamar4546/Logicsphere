from flask import Blueprint, g, jsonify, request

from ..agents.operations_agent import OperationsAgent
from ..services.jwt import login_required
from ..services.supabase_client import get_client

operations_bp = Blueprint("operations", __name__)
operations_agent = OperationsAgent()


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
        # Migration 007 adds integration data. Keep core operations usable
        # until it has been run, instead of making the whole page unavailable.
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


@operations_bp.post("/orders")
@login_required
def create_order():
    payload, org = request.get_json(force=True) or {}, g.current_user["org"]
    if not payload.get("reference_number"):
        return jsonify({"error": "reference_number is required"}), 400
    order = get_client().table("orders").insert({
        "organization_id": org, "reference_number": payload["reference_number"], "customer_name": payload.get("customer_name"),
        "origin": payload.get("origin"), "destination": payload.get("destination"), "priority": payload.get("priority", "standard"),
    }).execute().data[0]
    result = operations_agent.run(org, entity_type="order", entity_id=order["id"], operation="dispatch_order", entity=order)
    return jsonify({"order": order, "agent_result": result.to_dict()}), 201


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
