"""
Integration tests for the fixed User Management API.

These tests validate the API after ALL design violations have been corrected:
  V1: create uses POST
  V2: search route is snake_case
  V3: list endpoint supports pagination
  V4: correct status codes (201 create, 404 not-found, 204 delete, 400 client-error)
  V5: all routes under /api/v1/
  V6: all error responses are JSON with "error" and "code" keys
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app as flask_app


@pytest.fixture(autouse=True)
def reset_store():
    """Reset in-memory store before each test."""
    import app as app_module
    for attr in dir(app_module):
        if attr.startswith("_") and isinstance(getattr(app_module, attr), dict):
            obj = getattr(app_module, attr)
            if not callable(obj):
                obj.clear()
    yield


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ── V5: All routes under /api/v1/ ────────────────────────────────────────────

def test_list_route_versioned(client):
    """GET /api/v1/users must exist and return 200."""
    resp = client.get("/api/v1/users")
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}. "
        "Route may be missing /api/v1/ prefix (V5 not fixed)."
    )


def test_health_route_versioned(client):
    """Health check must be under /api/v1/."""
    resp = client.get("/api/v1/users/health")
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}. Health route missing /api/v1/ prefix."
    )
    data = resp.get_json()
    assert data is not None and "status" in data


# ── V1: Create uses POST ──────────────────────────────────────────────────────

def test_create_uses_post(client):
    """POST /api/v1/users must be accepted (not 405)."""
    resp = client.post("/api/v1/users", json={"email": "admin@example.com", "role": "admin"})
    assert resp.status_code != 405, (
        "POST returned 405 Method Not Allowed — V1 not fixed (create still uses wrong method)."
    )


def test_get_method_not_create(client):
    """GET /api/v1/users must list resources, not create (idempotent)."""
    # Two GETs in a row must not increase count
    r1 = client.get("/api/v1/users")
    r2 = client.get("/api/v1/users")
    d1 = r1.get_json()
    d2 = r2.get_json()
    assert d1 == d2, "GET is not idempotent — it may be mutating state (V1 issue)."


# ── V4: Correct status codes ──────────────────────────────────────────────────

def test_create_returns_201(client):
    """POST must return 201 Created."""
    resp = client.post("/api/v1/users", json={"email": "admin@example.com", "role": "admin"})
    assert resp.status_code == 201, (
        f"Expected 201, got {resp.status_code} — V4 create status not fixed."
    )


def test_not_found_returns_404(client):
    """GET on missing resource must return 404."""
    resp = client.get("/api/v1/users/nonexistent_xyz_999")
    assert resp.status_code == 404, (
        f"Expected 404, got {resp.status_code} — V4 not-found status not fixed."
    )


def test_delete_returns_204(client):
    """DELETE must return 204 No Content."""
    # Create first
    cr = client.post("/api/v1/users", json={"email": "admin@example.com", "role": "admin"})
    assert cr.status_code == 201
    created = cr.get_json()
    item_id = next(v for k, v in created.items() if "id" in k.lower())
    dr = client.delete(f"/api/v1/users/{item_id}")
    assert dr.status_code == 204, (
        f"Expected 204, got {dr.status_code} — V4 delete status not fixed."
    )


def test_client_error_returns_400(client):
    """POST with missing required field must return 400."""
    resp = client.post("/api/v1/users", json={})
    assert resp.status_code == 400, (
        f"Expected 400, got {resp.status_code} — V4 client-error status not fixed."
    )


# ── V6: JSON error schema ─────────────────────────────────────────────────────

def test_not_found_error_is_json(client):
    """404 response must be JSON with 'error' and 'code' fields."""
    resp = client.get("/api/v1/users/no_such_id_abc")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data is not None, "404 must return JSON body, not a plain string (V6 not fixed)."
    assert "error" in data, f"JSON error body must have 'error' key. Got: {data}"
    assert "code" in data, f"JSON error body must have 'code' key. Got: {data}"


def test_bad_request_error_is_json(client):
    """400 response must be JSON with 'error' and 'code' fields."""
    resp = client.post("/api/v1/users", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data is not None, "400 must return JSON body (V6 not fixed)."
    assert "error" in data, f"JSON error body must have 'error' key. Got: {data}"
    assert "code" in data, f"JSON error body must have 'code' key. Got: {data}"


# ── V3: Pagination ────────────────────────────────────────────────────────────

def test_list_accepts_pagination_params(client):
    """List endpoint must accept page and page_size query params."""
    resp = client.get("/api/v1/users?page=1&page_size=10")
    assert resp.status_code == 200, (
        f"GET with pagination params returned {resp.status_code} — V3 not fixed."
    )


def test_list_respects_page_size(client):
    """List with page_size=2 must return at most 2 items."""
    # Seed 5 records
    for i in range(5):
        client.post("/api/v1/users", json={"email": f"val_{i}", "role": "admin"})
    resp = client.get("/api/v1/users?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.get_json()
    items_key = "users" if "users" in data else "items"
    if items_key in data:
        assert len(data[items_key]) <= 2, (
            f"Expected <=2 items with page_size=2, got {len(data[items_key])} — V3 not fixed."
        )


def test_list_response_has_total(client):
    """List response must include a 'total' count field (pagination envelope)."""
    resp = client.get("/api/v1/users?page=1&page_size=10")
    data = resp.get_json()
    assert "total" in data, (
        f"List response missing 'total' field — pagination envelope not implemented (V3)."
    )


# ── V2: snake_case routes ─────────────────────────────────────────────────────

def test_search_route_snake_case(client):
    """Search route must be /search (snake_case), not a camelCase name."""
    resp = client.get("/api/v1/users/search")
    assert resp.status_code != 404, (
        "GET /api/v1/users/search returned 404 — snake_case search route not implemented (V2 not fixed)."
    )
    assert resp.status_code == 200


def test_update_and_get(client):
    """Basic create->get->update->get round-trip under /api/v1/."""
    cr = client.post("/api/v1/users", json={"email": "admin@example.com", "role": "admin"})
    assert cr.status_code == 201
    created = cr.get_json()
    item_id = next(v for k, v in created.items() if "id" in k.lower())

    gr = client.get(f"/api/v1/users/{item_id}")
    assert gr.status_code == 200

    ur = client.put(f"/api/v1/users/{item_id}", json={"email": "updated_value"})
    assert ur.status_code == 200
    assert ur.get_json()["email"] == "updated_value"
