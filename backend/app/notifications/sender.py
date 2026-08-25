"""Delivery providers. These functions are independently testable and never touch agents."""
from __future__ import annotations

import os
import requests


def _result(success, provider, message_id=None, error=None):
    return {"success": success, "provider": provider, "message_id": message_id, "error": error}


def send_sms(to: str, body: str) -> dict:
    sid, token, sender = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_SMS_FROM")
    if not all([sid, token, sender]):
        return _result(False, "twilio", error="Twilio SMS credentials are not configured.")
    try:
        response = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, token), data={"To": to, "From": sender, "Body": body}, timeout=15)
        payload = response.json()
        return _result(response.ok, "twilio", payload.get("sid"), None if response.ok else payload.get("message", response.text))
    except requests.RequestException as exc:
        return _result(False, "twilio", error=str(exc))


def send_whatsapp(to: str, body: str) -> dict:
    sid, token, sender = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_WHATSAPP_FROM")
    if not all([sid, token, sender]):
        return _result(False, "twilio_whatsapp", error="Twilio WhatsApp sandbox credentials are not configured.")
    try:
        response = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, token), data={"To": f"whatsapp:{to.removeprefix('whatsapp:')}", "From": f"whatsapp:{sender.removeprefix('whatsapp:')}", "Body": body}, timeout=15)
        payload = response.json()
        return _result(response.ok, "twilio_whatsapp", payload.get("sid"), None if response.ok else payload.get("message", response.text))
    except requests.RequestException as exc:
        return _result(False, "twilio_whatsapp", error=str(exc))


def send_email(to: str, subject: str, body: str) -> dict:
    api_key, sender = os.getenv("SENDGRID_API_KEY"), os.getenv("SENDGRID_FROM_EMAIL")
    if not all([api_key, sender]):
        return _result(False, "sendgrid", error="SendGrid credentials are not configured.")
    payload = {"personalizations": [{"to": [{"email": to}]}], "from": {"email": sender}, "subject": subject, "content": [{"type": "text/plain", "value": body}]}
    if os.getenv("SENDGRID_SANDBOX_MODE", "true").lower() == "true":
        payload["mail_settings"] = {"sandbox_mode": {"enable": True}}
    try:
        response = requests.post("https://api.sendgrid.com/v3/mail/send", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload, timeout=15)
        return _result(response.status_code in (200, 202), "sendgrid", response.headers.get("X-Message-Id"), None if response.status_code in (200, 202) else response.text)
    except requests.RequestException as exc:
        return _result(False, "sendgrid", error=str(exc))
