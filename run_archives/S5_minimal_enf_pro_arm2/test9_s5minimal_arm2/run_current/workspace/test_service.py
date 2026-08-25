"""Mock-based tests for service.py external API calls.

Covers all 3 API calls (get_user, get_weather, send_notification)
and the composite function process_user_weather — 10 test functions total.

Based on planner2's refined mock testing plan (v2).
"""
import pytest
import requests
from unittest.mock import Mock, patch

from service import (
    get_user,
    get_weather,
    send_notification,
    process_user_weather,
    BASE_USER_URL,
    BASE_WEATHER_URL,
    BASE_NOTIFY_URL,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def mock_response(json_data, status_code=200):
    """Create a mock requests.Response with given JSON payload and status.

    For status >= 400, raise_for_status() will raise HTTPError (matching
    the real requests.Response behaviour).
    """
    resp = Mock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp
        )
    return resp


# ===================================================================
# 1. get_user
# ===================================================================

@patch("service.requests.get")
def test_get_user_success(mock_get):
    """Successful get_user: verify URL, timeout, and returned dict."""
    mock_get.return_value = mock_response(
        {"id": "1", "name": "Alice", "email": "alice@example.com"}, 200
    )

    result = get_user("1")

    # Assert 1: exact URL (f-string) + timeout
    mock_get.assert_called_once_with(
        f"{BASE_USER_URL}/1", timeout=10
    )

    # Assert 2: return value shape — all expected keys present
    assert result == {"id": "1", "name": "Alice", "email": "alice@example.com"}
    assert "id" in result and "name" in result and "email" in result


@patch("service.requests.get")
def test_get_user_not_found(mock_get):
    """get_user with 404: verify HTTPError is propagated (per raise_for_status)."""
    mock_get.return_value = mock_response({"error": "Not Found"}, 404)

    with pytest.raises(requests.exceptions.HTTPError):
        get_user("999")

    mock_get.assert_called_once_with(
        f"{BASE_USER_URL}/999", timeout=10
    )


# ===================================================================
# 2. get_weather
# ===================================================================

@patch("service.requests.get")
def test_get_weather_success(mock_get):
    """Successful get_weather: verify URL, params dict, timeout, and return."""
    mock_get.return_value = mock_response(
        {"city": "Beijing", "temp": 72.5, "condition": "Sunny"}, 200
    )

    result = get_weather("Beijing")

    # Assert 1: exact URL + params dict + timeout
    mock_get.assert_called_once_with(
        BASE_WEATHER_URL,
        params={"city": "Beijing"}, timeout=10,
    )

    # Assert 2: return value shape
    assert result["city"] == "Beijing"
    assert result["temp"] == 72.5
    assert result["condition"] == "Sunny"


@patch("service.requests.get")
def test_get_weather_service_error(mock_get):
    """get_weather with 500: verify HTTPError and correct city param."""
    mock_get.return_value = mock_response({"error": "Internal Error"}, 500)

    with pytest.raises(requests.exceptions.HTTPError):
        get_weather("UnknownCity")

    mock_get.assert_called_once_with(
        BASE_WEATHER_URL,
        params={"city": "UnknownCity"}, timeout=10,
    )


# ===================================================================
# 3. send_notification
# ===================================================================

@patch("service.requests.post")
def test_send_notification_success(mock_post):
    """Successful send_notification: verify URL, JSON body, timeout, return."""
    mock_post.return_value = mock_response({"status": "sent"}, 200)

    result = send_notification("1", "Hello, Alice!")

    # Assert 1: URL + json body + timeout
    mock_post.assert_called_once_with(
        BASE_NOTIFY_URL,
        json={"user_id": "1", "message": "Hello, Alice!"},
        timeout=5,
    )

    # Assert 2: return value
    assert result == {"status": "sent"}


@patch("service.requests.post")
def test_send_notification_http_error(mock_post):
    """send_notification with 503: verify HTTPError propagation."""
    mock_post.return_value = mock_response({"status": "failed"}, 503)

    with pytest.raises(requests.exceptions.HTTPError):
        send_notification("1", "Test")

    mock_post.assert_called_once_with(
        BASE_NOTIFY_URL,
        json={"user_id": "1", "message": "Test"},
        timeout=5,
    )


@patch("service.requests.post")
def test_send_notification_timeout(mock_post):
    """send_notification with Timeout: verify graceful error dict return."""
    mock_post.side_effect = requests.exceptions.Timeout

    result = send_notification("1", "Hello")

    assert result == {"status": "error", "reason": "timeout"}
    mock_post.assert_called_once_with(
        BASE_NOTIFY_URL,
        json={"user_id": "1", "message": "Hello"},
        timeout=5,
    )


# ===================================================================
# 4. process_user_weather (composite)
# ===================================================================

@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_success(mock_get, mock_post):
    """Happy-path: all three sub-calls succeed.  Assert orchestration."""
    # side_effect: 1st = get_user, 2nd = get_weather
    mock_get.side_effect = [
        mock_response({"id": "1", "name": "Alice", "email": "alice@example.com"}, 200),
        mock_response({"city": "Beijing", "temp": 72.5, "condition": "Sunny"}, 200),
    ]
    mock_post.return_value = mock_response({"status": "sent"}, 200)

    result = process_user_weather("1", "Beijing")

    # Assert 1: GET called exactly twice
    assert mock_get.call_count == 2

    # Assert 2: 1st GET — get_user
    mock_get.assert_any_call(f"{BASE_USER_URL}/1", timeout=10)

    # Assert 3: 2nd GET — get_weather (with params)
    mock_get.assert_any_call(
        BASE_WEATHER_URL, params={"city": "Beijing"}, timeout=10
    )

    # Assert 4: POST called with correct URL, JSON body, timeout
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == BASE_NOTIFY_URL
    assert call_args[1]["json"]["user_id"] == "1"
    # Message format: "Hi {name}, weather in {city}: {temp}F"
    expected_msg = "Hi Alice, weather in Beijing: 72.5F"
    assert call_args[1]["json"]["message"] == expected_msg
    assert call_args[1]["timeout"] == 5

    # Assert 5: composite return contains all three sub-results
    assert "user" in result
    assert "weather" in result
    assert "notification" in result
    assert result["user"]["name"] == "Alice"
    assert result["weather"]["temp"] == 72.5
    assert result["notification"]["status"] == "sent"


@patch("service.requests.get")
def test_process_user_weather_user_fetch_fails(mock_get):
    """get_user returns 404 → HTTPError propagates, pipeline stops."""
    mock_get.return_value = mock_response({"error": "Not Found"}, 404)

    with pytest.raises(requests.exceptions.HTTPError):
        process_user_weather("999", "Beijing")

    # Only the first GET was attempted — second never reached
    mock_get.assert_called_once_with(
        f"{BASE_USER_URL}/999", timeout=10
    )


@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_weather_fetch_fails(mock_get, mock_post):
    """get_weather returns 500 → HTTPError; get_user succeeded, POST not called."""
    mock_get.side_effect = [
        mock_response({"id": "1", "name": "Alice", "email": "alice@example.com"}, 200),
        mock_response({"error": "Internal Error"}, 500),
    ]

    with pytest.raises(requests.exceptions.HTTPError):
        process_user_weather("1", "Beijing")

    # get_user was called successfully
    mock_get.assert_any_call(f"{BASE_USER_URL}/1", timeout=10)
    # get_weather was also attempted
    mock_get.assert_any_call(
        BASE_WEATHER_URL, params={"city": "Beijing"}, timeout=10
    )
    # POST never reached (weather failure stops the pipeline)
    mock_post.assert_not_called()


@patch("service.requests.post")
@patch("service.requests.get")
def test_process_user_weather_notification_fails(mock_get, mock_post):
    """send_notification returns 503 → HTTPError; user+weather still succeed."""
    mock_get.side_effect = [
        mock_response({"id": "1", "name": "Alice", "email": "alice@example.com"}, 200),
        mock_response({"city": "Beijing", "temp": 72.5, "condition": "Sunny"}, 200),
    ]
    mock_post.return_value = mock_response({"status": "failed"}, 503)

    with pytest.raises(requests.exceptions.HTTPError):
        process_user_weather("1", "Beijing")

    # GETs both succeeded
    assert mock_get.call_count == 2
    # POST was attempted but failed
    mock_post.assert_called_once()
