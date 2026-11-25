import secrets
from functools import wraps

from flask import abort, g, jsonify, request, session

from backend.db import get_db


def csrf_protect():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None

    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        abort(403, description="A valid CSRF token is required.")
    return None


def make_csrf_token():
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    return token


def current_user():
    if "current_user" in g:
        return g.current_user

    user_id = session.get("user_id")
    if user_id is None:
        return None

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, name, email, role, phone "
            "FROM Users WHERE user_id = %s",
            (user_id,),
        )
        g.current_user = cursor.fetchone()
    finally:
        cursor.close()

    if g.current_user is None:
        session.clear()
    return g.current_user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return jsonify({"error": "Authentication is required."}), 401
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if user["role"] not in roles:
                return jsonify({"error": "You are not authorized to perform this action."}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorate
