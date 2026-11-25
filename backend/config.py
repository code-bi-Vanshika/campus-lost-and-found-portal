import os

from dotenv import load_dotenv


def load_config():
    load_dotenv()

    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("FLASK_SECRET_KEY must be configured.")

    debug = os.environ.get("FLASK_DEBUG", "false").strip().lower() == "true"
    cookie_secure = os.environ.get("COOKIE_SECURE")
    return {
        "SECRET_KEY": secret_key,
        "DEBUG": debug,
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "MYSQL_CONFIG": {
            "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
            "port": int(os.environ.get("MYSQL_PORT", "3306")),
            "user": os.environ.get("MYSQL_USER", ""),
            "password": os.environ.get("MYSQL_PASSWORD", ""),
            "database": os.environ.get("MYSQL_DATABASE", "campus_lost_found"),
            "connection_timeout": 5,
            "charset": "utf8mb4",
            "use_unicode": True,
        },
        "MAX_CONTENT_LENGTH": 16 * 1024 * 1024,
        "MAX_IMAGE_BYTES": 2 * 1024 * 1024,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": (
            cookie_secure.lower() == "true" if cookie_secure is not None else not debug
        ),
    }