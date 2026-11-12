"""Send live land, vessel, or aircraft positions to a configured shipment.

Configure the shipment's live tracking ID in LogiSphere, then run one bridge
process for that shipment. Provider credentials stay server-side.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import getpass
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv("backend/.env")

LOGISPHERE_API = os.getenv("LOGISPHERE_API", "http://localhost:5000").rstrip("/")
SHIPMENT_ID = os.getenv("LOGISPHERE_SHIPMENT_ID", "").strip()
POLL_SECONDS = max(5, int(os.getenv("MULTIMODAL_POLL_SECONDS", "10")))
OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
OPENSKY_API = "https://opensky-network.org/api"
AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shipment-id", default=SHIPMENT_ID, help="LogiSphere shipment UUID (or LOGISPHERE_SHIPMENT_ID)")
    parser.add_argument("--mode", choices=("land", "sea", "air"), help="Validate the configured shipment mode")
    parser.add_argument("--once", action="store_true", help="send one current fix when the provider supports polling")
    return parser.parse_args()


def logisphere_session():
    session = requests.Session()
    token = os.getenv("LOGISPHERE_TOKEN", "").strip()
    if not token:
        email = os.getenv("LOGISPHERE_EMAIL") or input("LogiSphere email: ").strip()
        password = os.getenv("LOGISPHERE_PASSWORD") or getpass.getpass("LogiSphere password: ")
        response = session.post(f"{LOGISPHERE_API}/api/auth/login", json={"email": email, "password": password}, timeout=20)
        response.raise_for_status()
        token = response.json().get("token", "")
    if not token:
        raise RuntimeError("LogiSphere login did not return an access token.")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def get_shipment(session, shipment_id):
    response = session.get(f"{LOGISPHERE_API}/api/shipments", timeout=20)
    response.raise_for_status()
    shipment = next((row for row in response.json() if str(row.get("id")) == shipment_id), None)
    if not shipment:
        raise RuntimeError("Shipment not found in this LogiSphere account.")
    if shipment.get("status") in {"delivered", "cancelled"}:
        raise RuntimeError("Shipment is already delivered or cancelled.")
    mode = shipment.get("transport_mode") or {"road": "truck", "ocean": "ship", "air": "plane"}.get(shipment.get("mode"))
    live_id = str(shipment.get("live_tracking_id") or "").strip()
    if not mode or mode not in {"truck", "ship", "plane"} or not live_id:
        raise RuntimeError("Set the shipment mode and its live provider ID in the shipment map's Configure live location source section.")
    if shipment.get("tracking_number") and not shipment.get("tracking_provider"):
        print("Note: no parcel tracking provider is registered; position updates can still appear on the map.", file=sys.stderr)
    return shipment, mode, live_id


def push_position(session, shipment_id, mode, latitude, longitude, *, heading=None, altitude=None, event="Live position update", source):
    payload = {
        "latitude": latitude, "longitude": longitude,
        "transport_mode": mode, "tracking_source": source,
        "last_event_description": event,
    }
    if heading is not None:
        heading = float(heading)
        if 0 <= heading < 360:
            payload["current_heading"] = heading
    if altitude is not None:
        payload["current_altitude"] = altitude
    response = session.post(f"{LOGISPHERE_API}/api/shipments/{shipment_id}/tracking", json=payload, timeout=20)
    response.raise_for_status()
    print(f"Updated {mode} position {latitude:.5f}, {longitude:.5f} ({source}).")


def traccar_session():
    base = os.getenv("TRACCAR_URL", "http://localhost:8082").rstrip("/")
    session = requests.Session()
    session.headers["Accept"] = "application/json"
    token = os.getenv("TRACCAR_TOKEN", "").strip()
    username = os.getenv("TRACCAR_USERNAME", "").strip()
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    elif username:
        session.auth = (username, os.getenv("TRACCAR_PASSWORD") or getpass.getpass("Traccar password: "))
    else:
        session.auth = (input("Traccar username: ").strip(), getpass.getpass("Traccar password: "))
    response = session.get(f"{base}/api/devices", timeout=20)
    response.raise_for_status()
    return base, session


def traccar_device(provider_session, base, unique_id):
    response = provider_session.get(f"{base}/api/devices", timeout=20)
    response.raise_for_status()
    device = next((d for d in response.json() if str(d.get("uniqueId")) == unique_id), None)
    if not device:
        raise RuntimeError(f"Traccar has no device with unique ID {unique_id!r}.")
    return device["id"]


def traccar_fix(provider_session, base, device_id):
    positions = provider_session.get(f"{base}/api/positions", timeout=20)
    positions.raise_for_status()
    rows = [p for p in positions.json() if p.get("deviceId") == device_id and p.get("valid", True)]
    return max(rows, key=lambda p: p.get("serverTime", "")) if rows else None


class OpenSkyAuth:
    def __init__(self):
        self.client_id = os.getenv("OPENSKY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("OPENSKY_CLIENT_SECRET", "").strip()
        self.token = None
        self.expires_at = 0
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Set OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET for the OpenSky air source.")

    def headers(self, force_refresh=False):
        if force_refresh or not self.token or time.time() >= self.expires_at - 30:
            response = requests.post(OPENSKY_TOKEN_URL, data={
                "grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret,
            }, timeout=20)
            response.raise_for_status()
            result = response.json()
            self.token = result.get("access_token")
            self.expires_at = time.time() + int(result.get("expires_in", 1800))
            if not self.token:
                raise RuntimeError("OpenSky did not return an access token.")
        return {"Authorization": f"Bearer {self.token}"}


def opensky_fix(icao24, auth):
    response = requests.get(f"{OPENSKY_API}/states/all", params={"icao24": icao24.lower()},
                            headers=auth.headers(), timeout=20)
    if response.status_code == 401:
        response = requests.get(f"{OPENSKY_API}/states/all", params={"icao24": icao24.lower()},
                                headers=auth.headers(force_refresh=True), timeout=20)
    response.raise_for_status()
    states = response.json().get("states") or []
    if not states:
        return None
    # OpenSky StateVector field order: icao24, callsign, ..., lon, lat,
    # baro_altitude, on_ground, velocity, true_track, vertical_rate, ..., geo_altitude.
    state = states[0]
    if state[5] is None or state[6] is None:
        return None
    return {
        "longitude": state[5], "latitude": state[6],
        "altitude": state[13] if len(state) > 13 and state[13] is not None else state[7],
        "heading": state[10], "callsign": (state[1] or "").strip(), "on_ground": bool(state[8]),
        "timestamp": state[3] or state[4],
    }


async def run_sea(session, shipment_id, mmsi, once=False):
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Install backend requirements to use the AISStream WebSocket client.") from exc
    key = os.getenv("AISSTREAM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set AISSTREAM_API_KEY for the AISStream sea source.")
    bbox = json.loads(os.getenv("AISSTREAM_BBOX_JSON", "[[[-90,-180],[90,180]]]"))
    subscription = {"APIKey": key, "BoundingBoxes": bbox, "FiltersShipMMSI": [mmsi], "FilterMessageTypes": ["PositionReport"]}
    delay = 2
    while True:
        try:
            async with websockets.connect(AISSTREAM_URL, compression="deflate", ping_interval=20, ping_timeout=20) as socket:
                await socket.send(json.dumps(subscription))
                delay = 2
                while True:
                    raw = await asyncio.wait_for(socket.recv(), timeout=120)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    message = json.loads(raw)
                    metadata = message.get("MetaData") or {}
                    if str(metadata.get("MMSI") or "") != mmsi or message.get("MessageType") != "PositionReport":
                        continue
                    report = (message.get("Message") or {}).get("PositionReport") or {}
                    latitude = metadata.get("Latitude") if metadata.get("Latitude") is not None else report.get("Latitude")
                    longitude = metadata.get("Longitude") if metadata.get("Longitude") is not None else report.get("Longitude")
                    if latitude is None or longitude is None or report.get("Valid") is False:
                        continue
                    name = str(metadata.get("ShipName") or "Vessel").strip()
                    speed = report.get("Sog")
                    heading = report.get("TrueHeading")
                    if heading is None or not 0 <= heading < 360:
                        heading = report.get("Cog")
                    event = f"AIS position: {name}" + (f" · {speed} knots" if speed is not None else "")
                    push_position(session, shipment_id, "ship", float(latitude), float(longitude),
                                  heading=report.get("TrueHeading") or report.get("Cog"), event=event, source="aisstream")
                    if once:
                        return
        except Exception as exc:
            if once:
                raise
            print(f"AISStream disconnected: {exc}; reconnecting in {delay}s", file=sys.stderr)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


def main():
    args = parse_args()
    if not args.shipment_id:
        raise RuntimeError("Set LOGISPHERE_SHIPMENT_ID or pass --shipment-id.")
    app_session = logisphere_session()
    shipment, mode, live_id = get_shipment(app_session, args.shipment_id)
    selected = {"truck": "land", "ship": "sea", "plane": "air"}[mode]
    if args.mode and args.mode != selected:
        raise RuntimeError(f"This shipment is configured for {selected}, not {args.mode}.")
    print(f"Following {selected} identifier {live_id} for shipment {shipment.get('reference_number')}.")
    if selected == "sea":
        asyncio.run(run_sea(app_session, args.shipment_id, live_id, args.once))
        return 0

    if selected == "land":
        base, provider_session = traccar_session()
        provider = "traccar"
        auth = None
    else:
        base, provider_session, provider = None, None, "opensky"
        auth = OpenSkyAuth()
    device_id = traccar_device(provider_session, base, live_id) if selected == "land" else None
    previous = None
    while True:
        if selected == "land":
            fix = traccar_fix(provider_session, base, device_id)
            if fix:
                timestamp = fix.get("fixTime") or fix.get("serverTime")
                fix_id = fix.get("id")
                event = f"Traccar GPS position received ({timestamp or 'time unavailable'})"
                values = (fix_id, float(fix["latitude"]), float(fix["longitude"]))
                if values != previous:
                    push_position(app_session, args.shipment_id, "truck", values[1], values[2], heading=fix.get("course"), altitude=fix.get("altitude"), event=event, source=provider)
                    previous = values
        else:
            fix = opensky_fix(live_id, auth)
            if fix:
                when = datetime.fromtimestamp(fix["timestamp"], timezone.utc).isoformat() if fix.get("timestamp") else "time unavailable"
                state = "on ground" if fix["on_ground"] else "airborne"
                event = f"OpenSky ADS-B position · {fix['callsign'] or live_id} · {state} · {when}"
                values = (fix["latitude"], fix["longitude"], fix["heading"])
                if values != previous:
                    push_position(app_session, args.shipment_id, "plane", fix["latitude"], fix["longitude"], heading=fix["heading"], altitude=fix["altitude"], event=event, source=provider)
                    previous = values
        if args.once:
            return 0 if previous else 1
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (requests.RequestException, RuntimeError, ValueError, KeyError, TimeoutError) as exc:
        print(f"Multimodal tracking bridge stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
