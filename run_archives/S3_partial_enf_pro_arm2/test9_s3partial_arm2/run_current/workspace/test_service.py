"""Mock-based tests for service.py — 3 API calls + 1 composition function."""
from unittest.mock import MagicMock, patch

import pytest
import requests

import service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(json_data: dict):
    """Build a mock requests.Response that returns *json_data* from .json()."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ===================================================================
# 1. get_user
# ===================================================================

class TestGetUser:
    """Tests for get_user(user_id)."""

    @patch("service.requests.get")
    def test_get_user_success(self, mock_get):
        """Happy path: returns parsed JSON with user fields."""
        mock_get.return_value = _mock_response({
            "id": "123",
            "name": "Alice",
            "email": "alice@example.com",
        })

        result = service.get_user("123")

        mock_get.assert_called_once_with(
            "https://api.users.example.com/v1/users/123", timeout=10
        )
        assert result == {"id": "123", "name": "Alice", "email": "alice@example.com"}
        assert "id" in result and "name" in result and "email" in result

    @patch("service.requests.get")
    def test_get_user_http_error(self, mock_get):
        """Error path: HTTP 404 raises HTTPError."""
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = resp

        with pytest.raises(requests.exceptions.HTTPError):
            service.get_user("nonexistent")


# ===================================================================
# 2. get_weather
# ===================================================================

class TestGetWeather:
    """Tests for get_weather(city)."""

    @patch("service.requests.get")
    def test_get_weather_success(self, mock_get):
        """Happy path: returns weather data for a city."""
        mock_get.return_value = _mock_response({
            "city": "Beijing",
            "temp": 72,
            "humidity": 45,
            "condition": "Sunny",
        })

        result = service.get_weather("Beijing")

        mock_get.assert_called_once_with(
            "https://api.weather.example.com/v2/current",
            params={"city": "Beijing"},
            timeout=10,
        )
        assert result["city"] == "Beijing"
        assert result["temp"] == 72
        assert result["humidity"] == 45
        assert result["condition"] == "Sunny"

    @patch("service.requests.get")
    def test_get_weather_connection_error(self, mock_get):
        """Error path: ConnectionError propagates to caller."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        with pytest.raises(requests.exceptions.ConnectionError):
            service.get_weather("Shanghai")


# ===================================================================
# 3. send_notification
# ===================================================================

class TestSendNotification:
    """Tests for send_notification(user_id, message)."""

    @patch("service.requests.post")
    def test_send_notification_success(self, mock_post):
        """Happy path: POST succeeds and returns parsed JSON."""
        mock_post.return_value = _mock_response({
            "status": "sent",
            "message_id": "msg_001",
        })

        result = service.send_notification("user_42", "Hello!")

        mock_post.assert_called_once_with(
            "https://api.notify.example.com/v1/send",
            json={"user_id": "user_42", "message": "Hello!"},
            timeout=5,
        )
        assert result == {"status": "sent", "message_id": "msg_001"}

    @patch("service.requests.post")
    def test_send_notification_timeout(self, mock_post):
        """Error path: Timeout is caught → returns error dict."""
        mock_post.side_effect = requests.exceptions.Timeout("Read timed out")

        result = service.send_notification("user_42", "ping")

        assert result == {"status": "error", "reason": "timeout"}

    @patch("service.requests.post")
    def test_send_notification_connection_error(self, mock_post):
        """Error path: ConnectionError is caught → returns error dict."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Refused")

        result = service.send_notification("user_42", "ping")

        assert result == {"status": "error", "reason": "timeout"}


# ===================================================================
# 4. process_user_weather (composition)
# ===================================================================

class TestProcessUserWeather:
    """Tests for process_user_weather(user_id, city)."""

    @patch("service.requests.post")
    @patch("service.requests.get")
    def test_process_user_weather_success(self, mock_get, mock_post):
        """Integration-style: composes get_user → get_weather → send_notification."""
        # arrange
        mock_get.side_effect = [
            _mock_response({"id": "1", "name": "Bob", "email": "bob@example.com"}),
            _mock_response({"city": "Tokyo", "temp": 68, "humidity": 60, "condition": "Cloudy"}),
        ]
        mock_post.return_value = _mock_response({
            "status": "sent",
            "message_id": "msg_002",
        })

        # act
        result = service.process_user_weather("1", "Tokyo")

        # assert — get was called twice with correct arguments
        assert mock_get.call_count == 2
        mock_get.assert_any_call(
            "https://api.users.example.com/v1/users/1", timeout=10
        )
        mock_get.assert_any_call(
            "https://api.weather.example.com/v2/current",
            params={"city": "Tokyo"},
            timeout=10,
        )

        # assert — post was called with correct json body
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["user_id"] == "1"
        assert "Hi Bob, weather in Tokyo: 68F" in call_kwargs["json"]["message"]

        # assert — final return shape
        assert result["user"] == {"id": "1", "name": "Bob", "email": "bob@example.com"}
        assert result["weather"]["city"] == "Tokyo"
        assert result["notification"] == {"status": "sent", "message_id": "msg_002"}
