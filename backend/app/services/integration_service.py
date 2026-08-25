"""Provider-neutral carrier, ERP, and WMS integration boundary.

Credentials are read from the server environment. Agents never make these
calls; they only prepare safe internal work for a user-controlled dispatch.
"""
from __future__ import annotations

import os
import requests

from .supabase_client import get_client


def _log(org, code, direction, resource, status, count=0, detail=None):
    try:
        return get_client().table("integration_sync_log").insert({
            "organization_id": org, "integration_code": code, "direction": direction,
            "resource": resource, "status": status, "record_count": count, "detail": detail or {},
        }).execute().data
    except Exception:
        # A connection error must be reported to the dispatcher even while a
        # deployment is waiting for the integration migration to be applied.
        return None


def push(org: str, code: str, resource: str, payload: dict) -> dict:
    """Send to an explicitly configured connection and audit every attempt."""
    db = get_client()
    connection = db.table("integration_connections").select("*").eq("organization_id", org).eq("code", code).eq("enabled", True).execute().data
    if not connection:
        result = {"success": False, "error": f"No enabled {code.upper()} connection is configured."}
        _log(org, code, "outbound", resource, "failed", detail=result)
        return result
    connection = connection[0]
    token = os.getenv(connection.get("auth_env_key") or "")
    if connection.get("auth_env_key") and not token:
        result = {"success": False, "error": f"Server environment variable {connection['auth_env_key']} is not configured."}
        _log(org, code, "outbound", resource, "failed", detail=result)
        return result
    try:
        response = requests.post(
            f"{connection['base_url'].rstrip('/')}/{resource.lstrip('/')}", json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else {"Content-Type": "application/json"}, timeout=20,
        )
        data = response.json() if response.content else {}
        result = {"success": response.ok, "status_code": response.status_code, "data": data if response.ok else None, "error": None if response.ok else str(data or response.text)}
    except requests.RequestException as exc:
        result = {"success": False, "error": str(exc)}
    _log(org, code, "outbound", resource, "success" if result["success"] else "failed", 1 if result["success"] else 0, result)
    return result


def import_records(org: str, code: str, resource: str, records: list[dict]) -> dict:
    """Store inbound WMS inventory and ERP financial records with provenance."""
    if (code, resource) not in {("wms", "inventory"), ("erp", "financial_records")}:
        raise ValueError("Use WMS for inventory imports and ERP for financial_records imports.")
    db = get_client()
    try:
        if resource == "inventory":
            for item in records:
                if not item.get("sku") or not item.get("name"):
                    raise ValueError("Each inventory record requires sku and name.")
                db.table("inventory_items").upsert({
                    "organization_id": org, "sku": item["sku"], "name": item["name"],
                    "quantity": int(item.get("quantity", 0)), "reorder_point": int(item.get("reorder_point", 0)), "location": item.get("location"),
                }, on_conflict="organization_id,sku").execute()
        else:
            for record in records:
                if not record.get("external_id") or not record.get("record_type"):
                    raise ValueError("Each financial record requires external_id and record_type.")
                db.table("financial_records").upsert({
                    "organization_id": org, "external_id": record["external_id"], "document_number": record.get("document_number"),
                    "record_type": record["record_type"], "amount": record.get("amount"), "currency": record.get("currency", "USD"),
                    "status": record.get("status"), "source_payload": record,
                }, on_conflict="organization_id,external_id").execute()
        result = {"success": True, "imported": len(records)}
        _log(org, code, "inbound", resource, "success", len(records), result)
        return result
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
        _log(org, code, "inbound", resource, "failed", 0, result)
        return result
