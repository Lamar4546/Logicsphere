"""Open mapping lookups kept separate from shipment and agent orchestration."""

import os
from typing import Any

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"


def _headers() -> dict[str, str]:
    """Nominatim requires an identifying, configurable User-Agent."""
    return {"User-Agent": os.getenv("MAP_LOOKUP_USER_AGENT", "LogiSphere/1.0 (operations route lookup)")}


def geocode_place(place: str) -> dict[str, Any] | None:
    """Return a normalized Nominatim point, or None when it cannot be resolved."""
    text = str(place or "").strip()
    if not text:
        return None
    response = requests.get(NOMINATIM_URL, params={"q": text, "format": "jsonv2", "limit": 1}, headers=_headers(), timeout=6)
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    result = results[0]
    return {"latitude": float(result["lat"]), "longitude": float(result["lon"]), "label": result.get("display_name", text)}


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
