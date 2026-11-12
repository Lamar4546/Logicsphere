"""Simulate truck and sea GPS updates against the LogiSphere tracking API.

Examples:
    python simulate_tracking.py --mode both --create-demo --speed 3600 --delay-at 0.5 --evaluate-on-delay
    python simulate_tracking.py --mode truck --speed 600 --delay-at 0.5 --evaluate-on-delay

When --create-demo is omitted, set TRUCK_SHIPMENT_ID and/or SEA_SHIPMENT_ID
to shipment UUIDs owned by the signed-in organization.
"""

import argparse
from datetime import datetime, timedelta, timezone
import getpass
import math
import os
import random
import sys
import time

import requests


API_URL = os.getenv("LOGISPHERE_API", "http://localhost:5000").rstrip("/")
TOKEN = os.getenv("LOGISPHERE_TOKEN", "").strip()

ROUTES = {
    "truck": {
        "env_key": "TRUCK_SHIPMENT_ID",
        "waypoints": [
            (17.9712, -76.7936),
            (18.0179, -77.2000),
            (18.1000, -77.5500),
            (18.4762, -77.8939),
        ],
        "total_minutes": 240,
        "transport_mode": "truck",
        "database_mode": "road",
        "origin": "Kingston, Jamaica",
        "destination": "Montego Bay, Jamaica",
    },
    "sea": {
        "env_key": "SEA_SHIPMENT_ID",
        "waypoints": [
            (17.9600, -76.8000),
            (17.2000, -75.0000),
            (14.0000, -68.0000),
            (10.6600, -61.5100),
        ],
        "total_minutes": 2880,
        "transport_mode": "ship",
        "database_mode": "ocean",
        "origin": "Kingston, Jamaica",
        "destination": "Port of Spain, Trinidad and Tobago",
    },
}


def lerp_route(points, progress):
    """Interpolate a point along a polyline, weighted by segment length."""
    progress = max(0.0, min(float(progress), 1.0))
    segment_lengths = [
        math.dist(points[i], points[i + 1])
        for i in range(len(points) - 1)
    ]
    total_length = sum(segment_lengths)
    if total_length == 0:
        return points[0]

    target = progress * total_length
    for i, segment_length in enumerate(segment_lengths):
        if target <= segment_length or i == len(segment_lengths) - 1:
            fraction = 0.0 if segment_length == 0 else min(target / segment_length, 1.0)
            start, end = points[i], points[i + 1]
            return (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
        target -= segment_length
    return points[-1]


def parse_datetime(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def authenticate(session):
    token = TOKEN
    if not token:
        email = os.getenv("LOGISPHERE_EMAIL") or input("LogiSphere email: ").strip()
        password = os.getenv("LOGISPHERE_PASSWORD") or getpass.getpass(
            "LogiSphere password: "
        )
        response = session.post(
            f"{API_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(
                f"Login failed ({response.status_code}): {response.text[:500]}"
            )
        token = response.json().get("token", "")
        if not token:
            raise RuntimeError("Login response did not include an application token.")

    session.headers.update({"Authorization": f"Bearer {token}"})
    response = session.get(f"{API_URL}/api/shipments", timeout=20)
    if not response.ok:
        raise RuntimeError(
            f"Could not list shipments ({response.status_code}): {response.text[:500]}"
        )
    return response.json()


def create_demo_shipment(session, route_name, route):
    now = datetime.now(timezone.utc)
    arrival = now + timedelta(minutes=route["total_minutes"])
    reference = f"SIM-{route_name.upper()}-{now.strftime('%Y%m%d-%H%M%S')}-{random.randrange(1000, 9999)}"
    payload = {
        "reference_number": reference,
        "origin": route["origin"],
        "destination": route["destination"],
        "status": "in_transit",
        "mode": route["database_mode"],
        "transport_mode": route["transport_mode"],
        "eta_original": arrival.isoformat(),
        "eta_current": arrival.isoformat(),
        "current_latitude": route["waypoints"][0][0],
        "current_longitude": route["waypoints"][0][1],
        "last_event_description": "Tracking simulation started",
        "source_system": "tracking_simulator",
    }
    response = session.post(
        f"{API_URL}/api/shipments", json=payload, timeout=30
    )
    if not response.ok:
        raise RuntimeError(
            f"Could not create {route_name} demo shipment "
            f"({response.status_code}): {response.text[:500]}"
        )
    shipment = response.json()
    shipment_id = shipment.get("id")
    if not shipment_id:
        raise RuntimeError(f"Create shipment response had no id: {shipment}")
    print(f"Created {route_name} demo shipment {reference} ({shipment_id})")
    return shipment


def resolve_shipments(session, shipment_list, mode, create_demo):
    selected_modes = ["truck", "sea"] if mode == "both" else [mode]
    by_id = {str(row.get("id")): row for row in shipment_list}
    resolved = {}

    for route_name in selected_modes:
        route = ROUTES[route_name]
        if create_demo:
            shipment = create_demo_shipment(session, route_name, route)
        else:
            shipment_id = os.getenv(route["env_key"], "").strip()
            if not shipment_id:
                raise RuntimeError(
                    f"Set {route['env_key']} to an existing shipment UUID, "
                    "or pass --create-demo."
                )
            shipment = by_id.get(shipment_id)
            if shipment is None:
                raise RuntimeError(
                    f"{route['env_key']}={shipment_id} was not returned by "
                    "GET /api/shipments for this account. Check the UUID and organization."
                )
        if not shipment.get("eta_original"):
            raise RuntimeError(
                f"Shipment {shipment.get('reference_number', shipment.get('id'))} "
                "has no original ETA. Create a demo shipment or add eta_original "
                "to the shipment before simulating a delay."
            )
        route["shipment_id"] = str(shipment["id"])
        route["eta_original"] = parse_datetime(shipment["eta_original"])
        resolved[route_name] = route
    return resolved


def push_update(session, route, lat, lng, progress, eta_current, event):
    payload = {
        "latitude": lat,
        "longitude": lng,
        "transport_mode": route["transport_mode"],
        "tracking_source": "tracking_simulator",
        "eta_current": eta_current.isoformat(),
        "last_event_description": event,
    }
    response = session.post(
        f"{API_URL}/api/shipments/{route['shipment_id']}/tracking",
        json=payload,
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(
            f"Tracking update failed for {route['shipment_id']} "
            f"({response.status_code}): {response.text[:500]}"
        )
    print(
        f"[{route['shipment_id']}] {route['transport_mode']:<5} "
        f"{progress:5.1%} ({lat:.4f}, {lng:.4f}) -> {response.status_code}"
    )


def evaluate_shipment(session, route):
    response = session.post(
        f"{API_URL}/api/shipments/{route['shipment_id']}/evaluate",
        json={},
        timeout=40,
    )
    if not response.ok:
        raise RuntimeError(
            f"Shipment evaluation failed for {route['shipment_id']} "
            f"({response.status_code}): {response.text[:500]}"
        )
    result = response.json()
    print(f"[{route['shipment_id']}] evaluation: {result}")


def run(args):
    session = requests.Session()
    shipment_list = authenticate(session)
    routes = resolve_shipments(
        session, shipment_list, args.mode, args.create_demo
    )
    state = {
        name: {"sim_minutes": 0.0, "delayed": False, "done": False}
        for name in routes
    }

    for name, route in routes.items():
        lat, lng = route["waypoints"][0]
        push_update(
            session,
            route,
            lat,
            lng,
            0.0,
            route["eta_original"],
            "Tracking simulation dispatched",
        )

    while not all(item["done"] for item in state.values()):
        time.sleep(args.tick)
        for name, route in routes.items():
            item = state[name]
            if item["done"]:
                continue

            slowdown = 0.3 if item["delayed"] else 1.0
            item["sim_minutes"] += args.tick * args.speed / 60.0 * slowdown
            progress = min(
                item["sim_minutes"] / route["total_minutes"], 1.0
            )
            lat, lng = lerp_route(route["waypoints"], progress)
            if progress < 1.0:
                lat += random.uniform(-0.0004, 0.0004)
                lng += random.uniform(-0.0004, 0.0004)

            if (
                args.delay_at is not None
                and not item["delayed"]
                and progress >= args.delay_at
            ):
                item["delayed"] = True
                eta_current = route["eta_original"] + timedelta(
                    hours=args.delay_hours
                )
                reason = (
                    "Simulator delay: road traffic"
                    if name == "truck"
                    else "Simulator delay: vessel slowed"
                )
                push_update(
                    session, route, lat, lng, progress, eta_current, reason
                )
                if args.evaluate_on_delay:
                    evaluate_shipment(session, route)
                continue

            eta_current = route["eta_original"]
            if item["delayed"]:
                eta_current += timedelta(hours=args.delay_hours)
            if progress >= 1.0:
                item["done"] = True
                event = "Tracking simulation reached final waypoint"
            else:
                event = f"Tracking simulation position {progress:.0%}"
            push_update(
                session, route, lat, lng, progress, eta_current, event
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send simulated truck/ship coordinates to the LogiSphere tracking API."
    )
    parser.add_argument(
        "--mode", choices=["truck", "sea", "both"], default="both"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=3600,
        help="simulation time multiplier; 3600 is a short demo run",
    )
    parser.add_argument(
        "--tick", type=float, default=2, help="seconds between API updates"
    )
    parser.add_argument(
        "--delay-at",
        type=float,
        default=None,
        help="progress from 0 to 1 at which to inject a delay",
    )
    parser.add_argument(
        "--delay-hours",
        type=float,
        default=3,
        help="ETA delay to inject; 3 hours reaches the current low-risk threshold",
    )
    parser.add_argument(
        "--create-demo",
        action="store_true",
        help="create fresh shipment records through the authenticated API",
    )
    parser.add_argument(
        "--evaluate-on-delay",
        action="store_true",
        help="run the shipment risk workflow after injecting the delay",
    )
    args = parser.parse_args()
    if args.speed <= 0:
        parser.error("--speed must be greater than zero")
    if args.tick <= 0:
        parser.error("--tick must be greater than zero")
    if args.delay_at is not None and not 0 <= args.delay_at <= 1:
        parser.error("--delay-at must be between 0 and 1")
    if args.delay_hours <= 0:
        parser.error("--delay-hours must be greater than zero")
    return args


if __name__ == "__main__":
    try:
        run(parse_args())
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"Simulation stopped: {exc}", file=sys.stderr)
        sys.exit(1)
