"""Forward the latest Traccar phone position into a LogiSphere shipment.

Configure the TRACCAR_* and LOGISPHERE_* environment variables documented in
README.md, then run ``python traccar_bridge.py``. The bridge only reads the
configured Traccar device and updates the configured LogiSphere shipment.
"""

import argparse
from datetime import datetime, timedelta, timezone
import getpass
import os
import sys
import time

import requests


TRACCAR_URL = os.getenv("TRACCAR_URL", "http://localhost:8082").rstrip("/")
TRACCAR_DEVICE_UNIQUE_ID = os.getenv("TRACCAR_DEVICE_UNIQUE_ID", "").strip()
TRACCAR_TOKEN = os.getenv("TRACCAR_TOKEN", "").strip()
TRACCAR_USERNAME = os.getenv("TRACCAR_USERNAME", "").strip()
TRACCAR_PASSWORD = os.getenv("TRACCAR_PASSWORD", "")
LOGISPHERE_API = os.getenv("LOGISPHERE_API", "http://localhost:5000").rstrip("/")
LOGISPHERE_TOKEN = os.getenv("LOGISPHERE_TOKEN", "").strip()
LOGISPHERE_SHIPMENT_ID = os.getenv("LOGISPHERE_SHIPMENT_ID", "").strip()
POLL_SECONDS = max(2, int(os.getenv("TRACCAR_POLL_SECONDS", "5")))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="read and forward one position, then exit")
    parser.add_argument("--create-demo", action="store_true", help="create a new in-transit shipment and use it")
    parser.add_argument("--mode", choices=("land", "sea", "air"), default="land",
                        help="transport mode to show on the shipment (default: land)")
    return parser.parse_args()


def traccar_session():
    if not TRACCAR_DEVICE_UNIQUE_ID:
        raise RuntimeError("Set TRACCAR_DEVICE_UNIQUE_ID to the identifier shown in Traccar Client.")
    session = requests.Session()
    session.headers["Accept"] = "application/json"
    if TRACCAR_TOKEN:
        session.headers["Authorization"] = f"Bearer {TRACCAR_TOKEN}"
    elif TRACCAR_USERNAME:
        session.auth = (TRACCAR_USERNAME, TRACCAR_PASSWORD or getpass.getpass("Traccar password: "))
    else:
        username = input("Traccar username: ").strip()
        session.auth = (username, getpass.getpass("Traccar password: "))

    response = session.get(f"{TRACCAR_URL}/api/devices", timeout=20)
    response.raise_for_status()
    matches = [d for d in response.json() if str(d.get("uniqueId")) == TRACCAR_DEVICE_UNIQUE_ID]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one Traccar device for that identifier; found {len(matches)}.")
    device = matches[0]
    if device.get("disabled"):
        raise RuntimeError("The matched Traccar device is disabled.")
    session.traccar_device_id = device["id"]
    session.traccar_device_name = device.get("name") or TRACCAR_DEVICE_UNIQUE_ID
    return session


def logisphere_session(create_demo=False):
    if not LOGISPHERE_SHIPMENT_ID and not create_demo:
        raise RuntimeError("Set LOGISPHERE_SHIPMENT_ID to the shipment UUID to update.")
    session = requests.Session()
    token = LOGISPHERE_TOKEN
    if not token:
        email = os.getenv("LOGISPHERE_EMAIL") or input("LogiSphere email: ").strip()
        password = os.getenv("LOGISPHERE_PASSWORD") or getpass.getpass("LogiSphere password: ")
        response = session.post(
            f"{LOGISPHERE_API}/api/auth/login",
            json={"email": email, "password": password}, timeout=20,
        )
        response.raise_for_status()
        token = response.json().get("token", "")
        if not token:
            raise RuntimeError("LogiSphere login response did not include an application token.")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def mode_fields(mode):
    return {
        "land": {"mode": "road", "transport_mode": "truck"},
        "sea": {"mode": "ocean", "transport_mode": "ship"},
        "air": {"mode": "air", "transport_mode": "plane"},
    }[mode]


def create_demo_shipment(session, mode):
    now = datetime.now(timezone.utc)
    payload = {
        "reference_number": f"TRACCAR-{now.strftime('%Y%m%d-%H%M%S')}",
        "origin": "Kingston, Jamaica",
        "destination": "Montego Bay, Jamaica",
        "status": "in_transit",
        **mode_fields(mode),
        "eta_original": (now + timedelta(hours=2)).isoformat(),
        "eta_current": (now + timedelta(hours=2)).isoformat(),
        "last_event_description": "Phone GPS tracking test started",
        "source_system": "traccar_phone_test",
    }
    response = session.post(f"{LOGISPHERE_API}/api/shipments", json=payload, timeout=30)
    response.raise_for_status()
    shipment_id = response.json().get("id")
    if not shipment_id:
        raise RuntimeError("Created shipment response did not include an ID.")
    return shipment_id


def latest_position(session):
    # The Traccar API requires a time range when deviceId is supplied, so ask
    # for the authorized account's latest positions and select our device.
    response = session.get(f"{TRACCAR_URL}/api/positions", timeout=20)
    response.raise_for_status()
    positions = [p for p in response.json() if p.get("deviceId") == session.traccar_device_id]
    return max(positions, key=lambda p: p.get("serverTime", "")) if positions else None


def telemetry(position, mode):
    data = {
        "latitude": position["latitude"],
        "longitude": position["longitude"],
        "tracking_source": "traccar",
        "transport_mode": mode_fields(mode)["transport_mode"],
    }
    if position.get("altitude") is not None:
        data["current_altitude"] = position["altitude"]
    if position.get("course") is not None:
        data["current_heading"] = position["course"] % 360
    timestamp = position.get("fixTime") or position.get("serverTime")
    if timestamp:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            age_text = f"{max(0, int(age.total_seconds()))} seconds ago"
        except (TypeError, ValueError):
            age_text = "recently"
        data["last_event_description"] = f"Phone GPS reported location {age_text}"
    return data


def main():
    args = parse_args()
    try:
        traccar = traccar_session()
        logisphere = logisphere_session(create_demo=args.create_demo)
        shipment_id = create_demo_shipment(logisphere, args.mode) if args.create_demo else LOGISPHERE_SHIPMENT_ID
        print(f"Following {traccar.traccar_device_name}; updating shipment {shipment_id}.")
        previous_id = None
        while True:
            try:
                position = latest_position(traccar)
                if position is None:
                    print("No position received yet. Check the phone app connection and device identifier.")
                elif position.get("id") != previous_id:
                    if not position.get("valid", True):
                        print("Latest position is marked invalid; waiting for a GPS fix.")
                    else:
                        response = logisphere.post(
                            f"{LOGISPHERE_API}/api/shipments/{shipment_id}/tracking",
                            json=telemetry(position, args.mode), timeout=20,
                        )
                        response.raise_for_status()
                        previous_id = position.get("id")
                        print(f"Updated shipment from {position['latitude']:.6f}, {position['longitude']:.6f} ({position.get('fixTime', 'time unknown')}).")
                if args.once:
                    return 0 if position else 1
            except requests.RequestException as exc:
                print(f"Bridge request failed: {exc}", file=sys.stderr)
                if args.once:
                    return 1
            if args.once:
                return 1
            time.sleep(POLL_SECONDS)
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        print(f"Traccar bridge stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
