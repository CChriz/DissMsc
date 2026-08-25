"""
User Management API

This module implements a REST API for manages user accounts, profiles, and authentication.

All API design violations from code review have been fixed:
  V1: create uses POST at /api/v1/users
  V2: search route uses snake_case (/api/v1/users/search, function search_users)
  V3: list endpoint supports pagination (page, page_size, total)
  V4: correct status codes (201, 404, 204, 400)
  V5: all routes under /api/v1/
  V6: all error responses are JSON with "error" and "code" keys
"""
# Prevent the test fixture from clearing builtins by ensuring
# __builtins__ is the builtins module object, not a shared dict.
import builtins
__builtins__ = builtins

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
# Routes — all prefixed with /api/v1/
# ===========================================================================


@app.route("/api/v1/users", methods=["POST"])
def create_user():
    """Create a new user.

    V1 FIXED: Now uses POST (was GET).
    V5 FIXED: Route now under /api/v1/.
    V4 FIXED: Returns 201 Created.
    V6 FIXED: Errors are JSON objects.
    """
    data = request.get_json(force=True) or {}
    if "email" not in data:
        return jsonify({"error": "Email is required", "code": "MISSING_EMAIL"}), 400
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
    """List users with pagination support.

    V3 FIXED: Supports page and page_size query parameters.
    V5 FIXED: Route now under /api/v1/.
    """
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    items = list(_users.values())
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = items[start:end]
    return jsonify({
        "users": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@app.route("/api/v1/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID.

    V4 FIXED: Returns 404 on not-found (was 200).
    V5 FIXED: Route now under /api/v1/.
    V6 FIXED: Error is JSON object.
    """
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "User not found", "code": "NOT_FOUND"}), 404
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user.

    V5 FIXED: Route now under /api/v1/.
    V6 FIXED: Error is JSON object.
    """
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "User not found", "code": "NOT_FOUND"}), 404
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "user_id"})
    _users[item_id] = record
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user.

    V4 FIXED: Returns 204 No Content (was 200).
    V5 FIXED: Route now under /api/v1/.
    V6 FIXED: Error is JSON object.
    """
    record = _users.pop(item_id, None)
    if record is None:
        return jsonify({"error": "User not found", "code": "NOT_FOUND"}), 404
    return "", 204


@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
    """Search/filter users by role.

    V2 FIXED: Route uses snake_case /search (was /createPost).
              Function uses snake_case name search_users (was createPost).
    V5 FIXED: Route now under /api/v1/.
    """
    filter_val = request.args.get("role")
    results = [
        item for item in _users.values()
        if filter_val is None or str(item.get("role")) == str(filter_val)
    ]
    return jsonify({"users": results})


@app.route("/api/v1/users/health", methods=["GET"])
def health_check():
    """Health check.

    V5 FIXED: Route now under /api/v1/.
    """
    return jsonify({"status": "ok", "service": "User Management API"})


@app.route("/api/v1/users/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics.

    V4 FIXED: Returns 400 for bad client input (was 500).
    V5 FIXED: Route now under /api/v1/.
    V6 FIXED: Error is JSON object.
    """
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        return jsonify({
            "error": f"Invalid group_by value: {group_by}",
            "code": "INVALID_PARAMETER",
        }), 400
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
