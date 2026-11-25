import re

import mysql.connector
from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from backend.db import get_db, transaction
from backend.security import current_user, make_csrf_token


auth_bp = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None
    return body


@auth_bp.get("/csrf")
def csrf_token():
    return jsonify({"csrf_token": make_csrf_token()})


@auth_bp.post("/register")
def register():
    body = _json_body()
    if body is None:
        return jsonify({"error": "A JSON request body is required."}), 400

    name = body.get("name")
    email = body.get("email")
    password = body.get("password")
    phone = body.get("phone")

    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        return jsonify({"error": "Name is required and must be at most 100 characters."}), 400
    if not isinstance(email, str) or len(email.strip()) > 150:
        return jsonify({"error": "A valid email address is required."}), 400
    email = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        return jsonify({"error": "A valid email address is required."}), 400
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        return jsonify({"error": "Password must contain between 12 and 128 characters."}), 400
    if phone is not None and (
        not isinstance(phone, str) or len(phone.strip()) > 15
    ):
        return jsonify({"error": "Phone must be at most 15 characters."}), 400

    connection = get_db()
    cursor = connection.cursor()
    try:
        with transaction(connection):
            cursor.execute(
                "INSERT INTO Users (name, email, password_hash, phone) "
                "VALUES (%s, %s, %s, %s)",
                (
                    name.strip(),
                    email,
                    generate_password_hash(password),
                    phone.strip() if isinstance(phone, str) and phone.strip() else None,
                ),
            )
            user_id = cursor.lastrowid
    except mysql.connector.IntegrityError as error:
        if error.errno == 1062:
            return jsonify({"error": "An account with that email already exists."}), 409
        raise
    finally:
        cursor.close()

    return jsonify({"user_id": user_id, "message": "Registration successful."}), 201


@auth_bp.post("/login")
def login():
    body = _json_body()
    if body is None:
        return jsonify({"error": "A JSON request body is required."}), 400
    email = body.get("email")
    password = body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Email and password are required."}), 400
    if len(email.strip()) > 150 or len(password) > 128:
        return jsonify({"error": "Invalid email or password."}), 401

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id, name, email, password_hash, role "
            "FROM Users WHERE email = %s",
            (email.strip().lower(),),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password."}), 401

    session.clear()
    session["user_id"] = user["user_id"]
    token = make_csrf_token()
    return jsonify(
        {
            "user": {
                "user_id": user["user_id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
            },
            "csrf_token": token,
        }
    )


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})


@auth_bp.get("/me")
def me():
    user = current_user()
    if user is None:
        return jsonify({"error": "Authentication is required."}), 401
    return jsonify({"user": user})
