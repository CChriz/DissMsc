"""Mock-based tests for service.py covering all 3 API call functions."""
from unittest.mock import patch, Mock

import requests
import service


def mock_response(json_data, status_code=200):
    """Create a mock Response object with the given JSON data."""
    resp = Mock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    return resp


# ── get_user tests ──────────────────────────────────────────────

@patch("service.requests.get")
def test_get_user_success(mock_get):
    """Verify get_user calls the correct URL and returns the expected data."""
    mock_get.return_value = mock_response(
        {"id": "123", "name": "Alice", "email": "alice@example.com"}
    )

    result = service.get_user("123")

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/123", timeout=10
    )
    assert result["id"] == "123"
    assert result["name"] == "Alice"


@patch("service.requests.get")
def test_get_user_url_correct(mock_get):
    """Verify get_user constructs the URL correctly for a different user ID."""
    mock_get.return_value = mock_response({"id": "user-456"})

    service.get_user("user-456")

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/user-456", timeout=10
    )


# ── get_weather tests ───────────────────────────────────────────

@patch("service.requests.get")
def test_get_weather_success(mock_get):
    """Verify get_weather calls the correct URL with query params."""
    mock_get.return_value = mock_response(
        {"city": "Beijing", "temp": 72, "condition": "Sunny"}
    )

    result = service.get_weather("Beijing")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "Beijing"},
        timeout=10,
    )
    assert result["temp"] == 72


@patch("service.requests.get")
def test_get_weather_params_correct(mock_get):
    """Verify get_weather passes city as a query parameter."""
    mock_get.return_value = mock_response({"city": "Shanghai", "temp": 65})

    service.get_weather("Shanghai")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "Shanghai"},
        timeout=10,
    )


# ── send_notification tests ─────────────────────────────────────

@patch("service.requests.post")
def test_send_notification_success(mock_post):
    """Verify send_notification sends the correct JSON body and URL."""
    mock_post.return_value = mock_response(
        {"status": "ok", "message_id": "msg-001"}
    )

    result = service.send_notification("123", "Hello!")

    mock_post.assert_called_once_with(
        "https://api.notify.example.com/v1/send",
        json={"user_id": "123", "message": "Hello!"},
        timeout=5,
    )
    assert result["status"] == "ok"
    assert result["message_id"] == "msg-001"


@patch("service.requests.post")
def test_send_notification_timeout(mock_post):
    """Verify send_notification handles Timeout gracefully."""
    mock_post.side_effect = requests.exceptions.Timeout

    result = service.send_notification("123", "test")

    assert result == {"status": "error", "reason": "timeout"}


@patch("service.requests.post")
def test_send_notification_connection_error(mock_post):
    """Verify send_notification handles ConnectionError gracefully."""
    mock_post.side_effect = requests.exceptions.ConnectionError

    result = service.send_notification("123", "test")

    assert result == {"status": "error", "reason": "timeout"}


# ── process_user_weather tests ──────────────────────────────────

@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_success(mock_get, mock_post):
    """Verify process_user_weather chains all three API calls correctly."""
    # requests.get is called twice: first for user, then for weather
    mock_get.side_effect = [
        mock_response({"id": "123", "name": "Alice"}),
        mock_response({"city": "Tokyo", "temp": 68}),
    ]
    mock_post.return_value = mock_response({"status": "ok"})

    result = service.process_user_weather("123", "Tokyo")

    # Check each part of the composite result
    assert result["user"]["name"] == "Alice"
    assert result["weather"]["temp"] == 68
    assert result["notification"]["status"] == "ok"


@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_notification_timeout(mock_get, mock_post):
    """Verify process_user_weather survives a notification timeout."""
    mock_get.side_effect = [
        mock_response({"id": "123", "name": "Alice"}),
        mock_response({"city": "Tokyo", "temp": 68}),
    ]
    mock_post.side_effect = requests.exceptions.Timeout

    result = service.process_user_weather("123", "Tokyo")

    assert result["notification"] == {"status": "error", "reason": "timeout"}
    # User and weather data should still be intact
    assert result["user"]["name"] == "Alice"
    assert result["weather"]["temp"] == 68
