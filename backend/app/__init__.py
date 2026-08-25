import os
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from .services.supabase_client import init_supabase

load_dotenv()


def create_app():
    app = Flask(__name__)
    CORS(app, supports_credentials=True)

    app.config["SUPABASE_URL"] = os.environ.get("SUPABASE_URL")
    app.config["SUPABASE_SERVICE_KEY"] = os.environ.get("SUPABASE_SERVICE_KEY")
    # Ensure JWT secret is at least 32 bytes to avoid insecure HMAC warnings
    raw_secret = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-me")
    if len(raw_secret or "") < 32:
        import hashlib

        derived = hashlib.sha256((raw_secret or "").encode()).hexdigest()
        app.config["JWT_SECRET_KEY"] = derived
    else:
        app.config["JWT_SECRET_KEY"] = raw_secret

    init_supabase(app)

    # Register blueprints (import inside factory to avoid import-time side effects)
    from .blueprints.auth import auth_bp
    from .blueprints.command_center import command_center_bp
    from .blueprints.shipments import shipments_bp
    from .blueprints.recommendations import recommendations_bp
    from .blueprints.workflows import workflows_bp
    from .blueprints.operations import operations_bp
    from .blueprints.notifications import notifications_bp
    from .blueprints.integrations import integrations_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(command_center_bp, url_prefix="/api/command-center")
    app.register_blueprint(shipments_bp, url_prefix="/api/shipments")
    app.register_blueprint(recommendations_bp, url_prefix="/api/recommendations")
    app.register_blueprint(workflows_bp, url_prefix="/api/workflows")
    app.register_blueprint(operations_bp, url_prefix="/api/operations")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(integrations_bp, url_prefix="/api/integrations")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
