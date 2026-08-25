"""
Test suite for TEST9: Mock-Based API Testing

Tests verify that service.py correctly handles:
  1. Successful API calls for get_user, get_weather, send_notification
  2. Timeout errors in send_notification (returns error dict, no crash)
  3. Connection errors in send_notification (returns error dict, no crash)
  4. HTTP errors in get_user and get_weather (raises HTTPError as expected)
  5. process_user_weather integration (happy path + notification timeout)

All external HTTP calls are mocked via unittest.mock.
"""

import pytest
from unittest import mock
import requests
import service


# ── Helper: create a mock response ────────────────────────────────────────────

def _mock_response(status_code=200, json_data=None):
    """Create a mock requests.Response with given status and json data."""
    resp = mock.MagicMock()
    resp.status_code = status_code
    if json_data is None:
        json_data = {}
    resp.json.return_value = json_data
    return resp


# ── 1. test_get_user_success ─────────────────────────────────────────────────

@mock.patch("service.requests.get")
def test_get_user_success(mock_get):
    """get_user should call correct URL with timeout=10 and return parsed JSON."""
    mock_resp = _mock_response(200, {"id": "U1", "name": "Alice", "email": "alice@example.com"})
    mock_get.return_value = mock_resp

    result = service.get_user("U1")

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/U1",
        timeout=10,
    )
    assert result["id"] == "U1"
    assert result["name"] == "Alice"
    assert result["email"] == "alice@example.com"


# ── 2. test_get_weather_success ──────────────────────────────────────────────

@mock.patch("service.requests.get")
def test_get_weather_success(mock_get):
    """get_weather should call correct URL with params and timeout=10."""
    mock_resp = _mock_response(200, {"city": "Beijing", "temp": 22, "condition": "Sunny"})
    mock_get.return_value = mock_resp

    result = service.get_weather("Beijing")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "Beijing"},
        timeout=10,
    )
    assert result["city"] == "Beijing"
    assert result["temp"] == 22
    assert result["condition"] == "Sunny"


# ── 3. test_send_notification_success ────────────────────────────────────────

@mock.patch("service.requests.post")
def test_send_notification_success(mock_post):
    """send_notification should POST correct JSON with timeout=5."""
    mock_resp = _mock_response(200, {"status": "sent", "message_id": "msg-123"})
    mock_post.return_value = mock_resp

    result = service.send_notification("U1", "Hello!")

    mock_post.assert_called_once_with(
        "https://api.notify.example.com/v1/send",
        json={"user_id": "U1", "message": "Hello!"},
        timeout=5,
    )
    assert result["status"] == "sent"
    assert result["message_id"] == "msg-123"


# ── 4. test_send_notification_timeout ────────────────────────────────────────

@mock.patch("service.requests.post")
def test_send_notification_timeout(mock_post):
    """send_notification should catch Timeout and return error dict, not crash."""
    mock_post.side_effect = requests.exceptions.Timeout()

    result = service.send_notification("U1", "Hello!")

    assert result == {"status": "error", "reason": "timeout"}


# ── 5. test_send_notification_connection_error ───────────────────────────────

@mock.patch("service.requests.post")
def test_send_notification_connection_error(mock_post):
    """send_notification should catch ConnectionError and return error dict."""
    mock_post.side_effect = requests.exceptions.ConnectionError()

    result = service.send_notification("U1", "Test")

    assert result == {"status": "error", "reason": "timeout"}


# ── 6. test_get_user_http_error ──────────────────────────────────────────────

@mock.patch("service.requests.get")
def test_get_user_http_error(mock_get):
    """get_user should raise HTTPError on 404 (no try/except in get_user)."""
    mock_resp = _mock_response(404, {})
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
    mock_get.return_value = mock_resp

    with pytest.raises(requests.exceptions.HTTPError):
        service.get_user("INVALID")

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/INVALID",
        timeout=10,
    )


# ── 7. test_get_weather_http_error ───────────────────────────────────────────

@mock.patch("service.requests.get")
def test_get_weather_http_error(mock_get):
    """get_weather should raise HTTPError on 500 (no try/except in get_weather)."""
    mock_resp = _mock_response(500, {})
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    mock_get.return_value = mock_resp

    with pytest.raises(requests.exceptions.HTTPError):
        service.get_weather("Nowhere")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "Nowhere"},
        timeout=10,
    )


# ── 8. test_process_user_weather_success ─────────────────────────────────────

@mock.patch("service.requests.post")
@mock.patch("service.requests.get")
def test_process_user_weather_success(mock_get, mock_post):
    """process_user_weather should chain all 3 calls and return combined dict."""
    mock_user_resp = _mock_response(200, {"id": "U1", "name": "Alice"})
    mock_weather_resp = _mock_response(200, {"city": "Beijing", "temp": 22})
    mock_notify_resp = _mock_response(200, {"status": "sent", "message_id": "msg-456"})

    mock_get.side_effect = [mock_user_resp, mock_weather_resp]
    mock_post.return_value = mock_notify_resp

    result = service.process_user_weather("U1", "Beijing")

    # Verify get was called twice
    assert mock_get.call_count == 2
    mock_get.assert_any_call("https://api.users.example.com/v1/users/U1", timeout=10)
    mock_get.assert_any_call(
        "https://api.weather.example.com/v2/current",
        params={"city": "Beijing"},
        timeout=10,
    )

    # Verify post was called once with correct notification message
    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    assert call_kwargs["json"]["user_id"] == "U1"
    assert "Hi Alice" in call_kwargs["json"]["message"]
    assert "Beijing" in call_kwargs["json"]["message"]
    assert "22F" in call_kwargs["json"]["message"]

    # Verify return structure
    assert "user" in result
    assert "weather" in result
    assert "notification" in result
    assert result["user"]["name"] == "Alice"
    assert result["weather"]["temp"] == 22
    assert result["notification"]["status"] == "sent"


# ── 9. test_process_user_weather_notification_timeout ────────────────────────

@mock.patch("service.requests.post")
@mock.patch("service.requests.get")
def test_process_user_weather_notification_timeout(mock_get, mock_post):
    """process_user_weather should not crash when notification times out."""
    mock_user_resp = _mock_response(200, {"id": "U1", "name": "Bob"})
    mock_weather_resp = _mock_response(200, {"city": "Shanghai", "temp": 30})
    mock_post.side_effect = requests.exceptions.Timeout()

    mock_get.side_effect = [mock_user_resp, mock_weather_resp]

    result = service.process_user_weather("U1", "Shanghai")

    # Should not crash, user and weather still returned
    assert "user" in result
    assert "weather" in result
    assert "notification" in result
    assert result["notification"] == {"status": "error", "reason": "timeout"}
