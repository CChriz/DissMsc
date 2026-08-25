"""Mock-based tests for service.py API calls."""
import pytest
import requests
from unittest.mock import patch, Mock

# ============================================================
# A. get_user(user_id) — 4 tests
# ============================================================


class TestGetUser:
    """Mock tests for get_user()."""

    @patch("service.requests.get")
    def test_get_user_success(self, mock_get):
        """Verify get_user returns correct user data on 200 OK."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "name": "Alice",
            "email": "alice@example.com",
        }
        mock_get.return_value = mock_response

        from service import get_user
        result = get_user(123)

        assert result is not None
        assert result["id"] == 123
        assert result["name"] == "Alice"
        assert result["email"] == "alice@example.com"
        mock_get.assert_called_once()

    @patch("service.requests.get")
    def test_get_user_url_and_params(self, mock_get):
        """Verify get_user calls the correct URL with correct user_id."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 456,
            "name": "Bob",
            "email": "bob@example.com",
        }
        mock_get.return_value = mock_response

        from service import get_user
        get_user(456)

        call_args = mock_get.call_args
        url = call_args[0][0]
        assert "/users/456" in url
        assert "timeout" in call_args[1]

    @patch("service.requests.get")
    def test_get_user_response_shape(self, mock_get):
        """Verify get_user returns a dict with correct keys and types."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 789,
            "name": "Charlie",
            "email": "charlie@example.com",
        }
        mock_get.return_value = mock_response

        from service import get_user
        result = get_user(789)

        assert isinstance(result, dict)
        assert set(result.keys()) == {"id", "name", "email"}
        assert isinstance(result["id"], int)
        assert isinstance(result["name"], str)
        assert isinstance(result["email"], str)

    @patch("service.requests.get")
    def test_get_user_not_found(self, mock_get):
        """Verify get_user raises HTTPError for 404 responses."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError("404 Not Found")
        )
        mock_get.return_value = mock_response

        from service import get_user
        with pytest.raises(requests.exceptions.HTTPError):
            get_user(999)


# ============================================================
# B. get_weather(city) — 3 tests
# ============================================================


class TestGetWeather:
    """Mock tests for get_weather()."""

    @patch("service.requests.get")
    def test_get_weather_success(self, mock_get):
        """Verify get_weather returns correct weather data on 200 OK."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "city": "Beijing",
            "temp": 22,
            "condition": "sunny",
        }
        mock_get.return_value = mock_response

        from service import get_weather
        result = get_weather("Beijing")

        assert result is not None
        assert result["city"] == "Beijing"
        assert result["temp"] == 22
        assert result["condition"] == "sunny"
        mock_get.assert_called_once()

    @patch("service.requests.get")
    def test_get_weather_url_and_params(self, mock_get):
        """Verify get_weather calls correct URL and passes city parameter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "city": "Shanghai",
            "temp": 25,
            "condition": "cloudy",
        }
        mock_get.return_value = mock_response

        from service import get_weather
        get_weather("Shanghai")

        call_args = mock_get.call_args
        url = call_args[0][0]
        assert "/current" in url
        assert call_args[1]["params"] == {"city": "Shanghai"}
        assert "timeout" in call_args[1]

    @patch("service.requests.get")
    def test_get_weather_response_shape(self, mock_get):
        """Verify get_weather returns dict with correct keys and types."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "city": "Shenzhen",
            "temp": 30,
            "condition": "rainy",
        }
        mock_get.return_value = mock_response

        from service import get_weather
        result = get_weather("Shenzhen")

        assert isinstance(result, dict)
        assert set(result.keys()) == {"city", "temp", "condition"}
        assert isinstance(result["city"], str)
        assert isinstance(result["temp"], (int, float))
        assert isinstance(result["condition"], str)


# ============================================================
# C. send_notification(user_id, message) — 3 tests
# ============================================================


class TestSendNotification:
    """Mock tests for send_notification() including error handling."""

    @patch("service.requests.post")
    def test_send_notification_success(self, mock_post):
        """Verify send_notification returns ok status on success."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "sent"}
        mock_post.return_value = mock_response

        from service import send_notification
        result = send_notification("user123", "Hello!")

        assert result["status"] == "ok"
        assert "data" in result
        assert result["data"]["status"] == "sent"
        mock_post.assert_called_once()

        # Verify correct URL and payload
        call_args = mock_post.call_args
        url = call_args[0][0]
        assert "/send" in url
        assert call_args[1]["json"]["user_id"] == "user123"
        assert call_args[1]["json"]["message"] == "Hello!"

    @patch("service.requests.post")
    def test_send_notification_timeout(self, mock_post):
        """Verify send_notification returns error dict on timeout, does not crash."""
        mock_post.side_effect = requests.exceptions.Timeout()

        from service import send_notification
        result = send_notification("user456", "Test message")

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "timeout" in result["error"].lower()

    @patch("service.requests.post")
    def test_send_notification_connection_error(self, mock_post):
        """Verify send_notification returns error dict on connection error."""
        mock_post.side_effect = requests.exceptions.ConnectionError()

        from service import send_notification
        result = send_notification("user789", "Another message")

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "connection" in result["error"].lower()
