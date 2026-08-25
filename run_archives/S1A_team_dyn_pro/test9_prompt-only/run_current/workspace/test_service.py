"""Tests for service.py — all 3 API calls are mocked via unittest.mock."""
import service
import requests
from unittest.mock import patch, Mock


# ---------------------------------------------------------------------------
# Helper: build a mock response object with a given JSON payload
# ---------------------------------------------------------------------------
def _mock_response(json_data: dict) -> Mock:
    """Return a Mock that behaves like a requests.Response."""
    resp = Mock()
    resp.raise_for_status = Mock(return_value=None)
    resp.json.return_value = json_data
    return resp


# ===========================================================================
# get_user tests
# ===========================================================================

class TestGetUser:

    @patch("service.requests.get")
    def test_get_user_calls_correct_endpoint(self, mock_get):
        """Assert URL and timeout are correct."""
        mock_get.return_value = _mock_response({"id": "42", "name": "Alice"})

        service.get_user("42")

        mock_get.assert_called_once_with(
            "https://api.users.example.com/v1/users/42",
            timeout=10,
        )

    @patch("service.requests.get")
    def test_get_user_returns_expected_shape(self, mock_get):
        """Assert return value has expected keys and values."""
        mock_get.return_value = _mock_response(
            {"id": "99", "name": "Bob", "email": "bob@test.com"}
        )

        result = service.get_user("99")

        assert result == {"id": "99", "name": "Bob", "email": "bob@test.com"}
        assert "id" in result
        assert "name" in result
        assert "email" in result

    @patch("service.requests.get")
    def test_get_user_different_ids(self, mock_get):
        """Assert different user_ids produce different URLs and results."""

        def side_effect(url, **kwargs):
            if "users/1" in url:
                return _mock_response({"id": "1", "name": "Alice"})
            return _mock_response({"id": "2", "name": "Bob"})

        mock_get.side_effect = side_effect

        r1 = service.get_user("1")
        r2 = service.get_user("2")

        assert r1 == {"id": "1", "name": "Alice"}
        assert r2 == {"id": "2", "name": "Bob"}

        # Check that two calls were made with distinct URLs
        assert mock_get.call_count == 2
        call_urls = [c[0][0] for c in mock_get.call_args_list]
        assert "users/1" in call_urls[0]
        assert "users/2" in call_urls[1]


# ===========================================================================
# get_weather tests
# ===========================================================================

class TestGetWeather:

    @patch("service.requests.get")
    def test_get_weather_calls_correct_endpoint(self, mock_get):
        """Assert URL, query params, and timeout are correct."""
        mock_get.return_value = _mock_response(
            {"city": "London", "temp": 55}
        )

        service.get_weather("London")

        mock_get.assert_called_once_with(
            "https://api.weather.example.com/v2/current",
            params={"city": "London"},
            timeout=10,
        )

    @patch("service.requests.get")
    def test_get_weather_returns_expected_shape(self, mock_get):
        """Assert return value reflects the mocked weather data."""
        mock_get.return_value = _mock_response(
            {"city": "Tokyo", "temp": 80, "condition": "cloudy"}
        )

        result = service.get_weather("Tokyo")

        assert result["city"] == "Tokyo"
        assert result["temp"] == 80
        assert result["condition"] == "cloudy"


# ===========================================================================
# send_notification tests
# ===========================================================================

class TestSendNotification:

    @patch("service.requests.post")
    def test_send_notification_success_calls_correct_endpoint(self, mock_post):
        """Assert URL, json body, and timeout are correct."""
        mock_post.return_value = _mock_response(
            {"status": "ok", "message_id": "abc"}
        )

        service.send_notification("user1", "Hello!")

        mock_post.assert_called_once_with(
            "https://api.notify.example.com/v1/send",
            json={"user_id": "user1", "message": "Hello!"},
            timeout=5,
        )

    @patch("service.requests.post")
    def test_send_notification_success_returns_response(self, mock_post):
        """Assert the response dict is returned verbatim."""
        mock_post.return_value = _mock_response(
            {"status": "ok", "message_id": "xyz789"}
        )

        result = service.send_notification("u2", "Test msg")

        assert result == {"status": "ok", "message_id": "xyz789"}

    @patch("service.requests.post")
    def test_send_notification_handles_timeout(self, mock_post):
        """Timeout → graceful error dict, no exception raised."""
        mock_post.side_effect = requests.exceptions.Timeout()

        result = service.send_notification("u3", "msg")

        assert result == {"status": "error", "reason": "timeout"}

    @patch("service.requests.post")
    def test_send_notification_handles_connection_error(self, mock_post):
        """ConnectionError → graceful error dict, no exception raised."""
        mock_post.side_effect = requests.exceptions.ConnectionError()

        result = service.send_notification("u4", "msg")

        assert result == {"status": "error", "reason": "timeout"}


# ===========================================================================
# Integration test — process_user_weather
# ===========================================================================

class TestProcessUserWeather:

    @patch("service.requests.post")
    @patch("service.requests.get")
    def test_process_user_weather_integration(self, mock_get, mock_post):
        """End-to-end test: mock get (twice) + post, assert combined result."""
        # get is called twice: first for user, then for weather
        mock_get.side_effect = [
            _mock_response({"id": "42", "name": "Alice"}),
            _mock_response({"city": "Paris", "temp": 62}),
        ]
        mock_post.return_value = _mock_response(
            {"status": "ok", "message_id": "n_1"}
        )

        result = service.process_user_weather("42", "Paris")

        assert result["user"]["name"] == "Alice"
        assert result["weather"]["temp"] == 62
        assert result["notification"]["status"] == "ok"
