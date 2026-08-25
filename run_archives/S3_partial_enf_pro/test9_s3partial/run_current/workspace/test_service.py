"""Mock-based tests for service.py — 3 APIs, 12 test functions."""
import pytest
import requests
from unittest.mock import patch, Mock

from service import get_user, get_weather, send_notification, process_user_weather


# ──────────────────────────────────────────────
#  Group A: get_user(user_id)
#  GET https://api.users.example.com/v1/users/{user_id}
# ──────────────────────────────────────────────

@patch("service.requests.get")
def test_get_user_success(mock_get):
    """Happy path: return user dict on 200."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": 1, "name": "Alice", "email": "alice@example.com"
    }
    mock_get.return_value = mock_response

    result = get_user(1)

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/1", timeout=10
    )
    assert isinstance(result, dict)
    assert result["id"] == 1
    assert result["name"] == "Alice"
    assert "email" in result


@patch("service.requests.get")
def test_get_user_not_found(mock_get):
    """Return error dict when API returns 404."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"error": "not found"}
    mock_get.return_value = mock_response

    result = get_user(999)

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/999", timeout=10
    )
    assert isinstance(result, dict)
    assert "error" in result


@patch("service.requests.get")
def test_get_user_network_error(mock_get):
    """Propagate ConnectionError when network fails."""
    mock_get.side_effect = requests.exceptions.ConnectionError("network down")

    with pytest.raises(requests.exceptions.ConnectionError):
        get_user(1)


# ──────────────────────────────────────────────
#  Group B: get_weather(city)
#  GET https://api.weather.example.com/v2/current?city={city}
# ──────────────────────────────────────────────

@patch("service.requests.get")
def test_get_weather_success(mock_get):
    """Happy path: return weather dict on 200."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "city": "Beijing", "temp": 22.5, "condition": "Sunny"
    }
    mock_get.return_value = mock_response

    result = get_weather("Beijing")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "Beijing"},
        timeout=10,
    )
    assert isinstance(result, dict)
    assert result["city"] == "Beijing"
    assert result["temp"] == 22.5
    assert "condition" in result


@patch("service.requests.get")
def test_get_weather_city_not_found(mock_get):
    """Return error dict when city not found (404)."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"error": "city not found"}
    mock_get.return_value = mock_response

    result = get_weather("Atlantis")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "Atlantis"},
        timeout=10,
    )
    assert isinstance(result, dict)
    assert "error" in result


@patch("service.requests.get")
def test_get_weather_timeout(mock_get):
    """Propagate Timeout when request times out."""
    mock_get.side_effect = requests.exceptions.Timeout("request timed out")

    with pytest.raises(requests.exceptions.Timeout):
        get_weather("Beijing")


# ──────────────────────────────────────────────
#  Group C: send_notification(user_id, message)
#  POST https://api.notify.example.com/v1/send
# ──────────────────────────────────────────────

@patch("service.requests.post")
def test_send_notification_success(mock_post):
    """Happy path: return sent-status dict on 200."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent", "message_id": "msg-123"}
    mock_post.return_value = mock_response

    result = send_notification("user-1", "Hello!")

    mock_post.assert_called_once_with(
        "https://api.notify.example.com/v1/send",
        json={"user_id": "user-1", "message": "Hello!"},
        timeout=5,
    )
    assert isinstance(result, dict)
    assert result["status"] == "sent"
    assert result["message_id"] == "msg-123"


@patch("service.requests.post")
def test_send_notification_timeout(mock_post):
    """Return error dict instead of crashing on Timeout."""
    mock_post.side_effect = requests.exceptions.Timeout("request timed out")

    result = send_notification("user-1", "Hello!")

    assert isinstance(result, dict)
    assert result["status"] == "error"
    assert result["reason"] == "timeout"
    # Ensure no real network call was made — post was attempted and caught
    mock_post.assert_called_once()


@patch("service.requests.post")
def test_send_notification_connection_error(mock_post):
    """Return error dict instead of crashing on ConnectionError."""
    mock_post.side_effect = requests.exceptions.ConnectionError("connection refused")

    result = send_notification("user-1", "Hello!")

    assert isinstance(result, dict)
    assert result["status"] == "error"
    assert result["reason"] == "timeout"
    mock_post.assert_called_once()


# ──────────────────────────────────────────────
#  Group D: process_user_weather(user_id, city)
#  Orchestrates get_user → get_weather → send_notification
# ──────────────────────────────────────────────

@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_success(mock_get, mock_post):
    """Full happy path: user + weather + notification all succeed."""
    # Mock user response
    mock_user_resp = Mock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "id": 1, "name": "Alice", "email": "alice@example.com"
    }

    # Mock weather response
    mock_weather_resp = Mock()
    mock_weather_resp.status_code = 200
    mock_weather_resp.json.return_value = {
        "city": "Beijing", "temp": 22.5, "condition": "Sunny"
    }

    # Mock notification response
    mock_notify_resp = Mock()
    mock_notify_resp.status_code = 200
    mock_notify_resp.json.return_value = {"status": "sent", "message_id": "msg-456"}

    # Two GET calls: first user, then weather
    mock_get.side_effect = [mock_user_resp, mock_weather_resp]
    mock_post.return_value = mock_notify_resp

    result = process_user_weather(1, "Beijing")

    # Assert overall structure
    assert isinstance(result, dict)
    assert "user" in result
    assert "weather" in result
    assert "notification" in result

    # Assert user data
    assert result["user"]["id"] == 1
    assert result["user"]["name"] == "Alice"

    # Assert weather data
    assert result["weather"]["city"] == "Beijing"
    assert result["weather"]["temp"] == 22.5

    # Assert notification data
    assert result["notification"]["status"] == "sent"

    # Verify GET was called exactly twice
    assert mock_get.call_count == 2

    # Verify POST was called with correct payload
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://api.notify.example.com/v1/send"
    assert call_args[1]["json"]["user_id"] == 1
    assert "Alice" in call_args[1]["json"]["message"]
    assert "Beijing" in call_args[1]["json"]["message"]


@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_user_failure(mock_get, mock_post):
    """When user fetch fails (404), the error propagates through."""
    # Mock user failure
    mock_user_resp = Mock()
    mock_user_resp.status_code = 404
    mock_user_resp.json.return_value = {"error": "not found"}

    # Mock weather success
    mock_weather_resp = Mock()
    mock_weather_resp.status_code = 200
    mock_weather_resp.json.return_value = {
        "city": "Beijing", "temp": 22.5, "condition": "Sunny"
    }

    # Mock notification success
    mock_notify_resp = Mock()
    mock_notify_resp.status_code = 200
    mock_notify_resp.json.return_value = {"status": "sent", "message_id": "msg-789"}

    mock_get.side_effect = [mock_user_resp, mock_weather_resp]
    mock_post.return_value = mock_notify_resp

    result = process_user_weather(999, "Beijing")

    assert isinstance(result, dict)
    assert "user" in result
    assert "weather" in result
    assert "notification" in result

    # User data should contain error
    assert "error" in result["user"]

    # Weather should still be fine
    assert result["weather"]["city"] == "Beijing"

    # Notification should still be sent
    assert result["notification"]["status"] == "sent"


@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_notification_failure(mock_get, mock_post):
    """When notification times out, return error dict for notification only."""
    # Mock user success
    mock_user_resp = Mock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "id": 2, "name": "Bob", "email": "bob@example.com"
    }

    # Mock weather success
    mock_weather_resp = Mock()
    mock_weather_resp.status_code = 200
    mock_weather_resp.json.return_value = {
        "city": "Shanghai", "temp": 18.0, "condition": "Cloudy"
    }

    mock_get.side_effect = [mock_user_resp, mock_weather_resp]
    mock_post.side_effect = requests.exceptions.Timeout("request timed out")

    result = process_user_weather(2, "Shanghai")

    assert isinstance(result, dict)
    assert "user" in result
    assert "weather" in result
    assert "notification" in result

    # User and weather should still be correct
    assert result["user"]["name"] == "Bob"
    assert result["weather"]["city"] == "Shanghai"

    # Notification should be error dict
    assert result["notification"]["status"] == "error"
    assert result["notification"]["reason"] == "timeout"
