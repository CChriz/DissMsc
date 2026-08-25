"""Mock-based tests for service.py — 3 API calls, no real network requests."""
import pytest
from unittest.mock import patch, MagicMock
import requests
from service import (
    get_user,
    get_weather,
    send_notification,
    BASE_USER_URL,
    BASE_WEATHER_URL,
    BASE_NOTIFY_URL,
)


# ── get_user tests ──────────────────────────────────────────────

@patch("service.requests.get")
def test_get_user_success(mock_get):
    """Mock requests.get to return a user dict; verify URL and response."""
    mock_get.return_value.json.return_value = {
        "id": 1,
        "name": "Alice",
        "email": "alice@example.com",
    }
    mock_get.return_value.status_code = 200

    result = get_user("1")

    # URL assertion
    mock_get.assert_called_once_with(
        f"{BASE_USER_URL}/1", timeout=10
    )
    # Return value assertions
    assert isinstance(result, dict)
    assert result["id"] == 1
    assert result["name"] == "Alice"
    assert result["email"] == "alice@example.com"


@patch("service.requests.get")
def test_get_user_url_and_params(mock_get):
    """Verify requests.get is called with the correct URL for a given user_id."""
    mock_get.return_value.json.return_value = {"id": 42, "name": "Bob"}
    mock_get.return_value.status_code = 200

    get_user("42")

    mock_get.assert_called_once_with(
        f"{BASE_USER_URL}/42", timeout=10
    )


@patch("service.requests.get")
def test_get_user_returns_correct_shape(mock_get):
    """Verify the returned dict contains all required keys."""
    mock_get.return_value.json.return_value = {
        "id": 7,
        "name": "Charlie",
        "email": "charlie@example.com",
    }
    mock_get.return_value.status_code = 200

    result = get_user("7")

    assert isinstance(result, dict)
    assert "id" in result
    assert "name" in result
    assert "email" in result


# ── get_weather tests ───────────────────────────────────────────

@patch("service.requests.get")
def test_get_weather_success(mock_get):
    """Mock requests.get to return weather data; verify URL, params, and response."""
    mock_get.return_value.json.return_value = {
        "city": "Beijing",
        "temperature": 25,
        "condition": "Sunny",
    }
    mock_get.return_value.status_code = 200

    result = get_weather("Beijing")

    # URL and params assertion
    mock_get.assert_called_once_with(
        BASE_WEATHER_URL, params={"city": "Beijing"}, timeout=10
    )
    # Return value assertions
    assert isinstance(result, dict)
    assert result["city"] == "Beijing"
    assert result["temperature"] == 25
    assert result["condition"] == "Sunny"


@patch("service.requests.get")
def test_get_weather_different_city(mock_get):
    """Verify params differ when a different city is passed."""
    mock_get.return_value.json.return_value = {
        "city": "Shanghai",
        "temperature": 30,
        "condition": "Cloudy",
    }
    mock_get.return_value.status_code = 200

    get_weather("Shanghai")

    mock_get.assert_called_once_with(
        BASE_WEATHER_URL, params={"city": "Shanghai"}, timeout=10
    )


@patch("service.requests.get")
def test_get_weather_returns_correct_shape(mock_get):
    """Verify the returned dict contains city, temperature, and condition keys."""
    mock_get.return_value.json.return_value = {
        "city": "Tokyo",
        "temperature": 18,
        "condition": "Rainy",
    }
    mock_get.return_value.status_code = 200

    result = get_weather("Tokyo")

    assert isinstance(result, dict)
    assert "city" in result
    assert "temperature" in result
    assert "condition" in result


# ── send_notification tests ─────────────────────────────────────

@patch("service.requests.post")
def test_send_notification_success(mock_post):
    """Mock requests.post success; verify URL, payload, and return value."""
    mock_post.return_value.json.return_value = {
        "status": "ok",
        "message_id": "msg-123",
    }
    mock_post.return_value.status_code = 200

    result = send_notification("1", "Hello, World!")

    # URL assertion
    mock_post.assert_called_once_with(
        BASE_NOTIFY_URL,
        json={"user_id": "1", "message": "Hello, World!"},
        timeout=5,
    )
    # Return value assertions
    assert isinstance(result, dict)
    assert result["status"] == "ok"
    assert result["message_id"] == "msg-123"


@patch("service.requests.post")
def test_send_notification_payload(mock_post):
    """Verify the JSON payload sent to requests.post contains correct fields."""
    mock_post.return_value.json.return_value = {"status": "ok", "message_id": "xyz"}
    mock_post.return_value.status_code = 200

    send_notification("99", "Test message")

    # Extract the json= argument from the call
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["user_id"] == "99"
    assert call_kwargs["json"]["message"] == "Test message"


@patch("service.requests.post")
def test_send_notification_timeout(mock_post):
    """When requests.post raises Timeout, return error dict — no crash."""
    mock_post.side_effect = requests.exceptions.Timeout()

    result = send_notification("1", "Hello")

    # Must not raise; must return error dict
    assert isinstance(result, dict)
    assert result["status"] == "error"


@patch("service.requests.post")
def test_send_notification_connection_error(mock_post):
    """When requests.post raises ConnectionError, return error dict — no crash."""
    mock_post.side_effect = requests.exceptions.ConnectionError()

    result = send_notification("1", "Hello")

    # Must not raise; must return error dict
    assert isinstance(result, dict)
    assert result["status"] == "error"
