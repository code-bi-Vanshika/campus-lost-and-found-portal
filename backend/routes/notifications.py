from flask import Blueprint, jsonify, request

from backend.db import get_db, transaction
from backend.security import current_user, login_required


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("")
@login_required
def list_notifications():
    user = current_user()
    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(
            50,
            max(1, int(request.args.get("per_page", "20"))),
        )
    except ValueError:
        return jsonify({"error": "page and per_page must be integers."}), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT notification_id, message, created_at, is_read, claim_id "
            "FROM Notifications WHERE user_id = %s "
            "ORDER BY created_at DESC, notification_id DESC LIMIT %s OFFSET %s",
            (user["user_id"], per_page, (page - 1) * per_page),
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT COUNT(*) AS unread_count FROM Notifications "
            "WHERE user_id = %s AND is_read = FALSE",
            (user["user_id"],),
        )
        unread_count = cursor.fetchone()["unread_count"]
    finally:
        cursor.close()
    return jsonify(
        {
            "notifications": [
                {
                    "notification_id": row["notification_id"],
                    "message": row["message"],
                    "created_at": row["created_at"].isoformat(),
                    "is_read": bool(row["is_read"]),
                    "claim_id": row["claim_id"],
                }
                for row in rows
            ],
            "page": page,
            "per_page": per_page,
            "unread_count": unread_count,
        }
    )


@notifications_bp.post("/<int:notification_id>/read")
@login_required
def mark_read(notification_id):
    user = current_user()
    connection = get_db()
    cursor = connection.cursor()
    try:
        with transaction(connection):
            cursor.execute(
                "UPDATE Notifications SET is_read = TRUE "
                "WHERE notification_id = %s AND user_id = %s",
                (notification_id, user["user_id"]),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "SELECT notification_id FROM Notifications "
                    "WHERE notification_id = %s AND user_id = %s",
                    (notification_id, user["user_id"]),
                )
                if cursor.fetchone() is None:
                    return jsonify({"error": "Notification not found."}), 404
    finally:
        cursor.close()
    return jsonify({"message": "Notification marked as read."})
