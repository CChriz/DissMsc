# API1_version_compat: API Version Compatibility — Full Specification (Planner Only)

## Overview

The workspace contains `app.py` — a Flask UserService being upgraded from v1 to v2.
**3 endpoints need backward-compatible v1 shims** (add them),
**1 endpoint must NOT have a shim** (security fix),
**1 endpoint's shim must be removed** (clients have migrated).

The executor only receives the brief. This spec provides the full compatibility analysis.

## File Structure

- `app.py` — the ONLY file to modify
- `compat_matrix.md` — compatibility matrix (authoritative reference, do not modify)
- `tests/test_v1_compat.py` — v1 compatibility tests (do not modify)
- `tests/test_v2_endpoints.py` — v2 regression tests (do not modify)
- `requirements.txt` — dependencies

## Compatibility Matrix

| Endpoint | v1 Path | v2 Path | Action |
|----------|---------|---------|--------|
| E1 (get_user) | `/v1/users/<int:uid>` | `/v2/users/<int:uid>` | ADD shim |
| E2 (get_preferences) | `/v1/users/<int:uid>/preferences` | `/v2/users/<int:uid>/preferences` | ADD shim |
| E3 (search_users) | `/v1/users/search` | `/v2/users/search` | ADD shim |
| E4 (get_tokens) | _(none)_ | `/v2/users/<int:uid>/tokens` | NO shim |
| E5 (legacy_export) | `/v1/users/legacy_export` | `/v2/users/export` | REMOVE shim |

## Shim Specifications

### E1 — ADD shim: Field Rename at `/v1/users/<int:uid>`

v2 renames the response field `full_name` -> `display_name`.
v1 clients still expect `full_name`.

Add a route at `/v1/users/<int:uid>` that:
1. Calls the v2 handler logic (or re-uses `v2_get_user`)
2. In the JSON response, renames `display_name` -> `full_name`

Example:
```python
@app.route("/v1/users/<int:uid>")
def v1_get_user(...):
    resp = v2_get_user(...)
    data = resp.get_json()
    data["full_name"] = data.pop("display_name")
    return jsonify(data)
```

### E2 — ADD shim: Response Restructure at `/v1/users/<int:uid>/preferences`

v2 returns: `{"preferences": {"theme": "dark", "lang": "en"}, "version": 2}`
v1 clients expect: `{"theme": "dark", "lang": "en"}`

Add a route at `/v1/users/<int:uid>/preferences` that calls v2 and flattens the nested
response back to the v1 flat shape.

### E3 — ADD shim: Default Parameter at `/v1/users/search`

v2 requires query param `page`. v1 clients don't send it.

Add a route at `/v1/users/search` that injects
`page=1` as default when the param is absent,
then forwards to the v2 handler.

### E4 — NO shim: Security Fix at `/v2/users/<int:uid>/tokens`

**Do NOT create `/v1/users/<int:uid>/tokens`.**
v1 returned tokens without auth check; v2 requires Bearer token.
A v1 shim would silently re-introduce a security vulnerability.
The correct behavior is to return 404 for the v1 path.

### E5 — REMOVE shim: Dead Code at `/v1/users/legacy_export`

The route `/v1/users/legacy_export` currently exists in `app.py` but is dead code.
All clients migrated to /v2/users/export by 2025-Q1.
**Delete the `v1_legacy_export` route function entirely.**

## Acceptance Criteria

1. `GET /v1/users/<int:uid>` (with id=1) returns 200 with `full_name` field (not `display_name`)
2. `GET /v1/users/<int:uid>/preferences` (with id=1) returns 200 with flat v1 shape
3. `GET /v1/users/search` (no params) returns 200 (shim supplies default)
4. `GET /v1/users/<int:uid>/tokens` (with id=1) returns 404 (no shim exists)
5. `GET /v1/users/legacy_export` returns 404 (stale shim removed)
6. All v2 endpoints still return correct responses (regression check)
7. All tests in `tests/` pass

## Authoritative Sources

- This spec is the authoritative reference for compatibility decisions
- `compat_matrix.md` in the workspace provides the same information
- When in doubt: compat_matrix.md > any code comments
