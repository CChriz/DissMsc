"""
User Management API

This module implements a REST API for managing user accounts, profiles, and authentication.

NOTE: This file originally contained API design issues identified in code review.
All violations (V1-V6) have been fixed per the implementation plan.
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
# ALL VIOLATIONS FIXED:
#   V1: create_user is now POST /api/v1/users (was GET /users/new)
#   V2: search route is now GET /api/v1/users/search, function search_users
#       (was /users/createPost, function createPost — camelCase)
#   V3: list_users now supports pagination via page / page_size query params
#   V4: correct status codes — 201 (created), 404 (not-found),
#       204 (deleted), 400 (bad request)
#   V5: all routes use /api/v1/ prefix
#   V6: error responses are JSON {error, code} objects with
#       SCREAMING_SNAKE_CASE codes, not bare strings
# ===========================================================================


@app.route("/api/v1/users", methods=["GET"])
def list_users():
    """List users with pagination."""
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    all_users = list(_users.values())
    total = len(all_users)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = all_users[start:end]
    return jsonify({
        "users": paginated,
        "page": page,
        "page_size": page_size,
        "total": total,
    })


@app.route("/api/v1/users", methods=["POST"])
def create_user():
    """Create a new user."""
    data = request.get_json(force=True) or {}
    if "email" not in data:
        return jsonify({"error": "Email is required", "code": "BAD_REQUEST"}), 400
    rid = _new_id()
    record = {
        "user_id": rid,
        "email": data["email"],
        "role": data.get("role"),
        "is_active": data.get("is_active", False),
    }
    _users[rid] = record
    return jsonify(record), 201


@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
    """Search/filter users."""
    filter_val = request.args.get("role")
    results = [
        item for item in _users.values()
        if filter_val is None or str(item.get("role")) == str(filter_val)
    ]
    return jsonify({"users": results})


@app.route("/api/v1/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID."""
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "User not found", "code": "NOT_FOUND"}), 404
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user."""
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "User not found", "code": "NOT_FOUND"}), 404
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "user_id"})
    _users[item_id] = record
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user."""
    record = _users.pop(item_id, None)
    if record is None:
        return jsonify({"error": "User not found", "code": "NOT_FOUND"}), 404
    return "", 204


@app.route("/api/v1/health", methods=["GET"])
def health_check():
    """Health check."""
    return jsonify({"status": "ok", "service": "User Management API"})


@app.route("/api/v1/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics."""
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        return jsonify({"error": "Invalid group_by parameter", "code": "BAD_REQUEST"}), 400
    counts: dict = {}
    for item in _users.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({
        "group_by": group_by,
        "counts": counts,
        "total": len(_users),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
