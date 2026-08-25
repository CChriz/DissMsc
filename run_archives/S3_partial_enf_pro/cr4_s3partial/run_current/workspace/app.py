"""
User Management API

This module implements a REST API for manages user accounts, profiles, and authentication.

NOTE: This file contains API design issues identified in code review.
See the review report for the full list of violations that must be fixed.
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
# VIOLATION SUMMARY (all must be fixed):
#   V1: create_user is at "/users/new" with method GET instead of
#       POST at "/users"
#   V2: search route is "/users/createPost" (camelCase) instead of
#       "/users/search" with snake_case function name
#   V3: list_users returns all records with no pagination
#   V4: wrong status codes — create returns 200 (need 201),
#       not-found returns 200 (need 404),
#       delete returns 200 (need 204),
#       client errors return 500 (need 400)
#   V5: all routes use prefix "/users" instead of /api/v1/users
#   V6: error responses are bare strings, not JSON {error, code} objects
# ===========================================================================


# V1 FIXED: create endpoint now uses POST at /api/v1/users
# V5 FIXED: route includes /api/v1/ prefix
@app.route("/api/v1/users", methods=["POST"])
def create_user():
    """Create a new user."""
    data = request.get_json(force=True) or {}
    if "email" not in data:
        # V6 FIXED: JSON error schema
        # V4 FIXED: 400 instead of 500
        return jsonify({"error": "Missing required fields", "code": "BAD_REQUEST"}), 400
    rid = _new_id()
    record = {
        "user_id": rid,
        "email": data["email"],
        "role": data.get("role"),
        "is_active": data.get("is_active", False),
    }
    _users[rid] = record
    # V4 FIXED: 201 instead of 200
    return jsonify(record), 201


# V5 FIXED: route includes /api/v1/ prefix
# V3 FIXED: pagination support with page, page_size, total
@app.route("/api/v1/users", methods=["GET"])
def list_users():
    """List users with pagination."""
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


# V5 FIXED: route includes /api/v1/ prefix
@app.route("/api/v1/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID."""
    record = _users.get(item_id)
    if record is None:
        # V6 FIXED: JSON error schema
        # V4 FIXED: 404 instead of 200
        return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404
    return jsonify(record)


# V5 FIXED: route includes /api/v1/ prefix
@app.route("/api/v1/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user."""
    record = _users.get(item_id)
    if record is None:
        # V6 FIXED: JSON error schema
        return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "user_id"})
    _users[item_id] = record
    return jsonify(record)


# V5 FIXED: route includes /api/v1/ prefix
@app.route("/api/v1/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user."""
    record = _users.pop(item_id, None)
    if record is None:
        # V6 FIXED: JSON error schema
        return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404
    # V4 FIXED: 204 No Content with empty body
    return "", 204


# V2 FIXED: camelCase route and function renamed to snake_case
# V5 FIXED: route includes /api/v1/ prefix
@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
    """Search/filter users by role."""
    filter_val = request.args.get("role")
    results = [
        item for item in _users.values()
        if filter_val is None or str(item.get("role")) == str(filter_val)
    ]
    return jsonify({"users": results})


# V5 FIXED: route includes /api/v1/ prefix
@app.route("/api/v1/users/health", methods=["GET"])
def health_check():
    """Health check."""
    return jsonify({"status": "ok", "service": "User Management API"})


# V5 FIXED: route includes /api/v1/ prefix
@app.route("/api/v1/users/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics."""
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        # V4 FIXED: 400 instead of 500
        # V6 FIXED: JSON error schema
        return jsonify({"error": "Invalid group_by parameter", "code": "BAD_REQUEST"}), 400
    counts: dict = {}
    for item in _users.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({"group_by": group_by, "counts": counts, "total": len(_users)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
