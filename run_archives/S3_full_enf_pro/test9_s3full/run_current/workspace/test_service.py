"""Mock-based tests for service.py covering all 3 external API calls."""
import pytest
from unittest.mock import patch, Mock
import requests

import service


# ---------------------------------------------------------------------------
# get_user tests
# ---------------------------------------------------------------------------

@patch("service.requests.get")
def test_get_user_success(mock_get):
    """Verify get_user returns expected data and calls the correct URL."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "42",
        "name": "Alice",
        "email": "alice@example.com",
    }
    mock_get.return_value = mock_response

    result = service.get_user("42")

    # Assert URL / endpoint
    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/42", timeout=10
    )
    # Assert return value shape
    assert result == {"id": "42", "name": "Alice", "email": "alice@example.com"}


@patch("service.requests.get")
def test_get_user_response_shape(mock_get):
    """Verify get_user returns a dict with the required keys."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "7",
        "name": "Bob",
        "email": "bob@example.com",
    }
    mock_get.return_value = mock_response

    result = service.get_user("7")

    assert isinstance(result, dict)
    assert "id" in result
    assert "name" in result
    assert "email" in result


@patch("service.requests.get")
def test_get_user_passes_correct_user_id(mock_get):
    """Verify get_user passes the correct user_id in the URL."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "99", "name": "X", "email": "x@x.com"}
    mock_get.return_value = mock_response

    service.get_user("99")

    call_args = mock_get.call_args
    url = call_args[0][0]
    assert "/users/99" in url


# ---------------------------------------------------------------------------
# get_weather tests
# ---------------------------------------------------------------------------

@patch("service.requests.get")
def test_get_weather_success(mock_get):
    """Verify get_weather returns expected data and calls the correct endpoint."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "city": "London",
        "temp": 18,
        "condition": "cloudy",
        "humidity": 72,
    }
    mock_get.return_value = mock_response

    result = service.get_weather("London")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "London"},
        timeout=10,
    )
    assert result == {
        "city": "London",
        "temp": 18,
        "condition": "cloudy",
        "humidity": 72,
    }


@patch("service.requests.get")
def test_get_weather_response_shape(mock_get):
    """Verify get_weather returns a dict with required weather keys."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "city": "Paris",
        "temp": 25,
        "condition": "sunny",
        "humidity": 40,
    }
    mock_get.return_value = mock_response

    result = service.get_weather("Paris")

    assert isinstance(result, dict)
    assert "city" in result
    assert "temp" in result
    assert "condition" in result
    assert "humidity" in result


@patch("service.requests.get")
def test_get_weather_passes_correct_city(mock_get):
    """Verify get_weather passes the correct city parameter."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "city": "Tokyo",
        "temp": 30,
        "condition": "rainy",
        "humidity": 85,
    }
    mock_get.return_value = mock_response

    service.get_weather("Tokyo")

    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["params"] == {"city": "Tokyo"}


# ---------------------------------------------------------------------------
# send_notification tests
# ---------------------------------------------------------------------------

@patch("service.requests.post")
def test_send_notification_success(mock_post):
    """Verify send_notification returns expected response and calls POST correctly."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "sent", "message_id": "msg_abc"}
    mock_post.return_value = mock_response

    result = service.send_notification("user1", "Hello!")

    mock_post.assert_called_once_with(
        "https://api.notify.example.com/v1/send",
        json={"user_id": "user1", "message": "Hello!"},
        timeout=5,
    )
    assert result == {"status": "sent", "message_id": "msg_abc"}


@patch("service.requests.post")
def test_send_notification_timeout(mock_post):
    """Verify send_notification returns error dict on Timeout instead of crashing."""
    mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

    result = service.send_notification("user1", "test")

    assert result == {"status": "error", "reason": "timeout"}


@patch("service.requests.post")
def test_send_notification_connection_error(mock_post):
    """Verify send_notification returns error dict on ConnectionError."""
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

    result = service.send_notification("user2", "test")

    assert result == {"status": "error", "reason": "connection_error"}


# ---------------------------------------------------------------------------
# process_user_weather integration test
# ---------------------------------------------------------------------------

@patch("service.send_notification")
@patch("service.get_weather")
@patch("service.get_user")
def test_process_user_weather_integration(
    mock_get_user, mock_get_weather, mock_send_notification
):
    """Verify process_user_weather chains all three calls and returns combined dict."""
    mock_get_user.return_value = {"id": "1", "name": "Carol", "email": "c@c.com"}
    mock_get_weather.return_value = {
        "city": "Berlin",
        "temp": 20,
        "condition": "windy",
        "humidity": 50,
    }
    mock_send_notification.return_value = {"status": "sent", "message_id": "msg_xyz"}

    result = service.process_user_weather("1", "Berlin")

    # Verify get_user / get_weather were called with correct args
    mock_get_user.assert_called_once_with("1")
    mock_get_weather.assert_called_once_with("Berlin")

    # Verify send_notification was called with a message containing user name & city
    mock_send_notification.assert_called_once()
    call_args = mock_send_notification.call_args
    assert call_args[0][0] == "1"  # user_id
    notification_msg = call_args[0][1]
    assert "Carol" in notification_msg
    assert "Berlin" in notification_msg

    # Verify combined result shape
    assert "user" in result
    assert "weather" in result
    assert "notification" in result
    assert result["user"]["name"] == "Carol"
    assert result["weather"]["city"] == "Berlin"
    assert result["notification"]["status"] == "sent"
