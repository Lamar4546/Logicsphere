import os
from flask import Flask
from flask_cors import CORS

from .services.supabase_client import init_supabase


def create_app():
    app = Flask(__name__)
    CORS(app, supports_credentials=True)

    app.config["SUPABASE_URL"] = os.environ.get("SUPABASE_URL")
    app.config["SUPABASE_SERVICE_KEY"] = os.environ.get("SUPABASE_SERVICE_KEY")

    init_supabase(app)

    from .blueprints.command_center import command_center_bp
    from .blueprints.shipments import shipments_bp
    from .blueprints.recommendations import recommendations_bp
    from .blueprints.workflows import workflows_bp

    app.register_blueprint(command_center_bp, url_prefix="/api/command-center")
    app.register_blueprint(shipments_bp, url_prefix="/api/shipments")
    app.register_blueprint(recommendations_bp, url_prefix="/api/recommendations")
    app.register_blueprint(workflows_bp, url_prefix="/api/workflows")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
