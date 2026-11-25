import mysql.connector
from flask import Blueprint, jsonify, request

from backend.db import get_db, transaction
from backend.security import current_user, login_required, roles_required


claims_bp = Blueprint("claims", __name__)


def _too_long_text(value):
    return isinstance(value, str) and len(value.encode("utf-8")) > 65535


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None
    return body


def _notify(cursor, user_id, message, claim_id):
    cursor.execute(
        "INSERT INTO Notifications (user_id, message, claim_id) VALUES (%s, %s, %s)",
        (user_id, message, claim_id),
    )


def _load_locked_claim(cursor, claim_id):
    cursor.execute("SELECT item_id FROM Claims WHERE claim_id = %s", (claim_id,))
    reference = cursor.fetchone()
    if reference is None:
        return None, None

    item_id = reference["item_id"]
    cursor.execute(
        "SELECT item_id, user_id, item_type, status FROM Items "
        "WHERE item_id = %s FOR UPDATE",
        (item_id,),
    )
    item = cursor.fetchone()
    cursor.execute(
        "SELECT claim_id, item_id, claimant_id, ownership_evidence, finder_decision, "
        "finder_remarks, finder_decided_at, admin_decision, admin_id, admin_remarks, "
        "admin_decided_at, status, claim_date "
        "FROM Claims WHERE claim_id = %s FOR UPDATE",
        (claim_id,),
    )
    return item, cursor.fetchone()


def _sync_item_status(cursor, item_id):
    cursor.execute("SELECT status FROM Items WHERE item_id = %s", (item_id,))
    item = cursor.fetchone()
    if item is None or item["status"] in {"RETURNED", "CLOSED"}:
        return

    cursor.execute(
        "SELECT 1 FROM Claims WHERE item_id = %s AND status = 'APPROVED' LIMIT 1",
        (item_id,),
    )
    has_approved = cursor.fetchone() is not None
    if has_approved:
        next_status = "CLAIMED"
    else:
        cursor.execute(
            "SELECT 1 FROM Claims WHERE item_id = %s AND status = 'PENDING' LIMIT 1",
            (item_id,),
        )
        next_status = "CLAIM_PENDING" if cursor.fetchone() is not None else "ACTIVE"
    cursor.execute("UPDATE Items SET status = %s WHERE item_id = %s", (next_status, item_id))


def _claim_access(claim, item, user):
    if user["role"] == "ADMIN":
        return True
    return (
        user["user_id"] == claim["claimant_id"]
        or user["user_id"] == item["user_id"]
    )


def _claim_dict(row):
    return {
        "claim_id": row["claim_id"],
        "item_id": row["item_id"],
        "claimant_id": row["claimant_id"],
        "claimant_name": row.get("claimant_name"),
        "ownership_evidence": row["ownership_evidence"],
        "finder_decision": row["finder_decision"],
        "finder_remarks": row["finder_remarks"],
        "finder_decided_at": row["finder_decided_at"].isoformat()
        if row["finder_decided_at"]
        else None,
        "admin_decision": row["admin_decision"],
        "admin_remarks": row["admin_remarks"],
        "admin_decided_at": row["admin_decided_at"].isoformat()
        if row["admin_decided_at"]
        else None,
        "status": row["status"],
        "claim_date": row["claim_date"].isoformat(),
    }


@claims_bp.post("/items/<int:item_id>")
@login_required
def submit_claim(item_id):
    body = _json_body()
    evidence = body.get("ownership_evidence") if body else None
    if not isinstance(evidence, str) or not evidence.strip():
        return jsonify({"error": "Ownership evidence is required."}), 400
    evidence = evidence.strip()
    if len(evidence.encode("utf-8")) > 65535:
        return jsonify({"error": "Ownership evidence is too long."}), 400

    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        with transaction(connection):
            cursor.execute(
                "SELECT item_id, user_id, item_type, status FROM Items "
                "WHERE item_id = %s FOR UPDATE",
                (item_id,),
            )
            item = cursor.fetchone()
            if item is None:
                return jsonify({"error": "Item not found."}), 404
            if item["item_type"] != "FOUND":
                return jsonify({"error": "Claims can only be submitted for FOUND items."}), 409
            if item["user_id"] == user["user_id"]:
                return jsonify({"error": "You cannot claim an item you reported."}), 403
            if item["status"] not in {"ACTIVE", "CLAIM_PENDING"}:
                return jsonify({"error": "This item is not currently accepting claims."}), 409
            cursor.execute(
                "SELECT claim_id FROM Claims WHERE item_id = %s AND claimant_id = %s",
                (item_id, user["user_id"]),
            )
            if cursor.fetchone():
                return jsonify({"error": "You have already submitted a claim for this item."}), 409
            cursor.execute(
                "INSERT INTO Claims (item_id, claimant_id, ownership_evidence) "
                "VALUES (%s, %s, %s)",
                (item_id, user["user_id"], evidence),
            )
            claim_id = cursor.lastrowid
            cursor.execute(
                "UPDATE Items SET status = 'CLAIM_PENDING' WHERE item_id = %s",
                (item_id,),
            )
            _notify(
                cursor,
                item["user_id"],
                "A new ownership claim was submitted for your found item.",
                claim_id,
            )
    except mysql.connector.IntegrityError as error:
        if error.errno == 1062:
            return jsonify({"error": "A claim for this item already exists from this account."}), 409
        raise
    finally:
        cursor.close()
    return jsonify({"claim_id": claim_id, "message": "Claim submitted successfully."}), 201


@claims_bp.get("/mine")
@login_required
def my_claims():
    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT c.claim_id, c.item_id, c.claimant_id, c.ownership_evidence, "
            "c.finder_decision, c.finder_remarks, c.finder_decided_at, "
            "c.admin_decision, c.admin_remarks, c.admin_decided_at, c.status, "
            "c.claim_date, u.name AS claimant_name "
            "FROM Claims c JOIN Users u ON u.user_id = c.claimant_id "
            "WHERE c.claimant_id = %s ORDER BY c.claim_date DESC",
            (user["user_id"],),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify({"claims": [_claim_dict(row) for row in rows]})


@claims_bp.get("/review-queue")
@roles_required("ADMIN")
def admin_review_queue():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT c.claim_id, c.item_id, c.claimant_id, c.ownership_evidence, "
            "c.finder_decision, c.finder_remarks, c.finder_decided_at, "
            "c.admin_decision, c.admin_remarks, c.admin_decided_at, c.status, "
            "c.claim_date, claimant.name AS claimant_name, i.title AS item_title, "
            "i.item_date, i.status AS item_status "
            "FROM Claims c JOIN Users claimant ON claimant.user_id = c.claimant_id "
            "JOIN Items i ON i.item_id = c.item_id "
            "WHERE c.finder_decision = 'APPROVED' "
            "AND c.admin_decision = 'PENDING' AND c.status = 'PENDING' "
            "ORDER BY c.claim_date"
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    claims = []
    for row in rows:
        claim = _claim_dict(row)
        claim["item_title"] = row["item_title"]
        claim["item_date"] = row["item_date"].isoformat()
        claim["item_status"] = row["item_status"]
        claims.append(claim)
    return jsonify({"claims": claims})


_QUEUE_SELECT = (
    "SELECT c.claim_id, c.item_id, c.claimant_id, c.ownership_evidence, "
    "c.finder_decision, c.finder_remarks, c.finder_decided_at, "
    "c.admin_decision, c.admin_remarks, c.admin_decided_at, c.status, "
    "c.claim_date, claimant.name AS claimant_name, i.title AS item_title, "
    "i.item_date, i.status AS item_status "
)
_QUEUE_FROM = (
    "FROM Claims c JOIN Users claimant ON claimant.user_id = c.claimant_id "
    "JOIN Items i ON i.item_id = c.item_id "
)


def _page_args():
    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(50, max(1, int(request.args.get("per_page", "20"))))
    except ValueError:
        return None
    return page, per_page


def _queue_claim(row):
    claim = _claim_dict(row)
    claim["item_title"] = row["item_title"]
    claim["item_date"] = row["item_date"].isoformat()
    claim["item_status"] = row["item_status"]
    return claim


@claims_bp.get("/finder-queue")
@roles_required("STUDENT", "STAFF")
def finder_queue():
    """Claims on items reported by the logged-in user. state=pending limits it to claims
    awaiting the finder's decision; the default (all) lists every claim, pending ones first."""
    state = request.args.get("state", "all").lower()
    if state not in {"all", "pending"}:
        return jsonify({"error": "state must be all or pending."}), 400
    paging = _page_args()
    if paging is None:
        return jsonify({"error": "page and per_page must be integers."}), 400
    page, per_page = paging

    sql = _QUEUE_SELECT + _QUEUE_FROM + "WHERE i.user_id = %s "
    if state == "pending":
        sql += "AND c.status = 'PENDING' AND c.finder_decision = 'PENDING' "
    sql += (
        "ORDER BY (c.status = 'PENDING' AND c.finder_decision = 'PENDING') DESC, "
        "c.claim_date DESC, c.claim_id DESC LIMIT %s OFFSET %s"
    )
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, (current_user()["user_id"], per_page, (page - 1) * per_page))
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify({"claims": [_queue_claim(row) for row in rows], "page": page, "per_page": per_page})


@claims_bp.get("/handover-queue")
@roles_required("ADMIN")
def handover_queue():
    """Approved claims. state=pending (default): awaiting handover; completed: handed over; all: both."""
    state = request.args.get("state", "pending").lower()
    if state not in {"pending", "completed", "all"}:
        return jsonify({"error": "state must be pending, completed or all."}), 400
    paging = _page_args()
    if paging is None:
        return jsonify({"error": "page and per_page must be integers."}), 400
    page, per_page = paging

    sql = (
        _QUEUE_SELECT
        + ", h.handover_id, h.handover_date, h.remarks AS handover_remarks, h.recorded_by "
        + _QUEUE_FROM
        + "LEFT JOIN Handover h ON h.claim_id = c.claim_id WHERE c.status = 'APPROVED' "
    )
    if state == "pending":
        sql += "AND h.handover_id IS NULL ORDER BY c.admin_decided_at, c.claim_id "
    else:
        if state == "completed":
            sql += "AND h.handover_id IS NOT NULL "
        sql += "ORDER BY c.admin_decided_at DESC, c.claim_id DESC "
    sql += "LIMIT %s OFFSET %s"

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, (per_page, (page - 1) * per_page))
        rows = cursor.fetchall()
    finally:
        cursor.close()
    claims = []
    for row in rows:
        claim = _queue_claim(row)
        claim["handover"] = (
            {
                "handover_id": row["handover_id"],
                "handover_date": row["handover_date"].isoformat(),
                "remarks": row["handover_remarks"],
                "recorded_by": row["recorded_by"],
            }
            if row["handover_id"]
            else None
        )
        claims.append(claim)
    return jsonify({"claims": claims, "page": page, "per_page": per_page})


@claims_bp.get("/items/<int:item_id>")
@roles_required("STUDENT", "STAFF", "ADMIN")
def item_claims(item_id):
    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id FROM Items WHERE item_id = %s", (item_id,))
        item = cursor.fetchone()
        if item is None:
            return jsonify({"error": "Item not found."}), 404
        if user["role"] != "ADMIN" and user["user_id"] != item["user_id"]:
            return jsonify({"error": "Only the finder or an administrator can review these claims."}), 403
        cursor.execute(
            "SELECT c.claim_id, c.item_id, c.claimant_id, c.ownership_evidence, "
            "c.finder_decision, c.finder_remarks, c.finder_decided_at, "
            "c.admin_decision, c.admin_remarks, c.admin_decided_at, c.status, "
            "c.claim_date, u.name AS claimant_name "
            "FROM Claims c JOIN Users u ON u.user_id = c.claimant_id "
            "WHERE c.item_id = %s ORDER BY c.claim_date",
            (item_id,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify({"claims": [_claim_dict(row) for row in rows]})


@claims_bp.get("/<int:claim_id>")
@login_required
def claim_detail(claim_id):
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT c.claim_id, c.item_id, c.claimant_id, c.ownership_evidence, "
            "c.finder_decision, c.finder_remarks, c.finder_decided_at, "
            "c.admin_decision, c.admin_remarks, c.admin_decided_at, c.status, "
            "c.claim_date, i.user_id, u.name AS claimant_name "
            "FROM Claims c JOIN Items i ON i.item_id = c.item_id "
            "JOIN Users u ON u.user_id = c.claimant_id WHERE c.claim_id = %s",
            (claim_id,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        return jsonify({"error": "Claim not found."}), 404

    user = current_user()
    if not _claim_access(row, {"user_id": row["user_id"]}, user):
        return jsonify({"error": "You are not authorized to view this claim."}), 403
    return jsonify({"claim": _claim_dict(row)})


@claims_bp.post("/<int:claim_id>/finder-decision")
@roles_required("STUDENT", "STAFF")
def finder_decision(claim_id):
    body = _json_body()
    if body is None:
        return jsonify({"error": "A JSON request body is required."}), 400
    decision = body.get("decision")
    remarks = body.get("remarks")
    if decision not in {"APPROVED", "REJECTED"}:
        return jsonify({"error": "decision must be APPROVED or REJECTED."}), 400
    if remarks is not None and (not isinstance(remarks, str) or _too_long_text(remarks)):
        return jsonify({"error": "remarks must be text no longer than 65535 characters."}), 400
    if decision == "REJECTED" and (not isinstance(remarks, str) or not remarks.strip()):
        return jsonify({"error": "A reason is required when rejecting a claim."}), 400

    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        with transaction(connection):
            item, claim = _load_locked_claim(cursor, claim_id)
            if claim is None:
                return jsonify({"error": "Claim not found."}), 404
            if item is None:
                return jsonify({"error": "Item not found."}), 404
            if item["user_id"] != user["user_id"]:
                return jsonify({"error": "Only the finder can review this claim."}), 403
            if item["item_type"] != "FOUND":
                return jsonify({"error": "Claims are only supported for FOUND items."}), 409
            if claim["status"] != "PENDING" or claim["finder_decision"] != "PENDING":
                return jsonify({"error": "This claim is no longer awaiting finder review."}), 409
            if item["status"] in {"RETURNED", "CLOSED"}:
                return jsonify({"error": "This item is no longer under review."}), 409

            next_status = "REJECTED" if decision == "REJECTED" else "PENDING"
            cursor.execute(
                "UPDATE Claims SET finder_decision = %s, finder_remarks = %s, "
                "finder_decided_at = NOW(), status = %s WHERE claim_id = %s",
                (
                    decision,
                    remarks.strip() if isinstance(remarks, str) and remarks.strip() else None,
                    next_status,
                    claim_id,
                ),
            )
            if decision == "REJECTED":
                _sync_item_status(cursor, item["item_id"])
                message = "The finder rejected your claim."
            else:
                message = "The finder approved your claim. It is awaiting administrator review."
            _notify(cursor, claim["claimant_id"], message, claim_id)
    finally:
        cursor.close()
    return jsonify({"message": "Finder decision recorded."})


@claims_bp.post("/<int:claim_id>/admin-decision")
@roles_required("ADMIN")
def admin_decision(claim_id):
    body = _json_body()
    if body is None:
        return jsonify({"error": "A JSON request body is required."}), 400
    decision = body.get("decision")
    remarks = body.get("remarks")
    if decision not in {"APPROVED", "REJECTED"}:
        return jsonify({"error": "decision must be APPROVED or REJECTED."}), 400
    if remarks is not None and (not isinstance(remarks, str) or _too_long_text(remarks)):
        return jsonify({"error": "remarks must be text no longer than 65535 characters."}), 400
    if decision == "REJECTED" and (not isinstance(remarks, str) or not remarks.strip()):
        return jsonify({"error": "A reason is required when rejecting a claim."}), 400

    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        with transaction(connection):
            item, claim = _load_locked_claim(cursor, claim_id)
            if claim is None:
                return jsonify({"error": "Claim not found."}), 404
            if item is None:
                return jsonify({"error": "Item not found."}), 404
            if item["item_type"] != "FOUND":
                return jsonify({"error": "Claims are only supported for FOUND items."}), 409
            if claim["status"] != "PENDING" or claim["finder_decision"] != "APPROVED":
                return jsonify({"error": "Only finder-approved claims can receive an administrator decision."}), 409
            if claim["admin_decision"] != "PENDING":
                return jsonify({"error": "An administrator has already decided this claim."}), 409
            if item["status"] in {"RETURNED", "CLOSED"}:
                return jsonify({"error": "This item is no longer under review."}), 409

            if decision == "APPROVED":
                cursor.execute(
                    "SELECT 1 FROM Claims WHERE item_id = %s AND status = 'APPROVED' LIMIT 1",
                    (item["item_id"],),
                )
                if cursor.fetchone():
                    return jsonify({"error": "Another claim has already been approved for this item."}), 409
                cursor.execute(
                    "UPDATE Claims SET admin_decision = 'APPROVED', admin_id = %s, "
                    "admin_remarks = %s, admin_decided_at = NOW(), status = 'APPROVED' "
                    "WHERE claim_id = %s",
                    (
                        user["user_id"],
                        remarks.strip() if isinstance(remarks, str) and remarks.strip() else None,
                        claim_id,
                    ),
                )
                cursor.execute(
                    "UPDATE Items SET status = 'CLAIMED' WHERE item_id = %s",
                    (item["item_id"],),
                )
                message = "Your claim received final administrator approval. Contact the university to arrange handover."
            else:
                cursor.execute(
                    "UPDATE Claims SET admin_decision = 'REJECTED', admin_id = %s, "
                    "admin_remarks = %s, admin_decided_at = NOW(), status = 'REJECTED' "
                    "WHERE claim_id = %s",
                    (user["user_id"], remarks.strip(), claim_id),
                )
                _sync_item_status(cursor, item["item_id"])
                message = "The administrator rejected your claim."

            _notify(cursor, claim["claimant_id"], message, claim_id)
            _notify(
                cursor,
                item["user_id"],
                "An administrator recorded a final decision for a claim on your found item.",
                claim_id,
            )
    except mysql.connector.IntegrityError as error:
        if error.errno == 1062:
            return jsonify({"error": "Another claim has already been approved for this item."}), 409
        raise
    finally:
        cursor.close()
    return jsonify({"message": "Administrator decision recorded."})


@claims_bp.post("/<int:claim_id>/cancel-approval")
@roles_required("ADMIN")
def cancel_approval(claim_id):
    body = _json_body()
    reason = body.get("reason") if body else None
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason.encode("utf-8")) > 65000
    ):
        return jsonify({"error": "A cancellation reason is required."}), 400

    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        with transaction(connection):
            item, claim = _load_locked_claim(cursor, claim_id)
            if claim is None:
                return jsonify({"error": "Claim not found."}), 404
            if item is None:
                return jsonify({"error": "Item not found."}), 404
            if (
                claim["status"] != "APPROVED"
                or claim["admin_decision"] != "APPROVED"
                or claim["finder_decision"] != "APPROVED"
                or item["status"] != "CLAIMED"
            ):
                return jsonify({"error": "Only an approved claim can be cancelled."}), 409
            cursor.execute(
                "SELECT handover_id FROM Handover WHERE claim_id = %s",
                (claim_id,),
            )
            if cursor.fetchone():
                return jsonify({"error": "An approval cannot be cancelled after handover."}), 409

            cursor.execute(
                "UPDATE Claims SET admin_decision = 'REJECTED', admin_id = %s, "
                "admin_remarks = %s, admin_decided_at = NOW(), status = 'REJECTED' "
                "WHERE claim_id = %s",
                (user["user_id"], reason.strip(), claim_id),
            )
            _sync_item_status(cursor, item["item_id"])
            _notify(
                cursor,
                claim["claimant_id"],
                "Your claim approval was cancelled by an administrator. Reason: "
                + reason.strip(),
                claim_id,
            )
            _notify(
                cursor,
                item["user_id"],
                "An administrator cancelled an approval for a claim on your item.",
                claim_id,
            )
    finally:
        cursor.close()
    return jsonify({"message": "Claim approval cancelled."})


@claims_bp.post("/<int:claim_id>/handover")
@roles_required("ADMIN")
def record_handover(claim_id):
    body = _json_body()
    if body is None:
        body = {}
    remarks = body.get("remarks")
    if remarks is not None and (not isinstance(remarks, str) or _too_long_text(remarks)):
        return jsonify({"error": "remarks must be text no longer than 65535 characters."}), 400

    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        with transaction(connection):
            item, claim = _load_locked_claim(cursor, claim_id)
            if claim is None:
                return jsonify({"error": "Claim not found."}), 404
            if item is None:
                return jsonify({"error": "Item not found."}), 404
            if (
                claim["status"] != "APPROVED"
                or claim["admin_decision"] != "APPROVED"
                or claim["finder_decision"] != "APPROVED"
                or item["status"] != "CLAIMED"
            ):
                return jsonify({"error": "Only an approved claim for a CLAIMED item can be handed over."}), 409
            cursor.execute(
                "SELECT handover_id FROM Handover WHERE claim_id = %s",
                (claim_id,),
            )
            if cursor.fetchone():
                return jsonify({"error": "A handover has already been recorded for this claim."}), 409

            cursor.execute(
                "INSERT INTO Handover (claim_id, handover_date, remarks, recorded_by) "
                "VALUES (%s, NOW(), %s, %s)",
                (
                    claim_id,
                    remarks.strip() if isinstance(remarks, str) and remarks.strip() else None,
                    user["user_id"],
                ),
            )
            cursor.execute(
                "UPDATE Items SET status = 'RETURNED' WHERE item_id = %s",
                (item["item_id"],),
            )
            cursor.execute(
                "SELECT claim_id, claimant_id FROM Claims "
                "WHERE item_id = %s AND status = 'PENDING' FOR UPDATE",
                (item["item_id"],),
            )
            pending_claims = cursor.fetchall()
            rejection_reason = "This item was handed over after another claim was approved."
            for pending in pending_claims:
                cursor.execute(
                    "UPDATE Claims SET admin_decision = 'REJECTED', admin_id = %s, "
                    "admin_remarks = %s, admin_decided_at = NOW(), status = 'REJECTED' "
                    "WHERE claim_id = %s AND status = 'PENDING'",
                    (user["user_id"], rejection_reason, pending["claim_id"]),
                )
                _notify(
                    cursor,
                    pending["claimant_id"],
                    "Your claim was rejected because the item was handed over to another claimant.",
                    pending["claim_id"],
                )

            _notify(cursor, claim["claimant_id"], "The item handover has been recorded.", claim_id)
            _notify(
                cursor,
                item["user_id"],
                "The found item has been handed over to its approved claimant.",
                claim_id,
            )
    except mysql.connector.IntegrityError as error:
        if error.errno == 1062:
            return jsonify({"error": "A handover has already been recorded for this claim."}), 409
        raise
    finally:
        cursor.close()
    return jsonify({"message": "Handover recorded successfully."}), 201


@claims_bp.get("/<int:claim_id>/handover")
@login_required
def get_handover(claim_id):
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT h.handover_id, h.claim_id, h.handover_date, h.remarks, "
            "h.recorded_by, c.claimant_id, i.user_id "
            "FROM Handover h JOIN Claims c ON c.claim_id = h.claim_id "
            "JOIN Items i ON i.item_id = c.item_id WHERE h.claim_id = %s",
            (claim_id,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        return jsonify({"error": "Handover not found."}), 404
    user = current_user()
    if user["role"] != "ADMIN" and user["user_id"] not in {
        row["claimant_id"],
        row["user_id"],
    }:
        return jsonify({"error": "You are not authorized to view this handover."}), 403
    return jsonify(
        {
            "handover": {
                "handover_id": row["handover_id"],
                "claim_id": row["claim_id"],
                "handover_date": row["handover_date"].isoformat(),
                "remarks": row["remarks"],
                "recorded_by": row["recorded_by"],
            }
        }
    )
