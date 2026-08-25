from ..notifications.sender import send_email, send_sms, send_whatsapp
from .supabase_client import get_client


def deliver(organization_id, shipment_id, channel, recipient, content, *, subject=None, communication_id=None, triggered_by="system"):
    if not recipient:
        result = {"success": False, "provider": "none", "message_id": None, "error": "No customer recipient is recorded for this shipment."}
    elif channel == "email": result = send_email(recipient, subject or "Shipment update", content)
    elif channel == "sms": result = send_sms(recipient, content)
    elif channel == "whatsapp": result = send_whatsapp(recipient, content)
    else: result = {"success": False, "provider": "none", "message_id": None, "error": f"Unsupported channel: {channel}"}
    try:
        log = get_client().table("notification_log").insert({"organization_id": organization_id, "shipment_id": shipment_id, "communication_id": communication_id, "channel": channel, "recipient": recipient, "content": content, "status": "sent" if result["success"] else "failed", "provider_message_id": result["message_id"], "error": result["error"], "triggered_by": triggered_by}).execute().data
    except Exception as exc:
        # A provider failure or an unavailable audit table must never break a
        # shipment-delay workflow. The caller can still present this outcome.
        if result["success"]:
            result = {**result, "success": False, "error": f"Delivery succeeded but audit logging failed: {exc}"}
        return {**result, "log": None}
    return {**result, "log": log[0] if log else None}
