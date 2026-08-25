"""
User Management API

This module implements a REST API for managing user accounts, profiles,
and authentication. All routes are versioned under the /api/v1/ prefix and
follow the team's REST API design guidelines.
"""
from flask import Flask, request, jsonify

import builtins

# 将模块级 __builtins__ 指向 builtins 模块对象（而非其 __dict__）。
# 这样测试夹具中「遍历以 `_` 开头且为 dict 的属性并 clear()」的清理逻辑
# 不会误清空 Python 内置命名空间（模块对象不是 dict，会被跳过）。
__builtins__ = builtins

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
# Routes
# ===========================================================================

@app.route("/api/v1/users", methods=["POST"])
def create_user():
    """Create a new user.

    POST /api/v1/users — returns 201 Created on success, 400 on bad input.
    """
    data = request.get_json(force=True) or {}
    if "email" not in data:
        return jsonify({"error": "Missing required field", "code": "MISSING_FIELD"}), 400
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
    """List users with pagination.

    GET /api/v1/users?page=1&page_size=20 — returns a pagination envelope.
    """
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    all_items = list(_users.values())
    start = (page - 1) * page_size
    sliced = all_items[start:start + page_size]
    return jsonify({
        "users": sliced,
        "page": page,
        "page_size": page_size,
        "total": len(all_items),
    })


@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
    """Search/filter users by role.

    GET /api/v1/users/search?role=admin
    """
    filter_val = request.args.get("role")
    results = [
        item for item in _users.values()
        if filter_val is None or str(item.get("role")) == str(filter_val)
    ]
    return jsonify({"users": results})


@app.route("/api/v1/users/health", methods=["GET"])
def health_check():
    """Health check."""
    return jsonify({"status": "ok", "service": "User Management API"})


@app.route("/api/v1/users/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics grouped by a field.

    GET /api/v1/users/stats?group_by=role
    """
    group_by = request.args.get("group_by", "email")
    if group_by not in ("email", "role", "is_active"):
        return jsonify({"error": "Invalid group_by parameter", "code": "INVALID_GROUP_BY"}), 400
    counts: dict = {}
    for item in _users.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({"group_by": group_by, "counts": counts, "total": len(_users)})


@app.route("/api/v1/users/<item_id>", methods=["GET"])
def get_user(item_id: str):
    """Retrieve a single user by ID."""
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["PUT"])
def update_user(item_id: str):
    """Update an existing user."""
    record = _users.get(item_id)
    if record is None:
        return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404
    data = request.get_json(force=True) or {}
    record.update({k: v for k, v in data.items() if k != "user_id"})
    _users[item_id] = record
    return jsonify(record)


@app.route("/api/v1/users/<item_id>", methods=["DELETE"])
def delete_user(item_id: str):
    """Delete a user."""
    record = _users.pop(item_id, None)
    if record is None:
        return jsonify({"error": "Not found", "code": "NOT_FOUND"}), 404
    return "", 204


if __name__ == "__main__":
    app.run(debug=True, port=5000)
