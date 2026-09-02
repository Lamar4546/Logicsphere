"""Open mapping lookups kept separate from shipment and agent orchestration."""

import os
import time
from typing import Any

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
GEOCODE_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7
_geocode_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_last_geocode_request_at = 0.0


def _headers() -> dict[str, str]:
    """Nominatim requires an identifying, configurable User-Agent."""
    return {"User-Agent": os.getenv("MAP_LOOKUP_USER_AGENT", "LogiSphere/1.0 (operations route lookup)")}


def geocode_place(place: str) -> dict[str, Any] | None:
    """Return a normalized Nominatim point, or None when it cannot be resolved."""
    text = str(place or "").strip()
    if not text:
        return None
    cache_key = text.casefold()
    cached = _geocode_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < GEOCODE_CACHE_TTL_SECONDS:
        return cached[1]

    # The public Nominatim service asks clients to stay at or below 1 request
    # per second. This prevents UI selection/polling from causing a 429.
    global _last_geocode_request_at
    remaining = 1.05 - (time.monotonic() - _last_geocode_request_at)
    if remaining > 0:
        time.sleep(remaining)
    response = requests.get(NOMINATIM_URL, params={"q": text, "format": "jsonv2", "limit": 1}, headers=_headers(), timeout=8)
    _last_geocode_request_at = time.monotonic()
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    result = results[0]
    point = {"latitude": float(result["lat"]), "longitude": float(result["lon"]), "label": result.get("display_name", text)}
    _geocode_cache[cache_key] = (time.monotonic(), point)
    return point


def route_between(origin: str, destination: str) -> dict[str, Any] | None:
    """Geocode two place names and calculate their OSRM driving route.

    This service performs no database writes and can be mocked independently.
    """
    start = geocode_place(origin)
    end = geocode_place(destination)
    if not start or not end:
        return None
    coordinates = f"{start['longitude']},{start['latitude']};{end['longitude']},{end['latitude']}"
    response = requests.get(f"{OSRM_URL}/{coordinates}", params={"overview": "full", "geometries": "geojson", "steps": "false"}, headers=_headers(), timeout=8)
    response.raise_for_status()
    routes = response.json().get("routes") or []
    if not routes:
        return None
    route = routes[0]
    return {
        "origin_latitude": start["latitude"], "origin_longitude": start["longitude"],
        "destination_latitude": end["latitude"], "destination_longitude": end["longitude"],
        "route_geometry": route.get("geometry"),
        "route_distance_meters": round(float(route.get("distance") or 0)),
        "route_duration_seconds": round(float(route.get("duration") or 0)),
        "route_lookup_status": "ready",
    }
