# CR4: API Design Review Fix

## Goal
Fix all three API design violations identified in the code review of `app.py`.
The API must comply with the API Design Guidelines below after your changes.

All existing tests in `tests/test_api.py` must pass.

---

## Module Under Review

**User Management API** — `app.py`

This module manages user accounts, profiles, and authentication.

---

## API Design Guidelines

### G1 — HTTP Methods
| Intent | Method |
|--------|--------|
| Create resource | **POST** |
| Read resource(s) | **GET** |
| Replace resource | **PUT** |
| Partial update | **PATCH** |
| Delete resource | **DELETE** |

Never use GET for operations that mutate state.
Never use PUT or DELETE for creation.

### G2 — Naming Conventions
- All route path segments must use **snake_case** (e.g. `/search_results`, not `/searchResults`)
- Collection endpoints use plural nouns (e.g. `/users`, not `/user`)
- Python function names must mirror their route in snake_case
- A search/filter endpoint must be named `search_users` and routed to `/search`

### G3 — API Versioning
- Every route must be prefixed with `/api/v1/`
- Correct: `GET /api/v1/users`, `POST /api/v1/users`, `DELETE /api/v1/users/<id>`
- Incorrect: `GET /users`, `GET /api/users`, `GET /v1/users`

---

## Code Review Report — `app.py`

The following three violations were identified. **All must be fixed.**

---

### VIOLATION V1 — Wrong HTTP Method (breaks G1)

**Location**: `create_user()` route decorator

**Problem**: The create endpoint is decorated with `methods=["GET"]`.
Creating a new resource is a mutating operation and **must** use POST.

**Required fix**: Change the route decorator to `methods=["POST"]`.

```python
# Before (WRONG):
@app.route("/users", methods=["GET"])
def create_user():

# After (CORRECT):
@app.route("/api/v1/users", methods=["POST"])
def create_user():
```

---

### VIOLATION V2 — camelCase Route and Function Name (breaks G2)

**Location**: Search/filter endpoint — route `/createPost` and function `createPost`

**Problem**: Both the URL path segment and the Python function name use camelCase
(`createPost`). All routes and functions must use snake_case.

**Required fix**: Rename the route to `/search` and the function to `search_users`.

```python
# Before (WRONG):
@app.route("/users/createPost", methods=["GET"])
def createPost():

# After (CORRECT):
@app.route("/api/v1/users/search", methods=["GET"])
def search_users():
```

---

### VIOLATION V3 — Missing `/api/v1/` Prefix (breaks G3)

**Problem**: All routes currently use prefix `"/users"` instead of `/api/v1/users`.

**Required fix**: Update **every** `@app.route(...)` in the file to use the `/api/v1/` prefix.

```python
# Before:
@app.route("/users", ...)
@app.route("/users/<item_id>", ...)

# After:
@app.route("/api/v1/users", ...)
@app.route("/api/v1/users/<item_id>", ...)
```

This applies to ALL eight routes: list, create, get, update, delete, search, health, stats.

---

## Summary of All Required Changes

| # | Violation | Location | Fix |
|---|-----------|----------|-----|
| V1 | `GET` used for create | `create_user()` decorator | Change to `POST` |
| V2 | camelCase route `/createPost` | search route + function | Rename to `/search` + `search_users()` |
| V3 | Missing `/api/v1/` prefix | all 8 routes | Add `/api/v1/` to every route |

## Deliverables
1. `app.py` with all three violations corrected.
2. `tests/test_api.py` must pass without modification.
3. Verifier writes `attestation.json` with `verdict: pass` once all checks pass.
