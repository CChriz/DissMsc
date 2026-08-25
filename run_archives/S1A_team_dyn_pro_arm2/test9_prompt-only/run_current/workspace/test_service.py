"""Test suite for service.py — mock-based tests for 3 external API calls."""
import pytest
import requests
from unittest.mock import Mock, patch

from service import get_user, get_weather, send_notification, process_user_weather


# ---------------------------------------------------------------------------
# Helper: create a fake requests.Response with controlled json() and
# raise_for_status().
# ---------------------------------------------------------------------------
def create_mock_response(json_data: dict) -> Mock:
    """Return a Mock that mimics a successful requests.Response."""
    mock_resp = Mock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = json_data
    return mock_resp


# ===================================================================
# 1. get_user — success path
# ===================================================================
class TestGetUser:
    def test_success(self):
        """get_user returns the expected user dict and calls the correct URL."""
        user_data = {"id": "123", "name": "Alice", "email": "alice@example.com"}

        with patch("service.requests.get") as mock_get:
            mock_get.return_value = create_mock_response(user_data)

            result = get_user("123")

            assert result == user_data
            mock_get.assert_called_once_with(
                "https://api.users.example.com/v1/users/123", timeout=10
            )


# ===================================================================
# 2. get_weather — success path
# ===================================================================
class TestGetWeather:
    def test_success(self):
        """get_weather returns the expected weather dict with correct params."""
        weather_data = {"city": "NYC", "temp": 72, "condition": "sunny"}

        with patch("service.requests.get") as mock_get:
            mock_get.return_value = create_mock_response(weather_data)

            result = get_weather("NYC")

            assert result == weather_data
            mock_get.assert_called_once_with(
                "https://api.weather.example.com/v2/current",
                params={"city": "NYC"},
                timeout=10,
            )


# ===================================================================
# 3. send_notification — success path
# ===================================================================
class TestSendNotification:
    def test_success(self):
        """send_notification posts correct JSON and returns expected response."""
        notify_data = {"status": "ok", "message_id": "msg_456"}

        with patch("service.requests.post") as mock_post:
            mock_post.return_value = create_mock_response(notify_data)

            result = send_notification("123", "Hello")

            assert result == notify_data
            mock_post.assert_called_once_with(
                "https://api.notify.example.com/v1/send",
                json={"user_id": "123", "message": "Hello"},
                timeout=5,
            )


# ===================================================================
# 4. send_notification — timeout error
# ===================================================================
class TestSendNotificationTimeout:
    def test_timeout(self):
        """send_notification catches Timeout and returns error dict."""
        with patch("service.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout

            result = send_notification("123", "Hello")

            assert result == {"status": "error", "reason": "timeout"}


# ===================================================================
# 5. send_notification — connection error
# ===================================================================
class TestSendNotificationConnectionError:
    def test_connection_error(self):
        """send_notification catches ConnectionError and returns error dict."""
        with patch("service.requests.post") as mock_post:
            mock_post.side_effect = requests.exceptions.ConnectionError

            result = send_notification("123", "Hello")

            assert result == {"status": "error", "reason": "connection_error"}


# ===================================================================
# 6. process_user_weather — integration scenario
# ===================================================================
class TestProcessUserWeather:
    def test_success(self):
        """process_user_weather chains all three APIs and returns combined result."""
        user_mock = create_mock_response(
            {"id": "123", "name": "Alice", "email": "alice@example.com"}
        )
        weather_mock = create_mock_response(
            {"city": "NYC", "temp": 72, "condition": "sunny"}
        )
        notify_mock = create_mock_response(
            {"status": "ok", "message_id": "msg_456"}
        )

        with patch("service.requests.get") as mock_get, \
             patch("service.requests.post") as mock_post:

            mock_get.side_effect = [user_mock, weather_mock]
            mock_post.return_value = notify_mock

            result = process_user_weather("123", "NYC")

            # Top-level keys
            assert "user" in result
            assert "weather" in result
            assert "notification" in result

            # Sub-dict content
            assert result["user"]["name"] == "Alice"
            assert result["weather"]["city"] == "NYC"
            assert result["notification"]["status"] == "ok"

            # Verify the notification message contains key details
            call_kwargs = mock_post.call_args[1]
            sent_message = call_kwargs["json"]["message"]
            assert "Alice" in sent_message
            assert "NYC" in sent_message
            assert "72F" in sent_message


# ===================================================================
# 7. get_user — URL assertion
# ===================================================================
class TestGetUserUrlAssertion:
    def test_url_assertion(self):
        """get_user constructs the exact URL with the given user_id."""
        user_data = {"id": "456", "name": "Bob", "email": "bob@example.com"}

        with patch("service.requests.get") as mock_get:
            mock_get.return_value = create_mock_response(user_data)

            result = get_user("456")

            mock_get.assert_called_once_with(
                "https://api.users.example.com/v1/users/456", timeout=10
            )
            assert result["id"] == "456"


# ===================================================================
# 8. get_weather — params assertion
# ===================================================================
class TestGetWeatherParamsAssertion:
    def test_params_assertion(self):
        """get_weather passes the city as a query parameter."""
        weather_data = {"city": "London", "temp": 55, "condition": "cloudy"}

        with patch("service.requests.get") as mock_get:
            mock_get.return_value = create_mock_response(weather_data)

            result = get_weather("London")

            # Verify the query-params dict
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs["params"] == {"city": "London"}
            assert result["city"] == "London"


# ===================================================================
# 9. send_notification — payload assertion
# ===================================================================
class TestSendNotificationPayloadAssertion:
    def test_payload_assertion(self):
        """send_notification sends the exact JSON payload with timeout=5."""
        notify_data = {"status": "ok", "message_id": "msg_789"}

        with patch("service.requests.post") as mock_post:
            mock_post.return_value = create_mock_response(notify_data)

            send_notification("789", "Test message")

            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"] == {
                "user_id": "789",
                "message": "Test message",
            }
            assert call_kwargs["timeout"] == 5


# ===================================================================
# 10. process_user_weather — return-value shape assertion
# ===================================================================
class TestProcessUserWeatherShape:
    def test_shape_assertion(self):
        """process_user_weather returns a dict with well-formed sub-dicts."""
        user_mock = create_mock_response(
            {"id": "456", "name": "Bob", "email": "bob@example.com"}
        )
        weather_mock = create_mock_response(
            {"city": "Paris", "temp": 68, "condition": "rainy"}
        )
        notify_mock = create_mock_response(
            {"status": "ok", "message_id": "msg_999"}
        )

        with patch("service.requests.get") as mock_get, \
             patch("service.requests.post") as mock_post:

            mock_get.side_effect = [user_mock, weather_mock]
            mock_post.return_value = notify_mock

            result = process_user_weather("456", "Paris")

            # Top-level type and keys
            assert isinstance(result, dict)
            assert set(result.keys()) == {"user", "weather", "notification"}

            # User sub-dict shape
            assert "id" in result["user"]
            assert "name" in result["user"]
            assert "email" in result["user"]

            # Weather sub-dict shape
            assert "city" in result["weather"]
            assert "temp" in result["weather"]
            assert "condition" in result["weather"]

            # Notification sub-dict shape
            assert "status" in result["notification"]
            assert "message_id" in result["notification"]
