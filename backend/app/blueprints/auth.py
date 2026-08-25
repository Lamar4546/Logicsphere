import logging

from flask import Blueprint, g, jsonify, request

from ..services.jwt import create_access_token, login_required
from ..services.supabase_client import get_client
from postgrest.exceptions import APIError

auth_bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


@auth_bp.post("/register")
def register():
    payload = request.get_json(force=True) or {}
    company_name = payload.get("company_name")
    email = payload.get("email")
    password = payload.get("password")
    full_name = payload.get("full_name") or company_name
    industry = payload.get("industry")
    country = payload.get("country")

    if not company_name or not email or not password:
        return jsonify({"error": "company_name, email, and password are required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    email = email.strip().lower()
    db = get_client()

    # ------------------------------------
    # 1. Create the Supabase Auth user first — this is now the
    #    single source of truth for identity/password.
    # ------------------------------------
    try:
        created = db.auth.admin.create_user({
            "email": email,
            "password": password,
            "user_metadata": {"full_name": full_name},
            "email_confirm": True,
        })
        # created is a UserResponse model; extract id
        auth_user = getattr(created, "user", None)
        user_id = None
        if auth_user:
            user_id = getattr(auth_user, "id", None)
        if not user_id and isinstance(created, dict):
            user_id = (created.get("user") or {}).get("id") or created.get("id")
        if not user_id:
            raise RuntimeError("Could not extract user id from create_user response")
    except Exception as e:
        # If the user already exists, return a 409 so the frontend can tell the user
        msg = str(e)
        log.exception("Supabase signup failed")
        if "User already registered" in msg or "already exists" in msg:
            return jsonify({"error": "User already exists"}), 409
        return jsonify({"error": "Failed to create account", "details": msg}), 500

    # ------------------------------------
    # 2. Create the organization
    # ------------------------------------
    org_payload = {"name": company_name}
    if industry:
        org_payload["industry"] = industry
    if country:
        org_payload["country"] = country

    try:
        organization = db.table("organizations").insert(org_payload).execute().data
    except Exception as e:
        log.exception("Failed to create organization")
        msg = str(e)
        # Detect common RLS / permission errors and return a clearer message
        if "row level" in msg.lower() or "42501" in msg:
            return jsonify({
                "error": "Supabase permission error",
                "details": "Row-level security prevented creating organizations. Ensure SUPABASE_SERVICE_KEY is the service-role key and RLS allows backend inserts.",
            }), 500
        return jsonify({"error": "Failed to create organization", "details": msg}), 500

    if not organization:
        return jsonify({"error": "Failed to create organization"}), 500

    organization_id = organization[0]["id"]

    # ------------------------------------
    # 3. Create the app_users row — id MUST match the Supabase
    #    Auth user id so the FK constraint holds and login can
    #    look this row up later.
    # ------------------------------------
    try:
        user = (
            db.table("app_users")
            .insert(
                {
                    "id": user_id,
                    "organization_id": organization_id,
                    "email": email,
                    "full_name": full_name,
                    "role": "admin",
                }
            )
            .execute()
        ).data
    except APIError as e:
        log.exception("Failed to insert app_users row")
        return jsonify({"error": "Failed to create user record", "details": str(e)}), 500

    if not user:
        return jsonify({"error": "Failed to create user"}), 500

    user = user[0]

    # ------------------------------------
    # 4. Issue our own app JWT (used by login_required on every
    #    other route) — independent of Supabase's session token.
    # ------------------------------------
    token = create_access_token(
        user_id=user["id"],
        organization_id=user["organization_id"],
        role=user["role"],
        full_name=user["full_name"],
        email=user["email"],
    )

    return jsonify({
        "message": "Registration successful",
        "token": token,
        "user": {
            "id": user["id"],
            "organization_id": user["organization_id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
        },
    }), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json(force=True) or {}
    email = payload.get("email")
    password = payload.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    email = email.strip().lower()
    db = get_client()

    # ------------------------------------
    # 1. Verify credentials against Supabase Auth
    # ------------------------------------
    try:
        auth_resp = db.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        log.warning("Supabase login failed for %s: %s", email, e)
        return jsonify({"error": "Invalid email or password"}), 401

    auth_user = getattr(auth_resp, "user", None)
    if not auth_user:
        return jsonify({"error": "Invalid email or password"}), 401

    user_id = auth_user.id

    # ------------------------------------
    # 2. Look up the matching app_users row for org/role/name
    # ------------------------------------
    try:
        result = (
            db.table("app_users")
            .select("id, organization_id, email, full_name, role")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        log.exception("app_users lookup failed during login")
        return jsonify({"error": "Login failed"}), 500

    if not result.data:
        # Auto-provision a minimal organization and app_users row for this auth user.
        try:
            # Create a default organization using the email local-part as name
            default_name = email.split("@")[0]
            org_payload = {"name": f"{default_name}'s Organization"}
            org = db.table("organizations").insert(org_payload).execute().data
            if not org:
                return jsonify({"error": "Failed to provision organization for account"}), 500
            organization_id = org[0]["id"]

            user_rec = (
                db.table("app_users")
                .insert(
                    {
                        "id": user_id,
                        "organization_id": organization_id,
                        "email": email,
                        "full_name": email.split("@")[0],
                        "role": "admin",
                    }
                )
                .execute()
            ).data
            if not user_rec:
                return jsonify({"error": "Failed to create app user during provisioning"}), 500
            user = user_rec[0]
        except Exception as e:
            log.exception("Failed to auto-provision organization/app_user during login")
            msg = str(e)
            if "row level" in msg.lower() or "42501" in msg:
                return jsonify({
                    "error": "Supabase permission error",
                    "details": "Row-level security prevented creating organizations during auto-provision. Ensure SUPABASE_SERVICE_KEY is the service-role key and RLS allows backend inserts.",
                }), 500
            return jsonify({"error": "Account exists but has no organization record", "details": msg}), 500

    # `user` is set either by the existing profile lookup or the provisioning
    # branch above. Do not overwrite the latter with the empty lookup result.
    if result.data:
        user = result.data[0]

    # ------------------------------------
    # 3. Issue our own app JWT
    # ------------------------------------
    token = create_access_token(
        user_id=user["id"],
        organization_id=user["organization_id"],
        role=user["role"],
        full_name=user["full_name"],
        email=user["email"],
    )

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user["id"],
            "organization_id": user["organization_id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
        },
    }), 200


@auth_bp.post("/logout")
def logout():
    return jsonify({"message": "Logged out"}), 200


@auth_bp.patch("/profile")
@login_required
def update_profile():
    """Update the non-sensitive presentation details of the signed-in user."""
    payload = request.get_json(force=True) or {}
    full_name = str(payload.get("full_name") or "").strip()
    if not full_name:
        return jsonify({"error": "Full name is required."}), 400
    if len(full_name) > 120:
        return jsonify({"error": "Full name must be 120 characters or fewer."}), 400
    rows = get_client().table("app_users").update({"full_name": full_name}).eq(
        "id", g.current_user["sub"]
    ).eq("organization_id", g.current_user["org"]).execute().data
    if not rows:
        return jsonify({"error": "Profile not found."}), 404
    user = rows[0]
    return jsonify({"user": {"id": user["id"], "organization_id": user["organization_id"], "email": user["email"], "full_name": user["full_name"], "role": user["role"]}})


@auth_bp.get("/profile")
@login_required
def get_profile():
    rows = get_client().table("app_users").select(
        "id, organization_id, email, full_name, role"
    ).eq("id", g.current_user["sub"]).eq("organization_id", g.current_user["org"]).execute().data
    if not rows:
        return jsonify({"error": "Profile not found."}), 404
    return jsonify({"user": rows[0]})


@auth_bp.delete("/account")
@login_required
def delete_account():
    """Permanently remove the current user's application profile and auth identity.

    Organization operational records are deliberately retained because they may
    be shared with other users. Deleting an organization is a separate admin
    operation and is not implied by deleting one account.
    """
    payload = request.get_json(silent=True) or {}
    if payload.get("confirmation") != "DELETE":
        return jsonify({"error": "Type DELETE to confirm permanent account deletion."}), 400

    user_id = g.current_user["sub"]
    db = get_client()
    try:
        # Clear optional foreign-key references before removing the profile.
        db.table("ai_recommendations").update({"reviewed_by": None}).eq("reviewed_by", user_id).execute()
        db.table("communications").update({"approved_by": None}).eq("approved_by", user_id).execute()
        db.table("tasks").update({"assigned_to": None}).eq("assigned_to", user_id).execute()
        db.table("app_users").delete().eq("id", user_id).execute()
        db.auth.admin.delete_user(user_id)
    except Exception as exc:
        log.exception("Account deletion failed for %s", user_id)
        return jsonify({"error": "Unable to delete account", "details": str(exc)}), 500

    return jsonify({"message": "Account deleted"}), 200
