"""
User Management API

This module implements a REST API for managing user accounts, profiles, and authentication.

All routes are under the /api/v1/ prefix following REST API design guidelines.
"""
import builtins as _builtins_mod

# Rebind __builtins__ to the module object so the reset_store test fixture
# (which calls .clear() on every module-level dict attr starting with '_')
# does not destroy the builtin namespace shared across all modules.
# Without this the fixture would strip isinstance, str, BaseException, etc.
# from the running interpreter.
__builtins__ = _builtins_mod

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


_ERROR_CODE_MAP: dict = {400: "BAD_REQUEST", 404: "NOT_FOUND"}


def _error(message: str, http_status: int):
    """Return a JSON error response with consistent schema.

    The ``code`` field uses a SCREAMING_SNAKE_CASE string per G6.
    """
    return jsonify({"error": message, "code": _ERROR_CODE_MAP.get(http_status, str(http_status))}), http_status


# ==========================================================================
# Routes — ordered so that static segments (search, health, stats) match
# before the parameterised <item_id> segment.
# ==========================================================================


@app.route("/api/v1/users", methods=["POST"])
def create_user():
    """Create a new user.

    Returns 201 Created on success, 400 on missing required fields.
    """
    data = request.get_json(force=True) or {}
    if "email" not in data:
        return _error("Missing required field: email", 400)
    rid = _new_id()
    record = {
        "id": rid,
        "email": data["email"],
        "role": data.get("role"),
        "is_active": data.get("is_active", False),
    }
    _users[rid] = record
    return jsonify(record), 201


@app.route("/api/v1/users", methods=["GET"])
def list_users():
    """List users with pagination support.

    Query params:
        page     — page number (default 1)
        page_size — items per page (default 20)

    Response envelope: {"users": [...], "page": <int>, "page_size": <int>, "total": <int>}
    """
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    items = list(_users.values())
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    items = items[start:end]
    return jsonify({"users": items, "page": page, "page_size": page_size, "total": total})


@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
    """Search/filter users by optional ``role`` query parameter."""
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


@app.route("/api/v1/users/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics grouped by a field.

    Query params:
        group_by — one of "email", "role", "is_active" (default "email")

    Returns 400 for invalid group_by values.
    """
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        return _error("Invalid group_by parameter", 400)
    counts: dict = {}
    for item in _users.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({"group_by": group_by, "counts": counts, "total": len(_users)})


@app.route("/api/v1/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID.

    Returns 404 with JSON error when the user is not found.
    """
    record = _users.get(item_id)
    if record is None:
        return _error("User not found", 404)
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user.

    Returns 404 with JSON error when the user is not found.
    The ``id`` field in the request body is ignored (immutable).
    """
    record = _users.get(item_id)
    if record is None:
        return _error("User not found", 404)
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "id"})
    _users[item_id] = record
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user.

    Returns 204 No Content on success, 404 with JSON error when not found.
    """
    record = _users.pop(item_id, None)
    if record is None:
        return _error("User not found", 404)
    return "", 204


if __name__ == "__main__":
    app.run(debug=True, port=5000)
