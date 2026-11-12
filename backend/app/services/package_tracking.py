"""AfterShip adapter for carrier-level parcel tracking numbers."""

import os
import base64
import hashlib
import hmac
from datetime import datetime, timezone

import requests

from .route_lookup import geocode_place


API_BASE = "https://api.aftership.com/tracking/2026-07"
TRACK17_BASE = "https://api.17track.net/track/v2.4"


class PackageTrackingError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def verify_webhook_signature(raw_body, signature):
    secret = os.getenv("AFTERSHIP_WEBHOOK_SECRET", "").strip()
    if not secret or not signature:
        return False
    expected = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())


def _headers():
    key = os.getenv("AFTERSHIP_API_KEY", "").strip()
    if not key:
        raise PackageTrackingError("Package tracking is not configured. Set AFTERSHIP_API_KEY on the backend.", 503)
    return {"as-api-key": key, "as-api-version": "2026-07", "Content-Type": "application/json"}


def tracking_provider():
    configured = os.getenv("PACKAGE_TRACKING_PROVIDER", "").strip().lower()
    provider = configured or (
        "17track" if os.getenv("SEVENTEEN_TRACK_API_KEY", "").strip()
        else "aftership" if os.getenv("AFTERSHIP_API_KEY", "").strip()
        else "17track"
    )
    if provider not in {"17track", "aftership"}:
        raise PackageTrackingError("PACKAGE_TRACKING_PROVIDER must be 17track or aftership.", 503)
    return provider


def _track17_headers():
    key = os.getenv("SEVENTEEN_TRACK_API_KEY", "").strip()
    if not key:
        raise PackageTrackingError("Package tracking is not configured. Set SEVENTEEN_TRACK_API_KEY on the backend.", 503)
    return {"17token": key, "Content-Type": "application/json"}


def _track17_request(action, payload):
    try:
        response = requests.post(f"{TRACK17_BASE}/{action}", headers=_track17_headers(), json=payload, timeout=25)
    except requests.RequestException as exc:
        raise PackageTrackingError("Could not reach the package tracking provider.") from exc
    if not response.ok:
        if response.status_code == 429:
            raise PackageTrackingError("The package tracking provider is rate-limiting requests. Try again shortly.", 429)
        if response.status_code in (401, 403):
            raise PackageTrackingError("The package tracking provider rejected its API key.", 502)
        raise PackageTrackingError(f"Package tracking provider returned HTTP {response.status_code}.")
    try:
        body = response.json()
    except ValueError as exc:
        raise PackageTrackingError("The package tracking provider returned an invalid response.") from exc
    if body.get("code") not in (0, None):
        raise PackageTrackingError(body.get("message") or "The package tracking provider rejected the request.")
    return body.get("data") or {}


def _tracking_from_response(response):
    try:
        data = response.json().get("data") or {}
        return data.get("tracking") or data
    except (ValueError, AttributeError):
        return {}


def _raise_provider_error(response):
    try:
        body = response.json()
        meta = body.get("meta") or {}
        message = meta.get("message") or meta.get("details")
    except ValueError:
        message = None
    if response.status_code == 401 or response.status_code == 403:
        raise PackageTrackingError("The package tracking provider rejected its API key.", 502)
    if response.status_code == 429:
        raise PackageTrackingError("The package tracking provider is rate-limiting requests. Try again shortly.", 429)
    raise PackageTrackingError(message or f"Package tracking provider returned HTTP {response.status_code}.", 502)


def register_tracking(number, carrier_slug=None):
    if tracking_provider() == "17track":
        request_item = {"number": number.strip()}
        if carrier_slug:
            try:
                request_item["carrier"] = int(carrier_slug)
            except (TypeError, ValueError) as exc:
                raise PackageTrackingError("17TRACK carrier must be a numeric carrier code.", 400) from exc
        data = _track17_request("register", [request_item])
        accepted = data.get("accepted") or []
        rejected = data.get("rejected") or []
        if not accepted:
            message = ((rejected[0].get("error") or {}).get("message") if rejected else None)
            raise PackageTrackingError(message or "17TRACK did not accept this tracking number.", 400)
        item = accepted[0]
        carrier_code = item.get("carrier")
        tracking_ref = f"{number.strip()}::{carrier_code}" if carrier_code else number.strip()
        return {"id": tracking_ref, "tracking_number": number.strip(), "tracking_provider": "17track", "carrier_code": carrier_code}
    payload = {"tracking_number": number.strip()}
    if carrier_slug:
        payload["slug"] = carrier_slug.strip().lower()
    try:
        response = requests.post(f"{API_BASE}/trackings", headers=_headers(), json=payload, timeout=25)
    except requests.RequestException as exc:
        raise PackageTrackingError("Could not reach the package tracking provider.") from exc
    if not response.ok:
        _raise_provider_error(response)
    tracking = _tracking_from_response(response)
    if not tracking.get("id"):
        raise PackageTrackingError("The provider accepted the tracking number but did not return a tracking ID.")
    return tracking


def fetch_tracking(provider_tracking_id, provider=None):
    provider = provider or tracking_provider()
    if provider == "17track":
        tracking_number = str(provider_tracking_id)
        carrier_code = None
        if "::" in tracking_number:
            tracking_number, carrier_code = tracking_number.rsplit("::", 1)
        request_item = {"number": tracking_number}
        if carrier_code:
            try:
                request_item["carrier"] = int(carrier_code)
            except ValueError:
                pass
        data = _track17_request("gettrackinfo", [request_item])
        accepted = data.get("accepted") or []
        if not accepted:
            rejected = data.get("rejected") or []
            message = ((rejected[0].get("error") or {}).get("message") if rejected else None)
            raise PackageTrackingError(message or "17TRACK has not received a carrier scan yet.", 404)
        item = accepted[0]
        item["tracking_provider"] = "17track"
        return item
    try:
        response = requests.get(
            f"{API_BASE}/trackings/{provider_tracking_id}",
            headers=_headers(), params={"fields": "checkpoints"}, timeout=25,
        )
    except requests.RequestException as exc:
        raise PackageTrackingError("Could not reach the package tracking provider.") from exc
    if not response.ok:
        _raise_provider_error(response)
    tracking = _tracking_from_response(response)
    if not tracking:
        raise PackageTrackingError("The provider returned an empty tracking record.")
    return tracking


def _eta_fields(value, prefix):
    if not value:
        return {f"{prefix}_at": None, f"{prefix}_date": None}
    text = str(value)
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return {f"{prefix}_at": None, f"{prefix}_date": text}
    return {f"{prefix}_at": text, f"{prefix}_date": None}


def _eta_timestamp(value):
    if not value:
        return None
    text = str(value)
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        # Store a date-only ETA at the end of that date for delay evaluation;
        # the separate date field preserves that no clock time was supplied.
        return f"{text}T23:59:59+00:00"
    return text


def _latest_checkpoint(tracking):
    checkpoints = tracking.get("checkpoints") or []
    if not checkpoints:
        return None

    def checkpoint_time(item):
        value = str(item.get("checkpoint_time") or item.get("created_at") or "")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            return 0

    return max(checkpoints, key=checkpoint_time)


def normalize_tracking(tracking, fallback_origin=None, fallback_destination=None):
    """Convert an AfterShip tracking record to shipment database fields."""
    if tracking.get("tracking_provider") == "17track" or "track_info" in tracking:
        return _normalize_17track(tracking, fallback_origin, fallback_destination)
    checkpoint = _latest_checkpoint(tracking)
    carrier_edd = tracking.get("courier_estimated_delivery_date") or {}
    ai_edd = tracking.get("aftership_estimated_delivery_date") or {}
    latest_edd = tracking.get("latest_estimated_delivery") or {}
    carrier_eta_value = carrier_edd.get("estimated_delivery_date")
    ai_eta_value = ai_edd.get("estimated_delivery_date")
    eta = _eta_timestamp(latest_edd.get("datetime") or ai_eta_value or carrier_eta_value)

    tag = str(tracking.get("tag") or (checkpoint or {}).get("tag") or "Pending")
    status = {
        "Delivered": "delivered",
        "Exception": "exception",
        "AttemptFail": "exception",
        "Expired": "exception",
        "InTransit": "in_transit",
        "OutForDelivery": "in_transit",
        "AvailableForPickup": "in_transit",
        "InfoReceived": "planned",
        "Pending": "planned",
    }.get(tag, "in_transit")

    location = None
    latitude = longitude = None
    if checkpoint:
        location = checkpoint.get("location") or ", ".join(
            str(value) for value in (checkpoint.get("city"), checkpoint.get("state"), checkpoint.get("country_region_name")) if value
        ) or None
        coordinate = checkpoint.get("coordinate") or {}
        try:
            latitude, longitude = float(coordinate["latitude"]), float(coordinate["longitude"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                latitude = longitude = None
        except (KeyError, TypeError, ValueError):
            latitude = longitude = None
        if location and latitude is None:
            try:
                point = geocode_place(location)
                if point:
                    latitude, longitude = point["latitude"], point["longitude"]
            except requests.RequestException:
                # A carrier event remains useful even if the optional map
                # geocode service is temporarily unavailable.
                pass

    destination = (
        fallback_destination
        or tracking.get("destination_raw_location")
        or ", ".join(str(value) for value in (
            tracking.get("destination_city"), tracking.get("destination_state"),
            tracking.get("destination_country_region"),
        ) if value)
        or None
    )
    origin = (
        fallback_origin
        or tracking.get("origin_raw_location")
        or ", ".join(str(value) for value in (
            tracking.get("origin_city"), tracking.get("origin_state"),
            tracking.get("origin_country_region"),
        ) if value)
        or None
    )
    if checkpoint:
        event_description = checkpoint.get("message") or checkpoint.get("subtag_message") or tracking.get("subtag_message")
        event_at = checkpoint.get("checkpoint_time") or checkpoint.get("created_at")
    else:
        event_description = tracking.get("subtag_message") or tag
        event_at = tracking.get("updated_at")

    changes = {
        "tracking_number": tracking.get("tracking_number"),
        "tracking_provider": "aftership",
        "provider_tracking_id": tracking.get("id"),
        "tracking_carrier": tracking.get("courier_name") or tracking.get("slug"),
        "tracking_status": tag,
        "tracking_location": location,
        "tracking_events": tracking.get("checkpoints") or [],
        **_eta_fields(carrier_eta_value, "carrier_eta"),
        **_eta_fields(ai_eta_value, "ai_eta"),
        "ai_eta_source": "aftership_ai" if ai_eta_value else ("carrier" if carrier_eta_value else None),
        "eta_current": eta,
        "status": status,
        "tracking_source": "aftership",
    }
    if origin:
        changes["origin"] = origin
    if destination:
        changes["destination"] = destination
        try:
            point = geocode_place(destination)
            if point:
                changes["destination_latitude"] = point["latitude"]
                changes["destination_longitude"] = point["longitude"]
        except requests.RequestException:
            pass
    if event_description:
        changes["last_event_description"] = event_description
    if event_at:
        changes["last_event_at"] = event_at
    if location:
        changes["current_latitude"] = latitude
        changes["current_longitude"] = longitude
    return changes


def _normalize_17track(record, fallback_origin=None, fallback_destination=None):
    info = record.get("track_info") or {}
    latest = info.get("latest_event") or {}
    latest_status = info.get("latest_status") or {}
    metrics = info.get("time_metrics") or {}
    estimate = metrics.get("estimated_delivery_date") or {}
    providers = (info.get("tracking") or {}).get("providers") or []
    provider_info = next((item.get("provider") or {} for item in providers if item.get("provider")), {})
    events = []
    for provider in providers:
        for event in provider.get("events") or []:
            translated = event.get("description_translation") or {}
            events.append({
                "time_iso": event.get("time_iso"), "time_utc": event.get("time_utc"),
                "description": translated.get("description") if isinstance(translated, dict) else None,
                "message": (translated.get("description") if isinstance(translated, dict) else None) or event.get("description"),
                "location": event.get("location"), "stage": event.get("stage"),
                "sub_status": event.get("sub_status"), "address": event.get("address") or {},
            })
    if latest and not events:
        translated = latest.get("description_translation") or {}
        events.append({
            "time_iso": latest.get("time_iso"), "time_utc": latest.get("time_utc"),
            "description": translated.get("description") if isinstance(translated, dict) else None,
            "message": (translated.get("description") if isinstance(translated, dict) else None) or latest.get("description"),
            "location": latest.get("location"), "stage": latest.get("stage"),
            "sub_status": latest.get("sub_status"), "address": latest.get("address") or {},
        })
    events.sort(key=lambda item: item.get("time_utc") or item.get("time_iso") or "", reverse=True)
    raw_eta = estimate.get("to") or estimate.get("from")
    eta = _eta_timestamp(raw_eta)
    tag = latest_status.get("status") or record.get("tag") or "Pending"
    status = {
        "Delivered": "delivered", "Returning": "at_risk", "Returned": "exception",
        "Exception": "exception", "DeliveryFailure": "exception", "Expired": "exception",
        "InTransit": "in_transit", "OutForDelivery": "in_transit", "AvailableForPickup": "in_transit",
        "PickedUp": "in_transit", "InfoReceived": "planned", "Pending": "planned", "NotFound": "planned",
    }.get(tag, "in_transit")
    location = latest.get("location")
    coordinates = ((latest.get("address") or {}).get("coordinates") or {})
    latitude = longitude = None
    try:
        latitude, longitude = float(coordinates["latitude"]), float(coordinates["longitude"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            latitude = longitude = None
    except (KeyError, TypeError, ValueError):
        latitude = longitude = None
    if location and latitude is None:
        try:
            point = geocode_place(location)
            if point:
                latitude, longitude = point["latitude"], point["longitude"]
        except requests.RequestException:
            pass
    address_info = (info.get("shipping_info") or {})
    origin_address = address_info.get("shipper_address") or {}
    destination_address = address_info.get("recipient_address") or {}
    origin = fallback_origin or ", ".join(str(origin_address.get(key)) for key in ("city", "state", "country") if origin_address.get(key)) or None
    destination = fallback_destination or ", ".join(str(destination_address.get(key)) for key in ("city", "state", "country") if destination_address.get(key)) or None
    source = estimate.get("source")
    estimate_fields = {
        **_eta_fields(None, "carrier_eta"), **_eta_fields(None, "ai_eta"),
        **(_eta_fields(raw_eta, "carrier_eta" if source == "Official" else "ai_eta") if raw_eta else {}),
    }
    number = record.get("number") or record.get("tracking_number")
    carrier_code = record.get("carrier") or record.get("carrier_code")
    tracking_ref = f"{number}::{carrier_code}" if carrier_code else number
    change = {
        "tracking_number": number, "tracking_provider": "17track",
        "provider_tracking_id": tracking_ref, "tracking_carrier": provider_info.get("name") or str(carrier_code or "17TRACK"),
        "tracking_status": tag, "tracking_location": location, "tracking_events": events,
        **estimate_fields,
        "ai_eta_source": "17track_estimate" if eta and source != "Official" else ("carrier" if eta else None),
        "eta_current": eta, "status": status, "tracking_source": "17track",
    }
    if origin: change["origin"] = origin
    if destination:
        change["destination"] = destination
        try:
            point = geocode_place(destination)
            if point:
                change["destination_latitude"] = point["latitude"]
                change["destination_longitude"] = point["longitude"]
        except requests.RequestException:
            pass
    if latitude is not None:
        change["current_latitude"], change["current_longitude"] = latitude, longitude
    if latest.get("description"):
        translation = latest.get("description_translation") or {}
        change["last_event_description"] = (translation.get("description") if isinstance(translation, dict) else None) or latest.get("description")
    if latest.get("time_utc") or latest.get("time_iso"):
        change["last_event_at"] = latest.get("time_utc") or latest.get("time_iso")
    return change


def verify_17track_webhook(raw_body, signature):
    key = os.getenv("SEVENTEEN_TRACK_API_KEY", "").strip()
    if not key or not signature:
        return False
    expected = hashlib.sha256(raw_body + b"/" + key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, signature.strip())
