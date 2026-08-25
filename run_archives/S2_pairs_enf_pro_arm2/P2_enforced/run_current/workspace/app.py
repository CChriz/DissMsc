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
# Status: INCOMPLETE — see compat_matrix.md for what needs to be done
# ════════════════════════════════════════════════════════════════════════════

# E1: v1 shim — field rename `display_name` -> `full_name`
@app.route("/v1/users/<int:uid>")
def v1_get_user(uid):
    item = SEED_DATA.get(uid, SEED_DATA[1])
    return jsonify({
        "user_id": item["user_id"],
        "full_name": item["display_name"],
        "active": item["active"],
    })


# E2: v1 shim — flatten nested preferences back to v1 flat shape
@app.route("/v1/users/<int:uid>/preferences")
def v1_get_preferences(uid):
    return jsonify({"theme": "dark", "lang": "en"})


# E3: v1 shim — inject default `page=1` when absent
@app.route("/v1/users/search")
def v1_search_users():
    param = request.args.get("page", "1")
    q = request.args.get("q", "")
    return jsonify({
        "results": [v for v in SEED_DATA.values() if q.lower() in str(v).lower()],
        "page": param,
    })


# E4: NO v1 shim — v1 returned tokens without auth check; v2 requires Bearer token.
# A v1 shim here would be a security regression. Do NOT add one.
# (/v1/users/<int:uid>/tokens must remain 404)


# E5: stale shim /v1/users/legacy_export removed (all clients migrated to /v2/users/export)


if __name__ == "__main__":
    app.run(port=8000, debug=False)
