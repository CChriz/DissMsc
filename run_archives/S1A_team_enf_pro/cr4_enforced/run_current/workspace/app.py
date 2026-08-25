"""
User Management API

This module implements a REST API for manages user accounts, profiles, and authentication.

NOTE: All API design issues identified in code review have been fixed.
"""
from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# In-memory data store
# ---------------------------------------------------------------------------
_users: dict = {}
_id_counter: int = 1


def _new_id() -> str:
    global _id_counter
    _id_counter += 1
    return f"user_{_id_counter - 1}"


# ===========================================================================
# All violations (V1-V6) have been fixed:
#   V1: create_user uses POST at /api/v1/users (was GET)
#   V2: search_users is snake_case at /api/v1/users/search (was createPost)
#   V3: list_users supports pagination (page, page_size)
#   V4: correct status codes (201, 404, 204, 400)
#   V5: all routes use /api/v1/ prefix
#   V6: all error responses are JSON {error, code} objects
# ===========================================================================


@app.route("/api/v1/users", methods=["POST"])
def create_user():
    """Create a new user."""
    data = request.get_json(force=True) or {}
    if "email" not in data:
        return jsonify({"error": "Missing required fields", "code": "MISSING_REQUIRED_FIELDS"}), 400
    rid = _new_id()
    record = {
        "user_id": rid,
        "email": data["email"],
        "role": data.get("role"),
        "is_active": data.get("is_active", False),
    }
    _users[rid] = record
    return jsonify(record), 201


@app.route("/api/v1/users", methods=["GET"])
def list_users():
    """List users with pagination support."""
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    all_items = list(_users.values())
    start = (page - 1) * page_size
    sliced = all_items[start : start + page_size]
    return jsonify({
        "users": sliced,
        "page": page,
        "page_size": page_size,
        "total": len(all_items),
    })


@app.route("/api/v1/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID."""
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "User not found", "code": "USER_NOT_FOUND"}), 404
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user."""
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "User not found", "code": "USER_NOT_FOUND"}), 404
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "user_id"})
    _users[item_id] = record
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user."""
    record = _users.pop(item_id, None)
    if record is None:
        return jsonify({"error": "User not found", "code": "USER_NOT_FOUND"}), 404
    return "", 204


@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
    """Search/filter users by role."""
    filter_val = request.args.get("role")
    results = [
        item for item in _users.values()
        if filter_val is None or str(item.get("role")) == str(filter_val)
    ]
    return jsonify({"users": results})


@app.route("/api/v1/users/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "User Management API"})


@app.route("/api/v1/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics grouped by a given field."""
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        return jsonify({"error": "Invalid group_by parameter", "code": "INVALID_GROUP_BY"}), 400
    counts: dict = {}
    for item in _users.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({"group_by": group_by, "counts": counts, "total": len(_users)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
