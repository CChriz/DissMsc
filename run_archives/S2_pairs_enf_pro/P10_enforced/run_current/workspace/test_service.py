"""Tests for service.py — all external API calls are mocked."""
from unittest.mock import patch, MagicMock
import requests
import service


# ---------------------------------------------------------------------------
# get_user tests
# ---------------------------------------------------------------------------

@patch("service.requests.get")
def test_get_user_success(mock_get):
    """get_user returns user dict on 200 OK; URL must contain user_id."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "42", "name": "Alice", "email": "alice@example.com"
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = service.get_user("42")

    assert result == {"id": "42", "name": "Alice", "email": "alice@example.com"}
    assert "id" in result and "name" in result and "email" in result
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "42" in call_url
    assert "api.users.example.com" in call_url


@patch("service.requests.get")
def test_get_user_not_found(mock_get):
    """get_user should raise or propagate an HTTPError on 404."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
    mock_get.return_value = mock_response

    try:
        service.get_user("nonexistent")
        # If no exception, the function should have returned an error dict
        assert False, "Expected an HTTPError to be raised"
    except requests.exceptions.HTTPError:
        pass  # expected


# ---------------------------------------------------------------------------
# get_weather tests
# ---------------------------------------------------------------------------

@patch("service.requests.get")
def test_get_weather_success(mock_get):
    """get_weather returns weather dict on 200 OK; URL must include city param."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "city": "London", "temp": 62, "condition": "Cloudy"
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = service.get_weather("London")

    assert result == {"city": "London", "temp": 62, "condition": "Cloudy"}
    assert "city" in result and "temp" in result and "condition" in result
    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args[1]
    assert call_kwargs["params"] == {"city": "London"}


@patch("service.requests.get")
def test_get_weather_invalid_city(mock_get):
    """get_weather should raise HTTPError for invalid / non-existent city."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
    mock_get.return_value = mock_response

    try:
        service.get_weather("Atlantis")
        assert False, "Expected an HTTPError to be raised"
    except requests.exceptions.HTTPError:
        pass  # expected


# ---------------------------------------------------------------------------
# send_notification tests (core: error handling after fix)
# ---------------------------------------------------------------------------

@patch("service.requests.post")
def test_send_notification_success(mock_post):
    """send_notification returns {"status": "sent"} on 200 OK."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "sent"}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    result = service.send_notification("42", "Hello")

    assert result == {"status": "sent"}
    mock_post.assert_called_once()
    call_url = mock_post.call_args[0][0]
    assert "api.notify.example.com" in call_url
    call_json = mock_post.call_args[1]["json"]
    assert call_json["user_id"] == "42"
    assert call_json["message"] == "Hello"


@patch("service.requests.post")
def test_send_notification_timeout(mock_post):
    """send_notification returns error dict on Timeout, never crashes."""
    mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

    result = service.send_notification("42", "Hello")

    assert result == {"status": "error", "reason": "timeout"}
    assert result["status"] == "error"


@patch("service.requests.post")
def test_send_notification_connection_error(mock_post):
    """send_notification returns error dict on ConnectionError, never crashes."""
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

    result = service.send_notification("42", "Hello")

    assert result == {"status": "error", "reason": "connection_error"}
    assert result["status"] == "error"


@patch("service.requests.post")
def test_send_notification_server_error(mock_post):
    """send_notification returns error dict on HTTP 500."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    mock_post.return_value = mock_response

    result = service.send_notification("42", "Hello")

    assert result == {"status": "error", "reason": "server_error"}
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Optional — all-mocks-isolated test
# ---------------------------------------------------------------------------

@patch("service.requests.post")
@patch("service.requests.get")
def test_all_mocks_isolated(mock_get, mock_post):
    """Verify all 3 APIs are mockable — no real network calls escape.

    Uses process_user_weather which internally calls get_user, get_weather, and
    send_notification.
    """
    # --- Setup get_user mock ---
    mock_user_response = MagicMock()
    mock_user_response.json.return_value = {
        "id": "1", "name": "TestUser", "email": "test@test.com"
    }
    mock_user_response.raise_for_status = MagicMock()

    # --- Setup get_weather mock ---
    mock_weather_response = MagicMock()
    mock_weather_response.json.return_value = {
        "city": "TestCity", "temp": 75, "condition": "Sunny"
    }
    mock_weather_response.raise_for_status = MagicMock()

    # --- Setup send_notification mock ---
    mock_notify_response = MagicMock()
    mock_notify_response.json.return_value = {"status": "sent"}
    mock_notify_response.raise_for_status = MagicMock()

    # get is called twice (user + weather), post once
    mock_get.side_effect = [mock_user_response, mock_weather_response]
    mock_post.return_value = mock_notify_response

    result = service.process_user_weather("1", "TestCity")

    assert result["user"]["name"] == "TestUser"
    assert result["weather"]["temp"] == 75
    assert result["notification"]["status"] == "sent"

    assert mock_get.call_count == 2
    assert mock_post.call_count == 1
