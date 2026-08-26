"""Autonomous operational decisions for orders, inventory and returns."""
from .base import BaseAgent, AgentOutput
from ..services.supabase_client import get_client
from ..services.minimax_client import MiniMaxError, chat_json, is_configured


class OperationsAgent(BaseAgent):
    name = "operations_agent"
    objective = "Turn incoming logistics work into safe, executable operational tasks."

    def _execute(self, organization_id: str, operation: str, entity: dict, **kwargs) -> AgentOutput:
        if operation == "dispatch_order":
            return self._dispatch_order(organization_id, entity, kwargs.get("shipment_id"))
        if operation == "inventory_review":
            return self._review_inventory(organization_id, entity)
        if operation == "process_return":
            return self._process_return(organization_id, entity)
        raise ValueError(f"Unsupported operation: {operation}")

    def _dispatch_order(self, organization_id, order, shipment_id=None):
        reasoning = self._reason("Dispatch this order safely and efficiently", order)
        route_plan = {
            "origin": order.get("origin"), "destination": order.get("destination"),
            "strategy": "nearest_available_driver", "reasoning": reasoning,
        }
        task = get_client().table("delivery_tasks").insert({
            "organization_id": organization_id, "order_id": order["id"], "shipment_id": shipment_id,
            "assigned_driver": "Auto-assigned on carrier connection", "route_plan": route_plan,
            "status": "dispatched",
        }).execute().data[0]
        get_client().table("orders").update({"status": "dispatched"}).eq("id", order["id"]).execute()
        return AgentOutput("action", f"Dispatched order {order['reference_number']} automatically.", {"task": task, "ai_provider": "minimax" if reasoning else "deterministic"})

    def _review_inventory(self, organization_id, item):
        low = item.get("quantity", 0) <= item.get("reorder_point", 0)
        action = "create_replenishment_exception" if low else "inventory_healthy"
        return AgentOutput("prediction", f"SKU {item['sku']} is {'below' if low else 'above'} its reorder point.", {"low_stock": low, "next_action": action})

    def _process_return(self, organization_id, return_case):
        get_client().table("returns").update({"status": "return_route_created"}).eq("id", return_case["id"]).execute()
        return AgentOutput("action", "Created a reverse-logistics route; warehouse inspection is queued.", {"return_id": return_case["id"]})

    def _reason(self, instruction, entity):
        if not is_configured():
            return None
        try:
            answer = chat_json([
                {"role": "system", "content": "You are a logistics operations planner. Return JSON with one key: reasoning. Never authorize spend, carrier bookings, refunds, or commitments."},
                {"role": "user", "content": f"{instruction}. Data: {entity}"},
            ])
            return str(answer.get("reasoning", ""))[:800]
        except MiniMaxError:
            return None
