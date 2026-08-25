"""Tests that v1 backward-compatibility shims work correctly.""";
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


class TestV1Shims:
    def test_e1_v1_uses_old_field_name(self, client):
        """v1 response must use `full_name`, not `display_name`.""";
        resp = client.get("/v1/users/<int:uid>".replace("<int:uid>", "1")
                                              .replace("<int:pid>", "1")
                                              .replace("<int:oid>", "1")
                                              .replace("<int:rid>", "1")
                                              .replace("<string:sid>", "abc"))
        assert resp.status_code == 200
        data = resp.get_json()
        assert "full_name" in data, "v1 response must contain 'full_name'"
        assert "display_name" not in data, "v1 response must NOT contain 'display_name'"

    def test_e2_v1_flat_response(self, client):
        """v1 response must be flat (v1 shape), not nested (v2 shape).""";
        resp = client.get("/v1/users/<int:uid>/preferences".replace("<int:uid>", "1")
                                              .replace("<int:pid>", "1")
                                              .replace("<int:oid>", "1")
                                              .replace("<int:rid>", "1")
                                              .replace("<string:sid>", "abc"))
        assert resp.status_code == 200
        data = resp.get_json()
        # v1 shape is flat — must NOT have nested wrapper key
        nested_keys = [k for k, v in data.items() if isinstance(v, dict)]
        assert len(nested_keys) == 0, f"v1 response must be flat, got nested keys: {nested_keys}"

    def test_e3_v1_no_param_required(self, client):
        """v1 search must work without `page` parameter.""";
        resp = client.get("/v1/users/search")
        assert resp.status_code == 200, (
            "v1 search must not require 'page' parameter"
        )

    def test_e4_no_v1_shim(self, client):
        """v1 path for E4 must NOT exist (security fix).""";
        resp = client.get("/v1/users/<int:uid>/tokens".replace("<int:uid>", "1")
                                              .replace("<int:pid>", "1")
                                              .replace("<int:oid>", "1")
                                              .replace("<int:rid>", "1")
                                              .replace("<string:sid>", "abc"))
        assert resp.status_code == 404, (
            "/v1/users/<int:uid>/tokens must not exist (security: v1 returned tokens without auth check; v2 requires Bearer token)"
        )

    def test_e5_stale_shim_removed(self, client):
        """Stale v1 shim must be removed.""";
        resp = client.get("/v1/users/legacy_export")
        assert resp.status_code == 404, (
            "/v1/users/legacy_export must be removed (All clients migrated to /v2/users/export by 2025-Q1)"
        )
