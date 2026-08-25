"""Mock-based tests for service.py's 3 external API calls.

All external HTTP calls are mocked so the suite makes no real network
requests and does not depend on network availability.
"""
import requests
from unittest.mock import Mock, patch

import service


def _mock_response(payload):
    """Build a fake requests.Response whose .json() returns *payload*."""
    resp = Mock()
    resp.json.return_value = payload
    return resp


# ---------------------------------------------------------------------------
# get_user — user API (GET https://api.users.example.com/v1/users/{user_id})
# ---------------------------------------------------------------------------

def test_get_user_calls_correct_url():
    with patch("service.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"id": 123, "name": "Alice"})

        result = service.get_user("123")

        assert mock_get.call_args[0][0] == "https://api.users.example.com/v1/users/123"
        assert result == {"id": 123, "name": "Alice"}


def test_get_user_passes_user_id_in_url_and_timeout():
    with patch("service.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"id": 42, "name": "Bob"})

        service.get_user("42")

        assert mock_get.call_args[0][0].endswith("/users/42")
        assert mock_get.call_args.kwargs["timeout"] == 10


def test_get_user_returns_expected_shape():
    with patch("service.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"id": 7, "name": "Carol"})

        result = service.get_user("7")

        assert isinstance(result, dict)
        assert set(result.keys()) == {"id", "name"}


# ---------------------------------------------------------------------------
# get_weather — weather API (GET https://api.weather.example.com/v2/current?city=...)
# ---------------------------------------------------------------------------

def test_get_weather_calls_correct_url():
    with patch("service.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"city": "Paris", "temp": 72})

        result = service.get_weather("Paris")

        assert mock_get.call_args[0][0] == "https://api.weather.example.com/v2/current"
        assert result == {"city": "Paris", "temp": 72}


def test_get_weather_passes_city_param():
    with patch("service.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"city": "London", "temp": 60})

        service.get_weather("London")

        assert mock_get.call_args.kwargs["params"] == {"city": "London"}
        assert mock_get.call_args.kwargs["timeout"] == 10


def test_get_weather_returns_expected_shape():
    with patch("service.requests.get") as mock_get:
        mock_get.return_value = _mock_response({"city": "Tokyo", "temp": 85})

        result = service.get_weather("Tokyo")

        assert isinstance(result, dict)
        assert "city" in result
        assert "temp" in result


# ---------------------------------------------------------------------------
# send_notification — notification API (POST https://api.notify.example.com/v1/send)
# ---------------------------------------------------------------------------

def test_send_notification_calls_correct_url():
    with patch("service.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "sent"})

        result = service.send_notification("1", "hello")

        assert mock_post.call_args[0][0] == "https://api.notify.example.com/v1/send"
        assert result == {"status": "sent"}


def test_send_notification_passes_payload():
    with patch("service.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "sent"})

        service.send_notification("42", "hi there")

        assert mock_post.call_args.kwargs["json"] == {
            "user_id": "42",
            "message": "hi there",
        }
        assert mock_post.call_args.kwargs["timeout"] == 5


def test_send_notification_returns_expected_shape_on_success():
    with patch("service.requests.post") as mock_post:
        mock_post.return_value = _mock_response({"status": "sent", "id": "n1"})

        result = service.send_notification("1", "hi")

        assert isinstance(result, dict)
        assert result["status"] == "sent"


def test_send_notification_handles_timeout_gracefully():
    with patch("service.requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        result = service.send_notification("1", "hello")

        assert result == {"status": "error", "reason": "timeout"}


def test_send_notification_handles_connection_error_gracefully():
    with patch("service.requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError("connection refused")

        result = service.send_notification("1", "hello")

        assert result == {"status": "error", "reason": "timeout"}
