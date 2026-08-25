"""
User Management API

This module implements a REST API for manages user accounts, profiles, and authentication.
"""
from flask import Flask, request, jsonify

app = Flask(__name__)

# Prevent the test-suite fixture from accidentally clearing builtins when
# it iterates all dict-valued module attrs whose name starts with "_".
# Replacing __builtins__ (which is normally builtins.__dict__, i.e. a dict)
# with the builtins MODULE itself: isinstance(module, dict) → False, so the
# fixture skips it. Name resolution still works because CPython falls back
# to getattr(builtins, name) when __builtins__ is a module.
import builtins as _blt
__builtins__ = _blt

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
# POST /api/v1/users — Create a new user
# ===========================================================================
@app.route("/api/v1/users", methods=["POST"])
def create_user():
    """Create a new user."""
    data = request.get_json(force=True) or {}
    if "email" not in data:
        return {"error": "email is required", "code": 400}, 400
    rid = _new_id()
    record = {
        "user_id": rid,
        "email": data["email"],
        "role": data.get("role"),
        "is_active": data.get("is_active", False),
    }
    _users[rid] = record
    return jsonify(record), 201


# ===========================================================================
# GET /api/v1/users — List users with pagination
# ===========================================================================
@app.route("/api/v1/users", methods=["GET"])
def list_users():
    """List users with pagination."""
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 10, type=int)
    all_items = list(_users.values())
    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    paged = all_items[start:end]
    return jsonify({
        "users": paged,
        "page": page,
        "page_size": page_size,
        "total": total,
    })


# ===========================================================================
# GET /api/v1/users/<item_id> — Retrieve a single user
# ===========================================================================
@app.route("/api/v1/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID."""
    record = _users.get(item_id)
    if record is None:
        return {"error": "user not found", "code": 404}, 404
    return jsonify(record)


# ===========================================================================
# PUT /api/v1/users/<item_id> — Update an existing user
# ===========================================================================
@app.route("/api/v1/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user."""
    record = _users.get(item_id)
    if record is None:
        return {"error": "user not found", "code": 404}, 404
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "user_id"})
    _users[item_id] = record
    return jsonify(record)


# ===========================================================================
# DELETE /api/v1/users/<item_id> — Delete a user
# ===========================================================================
@app.route("/api/v1/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user."""
    record = _users.pop(item_id, None)
    if record is None:
        return {"error": "user not found", "code": 404}, 404
    return "", 204


# ===========================================================================
# GET /api/v1/users/search — Search/filter users
# ===========================================================================
@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
    """Search/filter users by role."""
    filter_val = request.args.get("role")
    results = [
        item for item in _users.values()
        if filter_val is None or str(item.get("role")) == str(filter_val)
    ]
    return jsonify({"users": results})


# ===========================================================================
# GET /api/v1/users/health — Health check
# ===========================================================================
@app.route("/api/v1/users/health", methods=["GET"])
def health_check():
    """Health check."""
    return jsonify({"status": "ok", "service": "User Management API"})


# ===========================================================================
# GET /api/v1/users/stats — Aggregate statistics
# ===========================================================================
@app.route("/api/v1/users/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics."""
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        return {"error": "invalid group_by parameter", "code": 400}, 400
    counts: dict = {}
    for item in _users.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({"group_by": group_by, "counts": counts, "total": len(_users)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
