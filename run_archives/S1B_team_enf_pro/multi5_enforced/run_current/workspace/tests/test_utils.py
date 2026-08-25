"""Tests for utility functions."""
from app.utils import format_response, validate_input, sanitize_string


def test_format_response_success():
    resp = format_response(data={"key": "value"})
    assert resp["status"] == "ok"
    assert resp["data"] == {"key": "value"}


def test_format_response_error():
    resp = format_response(error="Something went wrong")
    assert resp["status"] == "error"
    assert resp["error"] == "Something went wrong"


def test_validate_input_valid():
    assert validate_input({"key": "value"}) is True


def test_validate_input_empty():
    assert validate_input({}) is False


def test_validate_input_none():
    assert validate_input(None) is False


def test_sanitize_string():
    assert sanitize_string("  hello  ") == "hello"
    assert sanitize_string(42) == "42"
