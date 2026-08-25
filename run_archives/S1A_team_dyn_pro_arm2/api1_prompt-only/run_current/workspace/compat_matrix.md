# API Compatibility Matrix — UserService

## Overview

This matrix documents the v1 -> v2 migration status for all UserService
endpoints. It is the authoritative reference for compatibility decisions.

## Endpoints

| Endpoint | v1 Path | v2 Path | Action | Reason |
|----------|---------|---------|--------|--------|
| E1 (get_user) | `/v1/users/<int:uid>` | `/v2/users/<int:uid>` | **ADD shim** | v2 renames `full_name` -> `display_name` |
| E2 (get_preferences) | `/v1/users/<int:uid>/preferences` | `/v2/users/<int:uid>/preferences` | **ADD shim** | v2 restructures response into nested shape |
| E3 (search_users) | `/v1/users/search` | `/v2/users/search` | **ADD shim** | v2 requires `page` param; v1 clients don't send it |
| E4 (get_tokens) | _(none)_ | `/v2/users/<int:uid>/tokens` | **NO shim** | Security fix: v1 returned tokens without auth check; v2 requires Bearer token |
| E5 (legacy_export) | `/v1/users/legacy_export` | `/v2/users/export` | **REMOVE shim** | All clients migrated to /v2/users/export by 2025-Q1 |

## Shim Specifications

### E1 — Field Rename Shim

v1 clients expect `full_name` in the response.
v2 returns `display_name`.

The v1 shim at `/v1/users/<int:uid>` must:
1. Call the v2 handler (or duplicate its logic)
2. Rename `display_name` -> `full_name` in the response

### E2 — Response Restructure Shim

v1 clients expect a flat response: `{"theme": "dark", "lang": "en"}`
v2 returns a nested response: `{"preferences": {"theme": "dark", "lang": "en"}, "version": 2}`

The v1 shim at `/v1/users/<int:uid>/preferences` must flatten the v2 response back to v1 shape.

### E3 — Added Required Parameter Shim

v2 requires `page` in the query string.
v1 clients do not send this parameter.

The v1 shim at `/v1/users/search` must:
1. Inject `page=1` as the default when absent
2. Forward the request to the v2 handler

### E4 — No Shim (Security Break)

`/v2/users/<int:uid>/tokens` enforces authentication.
**Do NOT create a `/v1/users/<int:uid>/tokens` shim.**
v1 returned tokens without auth check; v2 requires Bearer token.
Adding a shim here would silently re-introduce a security vulnerability.

### E5 — Remove Stale Shim

`/v1/users/legacy_export` currently exists in the codebase but is dead code.
All clients migrated to /v2/users/export by 2025-Q1.
**Remove the `/v1/users/legacy_export` route entirely.**

## Migration Status

- E1, E2, E3: v1 shims missing — clients still on v1 routes will get 404
- E4: correctly has no v1 shim
- E5: v1 shim present but should be removed (dead code, maintenance burden)
