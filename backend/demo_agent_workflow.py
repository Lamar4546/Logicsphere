"""Run a live, inspectable shipment-agent demo against the local API.

Prerequisites:
  1. Apply the Supabase schema/migrations and set backend/.env.
  2. Set MINIMAX_API_KEY in backend/.env to observe MiniMax reasoning.
  3. Start the backend: python run.py
  4. Run: python demo_agent_workflow.py

The script creates a throwaway organization and two shipments:
  - a medium delay that the agents resolve autonomously;
  - a critical delay that intentionally pauses for human approval.
"""
from datetime import datetime, timedelta, timezone
import json
import time

import requests


BASE_URL = "http://127.0.0.1:5000/api"


def request(method, path, *, token=None, payload=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = requests.request(method, f"{BASE_URL}{path}", headers=headers, json=payload, timeout=30)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if not response.ok:
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {body}")
    return body


def create_and_evaluate(token, reference, delay_hours):
    now = datetime.now(timezone.utc)
    shipment = request(
        "POST",
        "/shipments",
        token=token,
        payload={
            "reference_number": reference,
            "origin": "Kingston, JM",
            "destination": "Miami, US",
            "status": "in_transit",
            "eta_original": (now + timedelta(hours=24)).isoformat(),
            "eta_current": (now + timedelta(hours=24 + delay_hours)).isoformat(),
            "last_event_description": "Carrier reported a port congestion delay.",
            "source_system": "agent_workflow_demo",
        },
    )
    return request("POST", f"/shipments/{shipment['id']}/evaluate", token=token, payload={})


def main():
    suffix = int(time.time())
    email = f"agent-demo-{suffix}@example.com"
    password = "DemoPass123!"
    registration = request(
        "POST",
        "/auth/register",
        payload={
            "company_name": f"Agent Demo {suffix}",
            "full_name": "Workflow Tester",
            "email": email,
            "password": password,
        },
    )
    token = registration["token"]

    print(f"Sign into the frontend with: {email} / {password}")

    automatic = create_and_evaluate(token, f"AUTO-{suffix}", 8)
    critical = create_and_evaluate(token, f"CRITICAL-{suffix}", 80)

    print("\n=== Routine medium-delay workflow ===")
    print(json.dumps({
        "severity": automatic["risk"]["data"]["severity"],
        "ai_provider": automatic["risk"]["data"].get("ai_provider"),
        "ai_reasoning": automatic["risk"]["data"].get("ai_reasoning"),
        "policy": automatic["policy"],
        "workflow_result": automatic["autonomous_action_result"],
    }, indent=2))

    print("\n=== Critical-delay workflow ===")
    print(json.dumps({
        "severity": critical["risk"]["data"]["severity"],
        "ai_provider": critical["risk"]["data"].get("ai_provider"),
        "policy": critical["policy"],
        "requires_human_approval": critical["policy"]["requires_approval"],
    }, indent=2))
    print("\nOpen the Command Center > Exceptions tab to approve the critical case.")


if __name__ == "__main__":
    main()
