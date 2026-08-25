import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash


JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 3600


def get_jwt_secret() -> str:
    secret = (
        current_app.config.get("JWT_SECRET_KEY")
        or os.environ.get("JWT_SECRET_KEY")
    )

    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required")

    return secret


def create_access_token(
    user_id: str,
    organization_id: str,
    role: str,
    full_name: str,
    email: str,
) -> str:

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role,
        "name": full_name,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(seconds=JWT_EXPIRATION_SECONDS)).timestamp()
        ),
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
        )

    except jwt.ExpiredSignatureError:
        return None

    except jwt.InvalidTokenError:
        return None


def get_auth_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return None

    return auth_header.split(" ", 1)[1].strip()


def login_required(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        token = get_auth_token()

        if not token:
            return jsonify({
                "error": "Authorization header required"
            }), 401

        payload = decode_access_token(token)

        if payload is None:
            return jsonify({
                "error": "Invalid or expired token"
            }), 401

        g.current_user = payload

        return func(*args, **kwargs)

    return wrapper


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)