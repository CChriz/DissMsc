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


# VIOLATION V1: create endpoint uses wrong method AND wrong path
# Correct: POST /users  |  Current: GET /users/new
@app.route("/users/new", methods=["GET"])
def create_user():
    """Create a new user.

    VIOLATION V1: Route is GET /users/new — should be POST /users.
    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    data = request.get_json(force=True) or {}
    if "email" not in data:
        # VIOLATION V6: bare string error, not JSON schema
        # VIOLATION V4: should be 400, not 500
        return "Not found", 500
    rid = _new_id()
    record = {
        "user_id": rid,
        "email": data["email"],
        "role": data.get("role"),
        "is_active": data.get("is_active", False),
    }
    _users[rid] = record
    # VIOLATION V4: should be 201, not 200
    return jsonify(record), 200


@app.route("/users", methods=["GET"])
def list_users():
    """List users.

    VIOLATION V3: No pagination — returns entire dataset unconditionally.
    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    # BUG V3: no page/page_size parameters — returns everything
    items = list(_users.values())
    return jsonify({"users": items, "count": len(items)})


@app.route("/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID.

    VIOLATION V5: Route missing /api/v1/ prefix.
    VIOLATION V4+V6: not-found returns bare string with wrong status.
    """
    record = _users.get(item_id)
    if record is None:
        # VIOLATION V6: bare string, not JSON error schema
        # VIOLATION V4: should be 404, not 200
        return "Not found", 200
    return jsonify(record)


@app.route("/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user.

    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    record = _users.get(item_id)
    if record is None:
        # VIOLATION V6: bare string error
        return "Not found", 404
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "user_id"})
    _users[item_id] = record
    return jsonify(record)


@app.route("/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user.

    VIOLATION V5: Route missing /api/v1/ prefix.
    VIOLATION V4: should return 204, not 200.
    """
    record = _users.pop(item_id, None)
    if record is None:
        # VIOLATION V6: bare string error
        return "Not found", 404
    # VIOLATION V4: should be 204, not 200
    return jsonify({"deleted": True}), 200


# VIOLATION V2: camelCase route and function name
@app.route("/users/createPost", methods=["GET"])
def createPost():
    """Search/filter users.

    VIOLATION V2: Route and function use camelCase name 'createPost'.
                  Should be /search with function 'search_users'.
    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    filter_val = request.args.get("role")
    results = [
        item for item in _users.values()
        if filter_val is None or str(item.get("role")) == str(filter_val)
    ]
    return jsonify({"users": results})


@app.route("/users/health", methods=["GET"])
def health_check():
    """Health check.

    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    return jsonify({"status": "ok", "service": "User Management API"})


@app.route("/users/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics.

    VIOLATION V4: Returns 500 for bad client input (should be 400).
    VIOLATION V5: Route missing /api/v1/ prefix.
    VIOLATION V6: bare string error response.
    """
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        # VIOLATION V4+V6: should be 400 with JSON error schema
        return "Not found", 500
    counts: dict = {}
    for item in _users.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({"group_by": group_by, "counts": counts, "total": len(_users)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
