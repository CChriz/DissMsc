"""Tests that v2 endpoints still work correctly after changes.""";
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


class TestV2Endpoints:
    def test_e1_v2_uses_new_field(self, client):
        resp = client.get("/v2/users/<int:uid>".replace("<int:uid>", "1")
                                              .replace("<int:pid>", "1")
                                              .replace("<int:oid>", "1")
                                              .replace("<int:rid>", "1")
                                              .replace("<string:sid>", "abc"))
        assert resp.status_code == 200
        data = resp.get_json()
        assert "display_name" in data

    def test_e2_v2_nested_response(self, client):
        resp = client.get("/v2/users/<int:uid>/preferences".replace("<int:uid>", "1")
                                              .replace("<int:pid>", "1")
                                              .replace("<int:oid>", "1")
                                              .replace("<int:rid>", "1")
                                              .replace("<string:sid>", "abc"))
        assert resp.status_code == 200

    def test_e3_v2_requires_param(self, client):
        resp = client.get("/v2/users/search")
        assert resp.status_code == 400, "v2 must require 'page'"

    def test_e3_v2_with_param(self, client):
        resp = client.get(f"/v2/users/search?page=1")
        assert resp.status_code == 200

    def test_e4_v2_requires_auth(self, client):
        resp = client.get("/v2/users/<int:uid>/tokens".replace("<int:uid>", "1")
                                              .replace("<int:pid>", "1")
                                              .replace("<int:oid>", "1")
                                              .replace("<int:rid>", "1")
                                              .replace("<string:sid>", "abc"))
        assert resp.status_code == 401

    def test_e4_v2_with_auth(self, client):
        resp = client.get(
            "/v2/users/<int:uid>/tokens".replace("<int:uid>", "1")
                                .replace("<int:pid>", "1")
                                .replace("<int:oid>", "1")
                                .replace("<int:rid>", "1")
                                .replace("<string:sid>", "abc"),
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
