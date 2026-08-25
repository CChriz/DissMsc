"""Mock-based tests for service.py — 3 API calls + composition function.

Mock strategy: patch 'service.requests.get' and 'service.requests.post' at
the module level so no real network requests are ever made.

Test coverage: 10 test functions across 3 groups:
  A: single-API success paths (tests 1-3)
  B: error paths — HTTP errors, timeout, connection error (tests 4-7)
  C: composition flow — process_user_weather (tests 8-10)
"""

import pytest
import requests
from unittest.mock import patch, MagicMock

import service


# ---------------------------------------------------------------------------
# helper — mock response factory
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None):
    """Build a MagicMock that behaves like a requests.Response.

    When status_code >= 400 the mock's raise_for_status() will raise
    requests.exceptions.HTTPError, matching the real library behaviour.
    """
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}

    if status_code >= 400:
        http_error = requests.exceptions.HTTPError(
            f"{status_code} Client Error", response=resp
        )
        resp.raise_for_status.side_effect = http_error

    return resp


# ===================================================================
# Group A — Single API success paths
# ===================================================================

class TestSingleApiSuccess:
    """Happy-path tests for each of the three external calls."""

    @patch("service.requests.get")
    def test_get_user_success(self, mock_get):
        """Fetch a valid user — should return the full user dict."""
        user_data = {
            "user_id": "U123",
            "name": "Alice",
            "email": "alice@example.com",
        }
        mock_get.return_value = _mock_response(200, user_data)

        result = service.get_user("U123")

        mock_get.assert_called_once_with(
            "https://api.users.example.com/v1/users/U123", timeout=10
        )
        assert result == user_data
        assert "user_id" in result
        assert "name" in result
        assert "email" in result

    @patch("service.requests.get")
    def test_get_weather_success(self, mock_get):
        """Fetch weather for a city — should return weather dict (field: temp)."""
        weather_data = {
            "city": "Beijing",
            "temp": 22,
            "condition": "Sunny",
        }
        mock_get.return_value = _mock_response(200, weather_data)

        result = service.get_weather("Beijing")

        mock_get.assert_called_once_with(
            "https://api.weather.example.com/v2/current",
            params={"city": "Beijing"},
            timeout=10,
        )
        assert result == weather_data
        assert result["city"] == "Beijing"
        assert result["temp"] == 22
        assert result["condition"] == "Sunny"

    @patch("service.requests.post")
    def test_send_notification_success(self, mock_post):
        """Send a notification — should return sent status."""
        mock_post.return_value = _mock_response(200, {"status": "sent"})

        result = service.send_notification("U123", "Hello!")

        mock_post.assert_called_once_with(
            "https://api.notify.example.com/v1/send",
            json={"user_id": "U123", "message": "Hello!"},
            timeout=5,
        )
        assert result == {"status": "sent"}


# ===================================================================
# Group B — Error paths
# ===================================================================

class TestErrorPaths:
    """Tests for failure modes: HTTP errors, timeouts, connection errors."""

    # -- get_user / get_weather: raise_for_status() → HTTPError propagates ---

    @patch("service.requests.get")
    def test_get_user_http_error(self, mock_get):
        """get_user should raise HTTPError when the API returns 4xx/5xx."""
        mock_get.return_value = _mock_response(404, {"error": "not found"})

        with pytest.raises(requests.exceptions.HTTPError):
            service.get_user("bad_id")

        mock_get.assert_called_once_with(
            "https://api.users.example.com/v1/users/bad_id", timeout=10
        )

    @patch("service.requests.get")
    def test_get_weather_http_error(self, mock_get):
        """get_weather should raise HTTPError when the API returns 5xx."""
        mock_get.return_value = _mock_response(500, {"error": "server error"})

        with pytest.raises(requests.exceptions.HTTPError):
            service.get_weather("InvalidCity")

        mock_get.assert_called_once_with(
            "https://api.weather.example.com/v2/current",
            params={"city": "InvalidCity"},
            timeout=10,
        )

    # -- send_notification: timeout / connection error (post-fix behaviour) --

    @patch("service.requests.post")
    def test_send_notification_timeout(self, mock_post):
        """send_notification should catch Timeout and return an error dict.

        NOTE: This test describes the *desired* post-fix behaviour.
        The current service.py does NOT catch Timeout (known bug).
        After executor2's fix this test will pass.
        """
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        result = service.send_notification("U123", "Hello!")

        assert result == {"status": "error", "reason": "timeout"}

    @patch("service.requests.post")
    def test_send_notification_connection_error(self, mock_post):
        """send_notification should catch ConnectionError and return error dict.

        Per spec (service.py docstring), both Timeout and ConnectionError
        return reason="timeout".
        """
        mock_post.side_effect = requests.exceptions.ConnectionError(
            "connection refused"
        )

        result = service.send_notification("U123", "Hello!")

        assert result == {"status": "error", "reason": "timeout"}


# ===================================================================
# Group C — Composition flow (process_user_weather)
# ===================================================================

class TestProcessUserWeather:
    """Integration-level tests for the composite process_user_weather.

    Every external call made by process_user_weather is patched so the
    test never touches the network.
    """

    @patch("service.requests.post")
    @patch("service.requests.get")
    def test_all_success(self, mock_get, mock_post):
        """Happy-path: all three APIs succeed, verify message format."""
        user_data = {
            "user_id": "U123",
            "name": "Alice",
            "email": "alice@example.com",
        }
        weather_data = {
            "city": "Beijing",
            "temp": 22,
            "condition": "Sunny",
        }
        notify_data = {"status": "sent"}

        # Two calls to requests.get: first for user, second for weather
        mock_get.side_effect = [
            _mock_response(200, user_data),
            _mock_response(200, weather_data),
        ]
        mock_post.return_value = _mock_response(200, notify_data)

        result = service.process_user_weather("U123", "Beijing")

        # --- Assert calls ---
        assert mock_get.call_count == 2
        mock_get.assert_any_call(
            "https://api.users.example.com/v1/users/U123", timeout=10
        )
        mock_get.assert_any_call(
            "https://api.weather.example.com/v2/current",
            params={"city": "Beijing"},
            timeout=10,
        )
        mock_post.assert_called_once_with(
            "https://api.notify.example.com/v1/send",
            json={
                "user_id": "U123",
                "message": "Hi Alice, weather in Beijing: 22F",
            },
            timeout=5,
        )

        # --- Assert return structure ---
        assert result["user"] == user_data
        assert result["weather"] == weather_data
        assert result["notification"] == notify_data

    @patch("service.requests.post")
    @patch("service.requests.get")
    def test_user_not_found(self, mock_get, mock_post):
        """User API returns 404 — HTTPError propagates, halting the flow.

        get_user calls raise_for_status() which raises HTTPError for 4xx.
        process_user_weather stops before reaching get_weather or
        send_notification.
        """
        weather_data = {"city": "Beijing", "temp": 22, "condition": "Sunny"}
        mock_get.side_effect = [
            _mock_response(404, {"error": "not found"}),
            _mock_response(200, weather_data),
        ]
        mock_post.return_value = _mock_response(200, {"status": "sent"})

        with pytest.raises(requests.exceptions.HTTPError):
            service.process_user_weather("bad_id", "Beijing")

        # Only the first GET (user) was made; weather & post never reached
        mock_get.assert_called_once_with(
            "https://api.users.example.com/v1/users/bad_id", timeout=10
        )
        mock_post.assert_not_called()

    @patch("service.requests.post")
    @patch("service.requests.get")
    def test_notification_timeout(self, mock_get, mock_post):
        """Notification times out — composite call should not crash.

        After executor2's fix, send_notification catches Timeout and
        returns an error dict.  process_user_weather therefore completes
        successfully with the error reflected in notification.
        """
        user_data = {
            "user_id": "U123",
            "name": "Alice",
            "email": "alice@example.com",
        }
        weather_data = {"city": "Beijing", "temp": 22, "condition": "Sunny"}
        mock_get.side_effect = [
            _mock_response(200, user_data),
            _mock_response(200, weather_data),
        ]
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        result = service.process_user_weather("U123", "Beijing")

        # User + weather were fetched successfully
        assert mock_get.call_count == 2
        mock_post.assert_called_once()

        # The composite result should include user and weather data,
        # and the notification should reflect the timeout error
        assert result["user"] == user_data
        assert result["weather"] == weather_data
        assert result["notification"] == {"status": "error", "reason": "timeout"}
