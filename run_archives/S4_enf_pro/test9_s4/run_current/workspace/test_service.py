import pytest
from unittest.mock import patch, Mock
import requests
import service


class TestGetUser:
    """Tests for get_user function."""

    @patch('service.requests.get')
    def test_get_user_success(self, mock_get):
        """Test successful get_user returns expected user dict."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": 1, "name": "Alice", "email": "alice@example.com"
        }
        mock_get.return_value = mock_response

        result = service.get_user("1")

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "users" in call_url
        assert "1" in call_url
        assert result == {"id": 1, "name": "Alice", "email": "alice@example.com"}

    @patch('service.requests.get')
    def test_get_user_not_found(self, mock_get):
        """Test get_user with 404 raises HTTPError via raise_for_status."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError("404 Client Error")
        )
        mock_get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            service.get_user("999")


class TestGetWeather:
    """Tests for get_weather function."""

    @patch('service.requests.get')
    def test_get_weather_success(self, mock_get):
        """Test successful get_weather returns expected weather dict."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "city": "Beijing", "temperature": 22, "conditions": "Sunny"
        }
        mock_get.return_value = mock_response

        result = service.get_weather("Beijing")

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "weather" in call_url
        assert "Beijing" in call_url
        assert result == {"city": "Beijing", "temperature": 22, "conditions": "Sunny"}

    @patch('service.requests.get')
    def test_get_weather_city_invalid(self, mock_get):
        """Test get_weather with 400 raises HTTPError via raise_for_status."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError("400 Bad Request")
        )
        mock_get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            service.get_weather("")


class TestSendNotification:
    """Tests for send_notification function."""

    @patch('service.requests.post')
    def test_send_notification_success(self, mock_post):
        """Test successful send_notification returns status dict."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"status": "sent"}
        mock_post.return_value = mock_response

        result = service.send_notification("1", "Hello")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        call_url = call_args[0][0]
        assert "notify" in call_url
        assert call_args[1]["json"] == {"user_id": "1", "message": "Hello"}
        assert result == {"status": "sent"}

    @patch('service.requests.post')
    def test_send_notification_timeout(self, mock_post):
        """Test send_notification catches Timeout and returns error dict."""
        mock_post.side_effect = requests.exceptions.Timeout

        result = service.send_notification("1", "test")

        assert result == {"status": "error", "reason": "timeout"}

    @patch('service.requests.post')
    def test_send_notification_connection_error(self, mock_post):
        """Test send_notification catches ConnectionError and returns error dict."""
        mock_post.side_effect = requests.exceptions.ConnectionError

        result = service.send_notification("1", "test")

        assert result == {"status": "error", "reason": "connection_error"}

    @patch('service.requests.post')
    def test_send_notification_server_error(self, mock_post):
        """Test send_notification with 500 raises HTTPError via raise_for_status."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError("500 Server Error")
        )
        mock_post.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            service.send_notification("1", "test")
