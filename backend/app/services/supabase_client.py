"""
Thin wrapper around the Supabase Python client.

Backend uses the SERVICE ROLE key — it bypasses RLS by design, because the
backend itself is the trusted layer that enforces organization scoping in
application code (every query below is explicitly filtered by
organization_id). RLS in schema.sql is the second line of defense for any
direct client-side Supabase access from the frontend.
"""
from supabase import create_client, Client

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
    _client = create_client(url, key)


def get_client() -> Client:
    if _client is None:
        raise RuntimeError(
            "Supabase client not initialized. Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
    return _client
