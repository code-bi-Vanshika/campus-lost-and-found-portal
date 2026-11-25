from flask import Blueprint, jsonify

from backend.db import get_db
from backend.security import roles_required


admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/dashboard")
@roles_required("ADMIN")
def dashboard():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT status, COUNT(*) AS count FROM Items GROUP BY status")
        item_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
        cursor.execute("SELECT status, COUNT(*) AS count FROM Claims GROUP BY status")
        claim_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT COUNT(*) AS count FROM Claims "
            "WHERE finder_decision = 'APPROVED' AND admin_decision = 'PENDING' "
            "AND status = 'PENDING'"
        )
        awaiting_admin = cursor.fetchone()["count"]
        cursor.execute(
            "SELECT COUNT(*) AS count FROM Claims "
            "WHERE finder_decision = 'PENDING' AND status = 'PENDING'"
        )
        awaiting_finder = cursor.fetchone()["count"]
    finally:
        cursor.close()
    return jsonify(
        {
            "items_by_status": item_counts,
            "claims_by_status": claim_counts,
            "claims_awaiting_finder": awaiting_finder,
            "claims_awaiting_admin": awaiting_admin,
        }
    )
