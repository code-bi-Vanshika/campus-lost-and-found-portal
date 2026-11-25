from datetime import date

from flask import Blueprint, Response, current_app, jsonify, request

from backend.db import get_db, transaction
from backend.security import current_user, roles_required


items_bp = Blueprint("items", __name__)
ITEM_FIELDS = {
    "title": ("title", 150),
    "description": ("description", None),
    "category_id": ("category_id", None),
    "location_id": ("location_id", None),
    "item_date": ("item_date", None),
}
ITEM_TYPES = {"LOST", "FOUND"}
ITEM_STATUSES = {"ACTIVE", "CLAIM_PENDING", "CLAIMED", "RETURNED", "CLOSED"}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _positive_id(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _image_mime(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _read_uploaded_images(files):
    maximum = current_app.config["MAX_IMAGE_BYTES"]
    images = []
    for uploaded in files:
        if not uploaded or not uploaded.filename:
            continue
        data = uploaded.stream.read(maximum + 1)
        if not data:
            return None, "Uploaded images cannot be empty."
        if len(data) > maximum:
            return None, "Each image must be no larger than 2 MB."
        detected_mime = _image_mime(data)
        if detected_mime not in IMAGE_MIME_TYPES:
            return None, "Images must be valid JPEG, PNG, or WebP files."
        images.append((data, detected_mime))
    return images, None


def _parse_item_values(values, required):
    parsed = {}
    for field, (column, maximum) in ITEM_FIELDS.items():
        value = values.get(field)
        if value is None or value == "":
            if required:
                return None, f"{field} is required."
            continue
        if field in {"category_id", "location_id"}:
            value = _positive_id(value)
            if value is None:
                return None, f"{field} must be a positive integer."
        elif field == "item_date":
            try:
                value = date.fromisoformat(value)
            except (TypeError, ValueError):
                return None, "item_date must use YYYY-MM-DD format."
        elif field == "title":
            if not isinstance(value, str) or not value.strip():
                return None, "title cannot be empty."
            value = value.strip()
            if len(value) > maximum:
                return None, "title must be at most 150 characters."
        elif field == "description":
            if not isinstance(value, str) or not value.strip():
                return None, "description cannot be empty."
            value = value.strip()
            if len(value.encode("utf-8")) > 65535:
                return None, "description must fit in the database TEXT field."
        parsed[column] = value
    return parsed, None


def _serialize_item(row):
    return {
        "item_id": row["item_id"],
        "title": row["title"],
        "description": row["description"],
        "item_type": row["item_type"],
        "item_date": row["item_date"].isoformat(),
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "category": {
            "category_id": row["category_id"],
            "category_name": row["category_name"],
        },
        "location": {
            "location_id": row["location_id"],
            "location_name": row["location_name"],
        },
    }


@items_bp.get("/meta")
def item_form_metadata():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT category_id, category_name FROM Categories ORDER BY category_name")
        categories = cursor.fetchall()
        cursor.execute("SELECT location_id, location_name FROM Locations ORDER BY location_name")
        locations = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify({"categories": categories, "locations": locations})


@items_bp.get("")
def search_items():
    filters = []
    parameters = []

    query = request.args.get("q", "").strip()
    if len(query) > 200:
        return jsonify({"error": "Search text must be at most 200 characters."}), 400
    if query:
        filters.append("(i.title LIKE %s OR i.description LIKE %s)")
        pattern = f"%{query}%"
        parameters.extend((pattern, pattern))

    for parameter, column in (
        ("category_id", "i.category_id"),
        ("location_id", "i.location_id"),
    ):
        value = request.args.get(parameter)
        if value:
            parsed = _positive_id(value)
            if parsed is None:
                return jsonify({"error": f"{parameter} must be a positive integer."}), 400
            filters.append(f"{column} = %s")
            parameters.append(parsed)

    item_type = request.args.get("item_type", "").upper()
    if item_type:
        if item_type not in ITEM_TYPES:
            return jsonify({"error": "item_type must be LOST or FOUND."}), 400
        filters.append("i.item_type = %s")
        parameters.append(item_type)

    status = request.args.get("status", "").upper()
    if status:
        if status not in ITEM_STATUSES:
            return jsonify({"error": "Invalid item status."}), 400
        filters.append("i.status = %s")
        parameters.append(status)

    for parameter, operator in (("item_date", "="), ("date_from", ">="), ("date_to", "<=")):
        value = request.args.get(parameter)
        if value:
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError:
                return jsonify({"error": f"{parameter} must use YYYY-MM-DD format."}), 400
            filters.append(f"i.item_date {operator} %s")
            parameters.append(parsed_date)

    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(50, max(1, int(request.args.get("per_page", "20"))))
    except ValueError:
        return jsonify({"error": "page and per_page must be integers."}), 400
    parameters.extend((per_page, (page - 1) * per_page))

    sql = (
        "SELECT i.item_id, i.title, i.description, i.item_type, i.item_date, "
        "i.status, i.created_at, i.category_id, c.category_name, "
        "i.location_id, l.location_name "
        "FROM Items i JOIN Categories c ON c.category_id = i.category_id "
        "JOIN Locations l ON l.location_id = i.location_id"
    )
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY i.created_at DESC, i.item_id DESC LIMIT %s OFFSET %s"

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, tuple(parameters))
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return jsonify(
        {
            "items": [_serialize_item(row) for row in rows],
            "page": page,
            "per_page": per_page,
        }
    )


@items_bp.get("/mine")
@roles_required("STUDENT", "STAFF")
def my_items():
    """Items reported by the logged-in user, newest first, with claim counts for the owner."""
    user = current_user()
    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(50, max(1, int(request.args.get("per_page", "20"))))
    except ValueError:
        return jsonify({"error": "page and per_page must be integers."}), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT i.item_id, i.title, i.description, i.item_type, i.item_date, "
            "i.status, i.created_at, i.category_id, c.category_name, "
            "i.location_id, l.location_name, "
            "(SELECT COUNT(*) FROM Claims k WHERE k.item_id = i.item_id) AS claim_count, "
            "(SELECT COUNT(*) FROM Claims k WHERE k.item_id = i.item_id "
            "AND k.status = 'PENDING' AND k.finder_decision = 'PENDING') AS claims_awaiting_review "
            "FROM Items i JOIN Categories c ON c.category_id = i.category_id "
            "JOIN Locations l ON l.location_id = i.location_id "
            "WHERE i.user_id = %s "
            "ORDER BY i.created_at DESC, i.item_id DESC LIMIT %s OFFSET %s",
            (user["user_id"], per_page, (page - 1) * per_page),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    items = []
    for row in rows:
        item = _serialize_item(row)
        item["claim_count"] = int(row["claim_count"])
        item["claims_awaiting_review"] = int(row["claims_awaiting_review"])
        items.append(item)
    return jsonify({"items": items, "page": page, "per_page": per_page})


@items_bp.get("/<int:item_id>")
def get_item(item_id):
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT i.item_id, i.title, i.description, i.item_type, i.item_date, "
            "i.status, i.created_at, i.category_id, c.category_name, "
            "i.location_id, l.location_name "
            "FROM Items i JOIN Categories c ON c.category_id = i.category_id "
            "JOIN Locations l ON l.location_id = i.location_id "
            "WHERE i.item_id = %s",
            (item_id,),
        )
        item = cursor.fetchone()
        if item is None:
            return jsonify({"error": "Item not found."}), 404
        cursor.execute(
            "SELECT image_id FROM Item_Images WHERE item_id = %s ORDER BY image_id",
            (item_id,),
        )
        image_ids = [row["image_id"] for row in cursor.fetchall()]
    finally:
        cursor.close()
    result = _serialize_item(item)
    result["images"] = [
        {"image_id": image_id, "url": f"/api/items/{item_id}/images/{image_id}"}
        for image_id in image_ids
    ]
    return jsonify({"item": result})


@items_bp.get("/<int:item_id>/images/<int:image_id>")
def get_item_image(item_id, image_id):
    connection = get_db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT image_data, mime_type FROM Item_Images "
            "WHERE item_id = %s AND image_id = %s",
            (item_id, image_id),
        )
        image = cursor.fetchone()
    finally:
        cursor.close()
    if image is None:
        return jsonify({"error": "Image not found."}), 404
    response = Response(image[0], mimetype=image[1])
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@items_bp.post("")
@roles_required("STUDENT", "STAFF")
def create_item():
    values, error = _parse_item_values(request.form, required=True)
    if error:
        return jsonify({"error": error}), 400
    item_type = request.form.get("item_type", "").upper()
    if item_type not in ITEM_TYPES:
        return jsonify({"error": "item_type must be LOST or FOUND."}), 400
    images, error = _read_uploaded_images(request.files.getlist("images"))
    if error:
        return jsonify({"error": error}), 400

    user = current_user()
    connection = get_db()
    cursor = connection.cursor()
    try:
        with transaction(connection):
            cursor.execute(
                "SELECT category_id FROM Categories WHERE category_id = %s",
                (values["category_id"],),
            )
            if cursor.fetchone() is None:
                return jsonify({"error": "category_id does not identify an existing category."}), 400
            cursor.execute(
                "SELECT location_id FROM Locations WHERE location_id = %s",
                (values["location_id"],),
            )
            if cursor.fetchone() is None:
                return jsonify({"error": "location_id does not identify an existing location."}), 400
            cursor.execute(
                "INSERT INTO Items "
                "(user_id, category_id, location_id, title, description, item_type, item_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    user["user_id"],
                    values["category_id"],
                    values["location_id"],
                    values["title"],
                    values["description"],
                    item_type,
                    values["item_date"],
                ),
            )
            item_id = cursor.lastrowid
            for data, mime_type in images:
                cursor.execute(
                    "INSERT INTO Item_Images (item_id, image_data, mime_type) "
                    "VALUES (%s, %s, %s)",
                    (item_id, data, mime_type),
                )
    finally:
        cursor.close()
    return jsonify({"item_id": item_id, "message": "Item reported successfully."}), 201


@items_bp.patch("/<int:item_id>")
@roles_required("STUDENT", "STAFF")
def edit_item(item_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not body:
        return jsonify({"error": "A non-empty JSON request body is required."}), 400
    values, error = _parse_item_values(body, required=False)
    if error:
        return jsonify({"error": error}), 400
    if not values:
        return jsonify({"error": "At least one editable item field is required."}), 400

    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        with transaction(connection):
            cursor.execute(
                "SELECT user_id, status FROM Items WHERE item_id = %s FOR UPDATE",
                (item_id,),
            )
            item = cursor.fetchone()
            if item is None:
                return jsonify({"error": "Item not found."}), 404
            if item["user_id"] != user["user_id"]:
                return jsonify({"error": "You can only edit your own items."}), 403
            if item["status"] != "ACTIVE":
                return jsonify({"error": "Only ACTIVE items can be edited."}), 409
            if "category_id" in values:
                cursor.execute(
                    "SELECT category_id FROM Categories WHERE category_id = %s",
                    (values["category_id"],),
                )
                if cursor.fetchone() is None:
                    return jsonify({"error": "category_id does not identify an existing category."}), 400
            if "location_id" in values:
                cursor.execute(
                    "SELECT location_id FROM Locations WHERE location_id = %s",
                    (values["location_id"],),
                )
                if cursor.fetchone() is None:
                    return jsonify({"error": "location_id does not identify an existing location."}), 400
            assignments = ", ".join(f"{column} = %s" for column in values)
            cursor.execute(
                f"UPDATE Items SET {assignments} WHERE item_id = %s",
                tuple(values.values()) + (item_id,),
            )
    finally:
        cursor.close()
    return jsonify({"message": "Item updated successfully."})


@items_bp.post("/<int:item_id>/close")
@roles_required("STUDENT", "STAFF")
def close_item(item_id):
    user = current_user()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    try:
        with transaction(connection):
            cursor.execute(
                "SELECT user_id, status FROM Items WHERE item_id = %s FOR UPDATE",
                (item_id,),
            )
            item = cursor.fetchone()
            if item is None:
                return jsonify({"error": "Item not found."}), 404
            if item["user_id"] != user["user_id"]:
                return jsonify({"error": "You can only close your own items."}), 403
            if item["status"] != "ACTIVE":
                return jsonify({"error": "Only ACTIVE items can be closed."}), 409
            cursor.execute("UPDATE Items SET status = 'CLOSED' WHERE item_id = %s", (item_id,))
    finally:
        cursor.close()
    return jsonify({"message": "Item closed successfully."})
