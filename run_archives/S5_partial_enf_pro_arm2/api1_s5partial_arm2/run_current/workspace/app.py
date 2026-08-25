"""
UserService: Flask API with v1/v2 versioning.

v2 endpoints are the canonical implementation.
Some v1 routes need backward-compatibility shims.
See compat_matrix.md for which endpoints need shims, no-shim, or removal.
"""
from __future__ import annotations

from flask import Flask, jsonify, request, abort

app = Flask(__name__)

# ── Seed data (in-memory for testing) ─────────────────────────────────────────
SEED_DATA = {
    1: {
        "user_id": 1,
        "display_name": "Sample User One",
        "active": True,
        "meta": {"created_at": "2025-01-01T00:00:00Z"},
    },
    2: {
        "user_id": 2,
        "display_name": "Sample User Two",
        "active": True,
        "meta": {"created_at": "2025-02-01T00:00:00Z"},
    },
}


# ════════════════════════════════════════════════════════════════════════════
# v2 endpoints — canonical implementation
# ════════════════════════════════════════════════════════════════════════════

# E1 v2: Get user profile — uses new field name `display_name`
@app.route("/v2/users/<int:uid>")
def v2_get_user(uid=None, pid=None, oid=None, rid=None, sid=None):
    item_id = uid or pid or oid or rid or sid or 1
    item = SEED_DATA.get(int(str(item_id)), SEED_DATA[1])
    return jsonify({
        "user_id": item["user_id"],
        "display_name": item["display_name"],
        "active": item["active"],
    })


# E2 v2: Get user preferences — uses nested response shape
@app.route("/v2/users/<int:uid>/preferences")
def v2_get_preferences(uid=None, pid=None, oid=None, rid=None, sid=None):
    return jsonify({"preferences": {"theme": "dark", "lang": "en"}, "version": 2})


# E3 v2: Search users — requires `page` parameter
@app.route("/v2/users/search")
def v2_search_users():
    param = request.args.get("page")
    if param is None:
        abort(400, description="Missing required parameter: page")
    q = request.args.get("q", "")
    return jsonify({
        "results": [v for v in SEED_DATA.values()
                    if q.lower() in str(v).lower()],
        "page": param,
    })


# E4 v2: Get user tokens (auth required) — enforces authentication
@app.route("/v2/users/<int:uid>/tokens")
def v2_get_tokens(uid=None, pid=None, oid=None, rid=None, sid=None):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        abort(401, description="Authentication required")
    return jsonify({"data": [], "authenticated": True})


# E5 v2 replacement: canonical new endpoint
@app.route("/v2/users/export")
def v2_export():
    return jsonify({"export": list(SEED_DATA.values()), "format": "v2"})


# ════════════════════════════════════════════════════════════════════════════
# v1 backward-compatibility shims
# Status: COMPLETE — E1/E2/E3 shims active, E4 intentionally omitted, E5 removed
# ════════════════════════════════════════════════════════════════════════════

# E1 v1 shim: maps `display_name` -> `full_name` to preserve v1 contract
@app.route("/v1/users/<int:uid>")
def v1_get_user(uid):
    resp = v2_get_user(uid)
    data = resp.get_json()
    if resp.status_code == 200 and "display_name" in data:
        data["full_name"] = data.pop("display_name")
    return jsonify(data), resp.status_code


# E2 v1 shim: flattens nested v2 response back to v1 flat shape
@app.route("/v1/users/<int:uid>/preferences")
def v1_get_preferences(uid):
    resp = v2_get_preferences(uid)
    data = resp.get_json()
    if resp.status_code == 200:
        flat_data = data.get("preferences", {})
        return jsonify(flat_data)
    return jsonify(data), resp.status_code


# E3 v1 shim: supplies default page=1 when v1 clients omit the parameter
@app.route("/v1/users/search")
def v1_search_users():
    page = request.args.get("page", "1")
    q = request.args.get("q", "")
    return jsonify({
        "results": [v for v in SEED_DATA.values()
                    if q.lower() in str(v).lower()],
        "page": page,
    })


# E4: NO v1 shim — v1 returned tokens without auth check; v2 requires Bearer token.
# A v1 shim here would be a security regression. Do NOT add one.


if __name__ == "__main__":
    app.run(port=8000, debug=False)
