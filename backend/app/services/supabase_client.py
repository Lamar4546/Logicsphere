"""
Thin wrapper around the Supabase Python client.

Backend uses the SERVICE ROLE key — it bypasses RLS by design, because the
backend itself is the trusted layer that enforces organization scoping in
application code (every query below is explicitly filtered by
organization_id). RLS in schema.sql is the second line of defense for any
direct client-side Supabase access from the frontend.
"""
import logging
from supabase import create_client, Client
import jwt as _jwt

log = logging.getLogger(__name__)

_client: Client | None = None


def init_supabase(app):
    global _client
    url = app.config["SUPABASE_URL"]
    key = app.config["SUPABASE_SERVICE_KEY"]
    if not url or not key:
        # Allow the app to boot without credentials (e.g. for local frontend-only work),
        # but any DB call will raise clearly instead of failing silently.
        _client = None
        return
    # Trim surrounding quotes which sometimes appear in .env files
    if isinstance(url, str):
        url = url.strip().strip('"')
    if isinstance(key, str):
        key = key.strip().strip('"')

    # Basic sanity-check: the SERVICE_KEY should be a supabase service-role JWT.
    # Decode failure and role mismatch are handled separately so a wrong-role
    # key actually stops startup instead of being silently swallowed by a
    # catch-all except.
    try:
        # Decode without verifying signature to inspect claims
        payload = _jwt.decode(key, options={"verify_signature": False})
    except Exception as e:
        log.warning("Could not decode SUPABASE_SERVICE_KEY to inspect role: %s", e)
    else:
        role = payload.get("role")
        if role != "service_role":
            log.error("SUPABASE_SERVICE_KEY does not appear to be a service-role key (role=%s)", role)
            raise RuntimeError("SUPABASE_SERVICE_KEY must be the Supabase service_role key")

    _client = create_client(url, key)


def get_client() -> Client:
    if _client is None:
        raise RuntimeError(
            "Supabase client not initialized. Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
    return _client