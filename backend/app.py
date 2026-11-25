import logging

import mysql.connector
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from backend.config import load_config
from backend.db import close_db
from backend.routes.auth import auth_bp
from backend.routes.admin import admin_bp
from backend.routes.claims import claims_bp
from backend.routes.items import items_bp
from backend.routes.notifications import notifications_bp
from backend.security import csrf_protect


def create_app(test_config=None):
    app = Flask(__name__)
    if test_config is None:
        app.config.from_mapping(load_config())
    else:
        app.config.from_mapping(
            {
                "SECRET_KEY": "test-only-secret",
                "LOG_LEVEL": "WARNING",
                "MYSQL_CONFIG": {},
                "MAX_CONTENT_LENGTH": 16 * 1024 * 1024,
                "MAX_IMAGE_BYTES": 2 * 1024 * 1024,
                "SESSION_COOKIE_HTTPONLY": True,
                "SESSION_COOKIE_SAMESITE": "Lax",
                "SESSION_COOKIE_SECURE": False,
            }
        )
        app.config.update(test_config)

    logging.basicConfig(level=app.config["LOG_LEVEL"])
    app.teardown_appcontext(close_db)
    app.before_request(csrf_protect)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(items_bp, url_prefix="/api/items")
    app.register_blueprint(claims_bp, url_prefix="/api/claims")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify({"error": error.description}), error.code

    @app.errorhandler(mysql.connector.Error)
    def handle_database_error(error):
        app.logger.error("Database operation failed: %s", error)
        return jsonify({"error": "A database operation failed."}), 503

    return app


if __name__ == "__main__":
    create_app().run()
