"""Mock-based tests for service.py API calls."""
from unittest.mock import patch, Mock

import pytest
import requests

import service


# ─── get_user ───────────────────────────────────────────────────────────────

def test_get_user_success():
    """get_user should return user dict on 200 OK."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1, "name": "Alice", "email": "alice@example.com"}

    with patch("service.requests.get", return_value=mock_response) as mock_get:
        result = service.get_user("1")

    mock_get.assert_called_once()
    assert result == {"id": 1, "name": "Alice", "email": "alice@example.com"}


def test_get_user_returns_correct_shape():
    """get_user return dict must contain id, name, email."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 42, "name": "Bob", "email": "bob@test.com"}

    with patch("service.requests.get", return_value=mock_response):
        result = service.get_user("42")

    assert "id" in result
    assert "name" in result
    assert "email" in result
    assert result["id"] == 42
    assert result["name"] == "Bob"
    assert result["email"] == "bob@test.com"


def test_get_user_url_and_params():
    """get_user must call GET with correct URL containing user_id."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 99, "name": "X", "email": "x@x.com"}

    with patch("service.requests.get", return_value=mock_response) as mock_get:
        service.get_user("99")

    mock_get.assert_called_once()
    called_url = mock_get.call_args[0][0]
    assert "/users/99" in called_url


# ─── get_weather ────────────────────────────────────────────────────────────

def test_get_weather_success():
    """get_weather should return weather dict on 200 OK."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"city": "Beijing", "temp": 72, "desc": "sunny"}

    with patch("service.requests.get", return_value=mock_response) as mock_get:
        result = service.get_weather("Beijing")

    mock_get.assert_called_once()
    assert result == {"city": "Beijing", "temp": 72, "desc": "sunny"}


def test_get_weather_returns_correct_shape():
    """get_weather return dict must contain city, temp, desc."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"city": "Tokyo", "temp": 60, "desc": "cloudy"}

    with patch("service.requests.get", return_value=mock_response):
        result = service.get_weather("Tokyo")

    assert "city" in result
    assert "temp" in result
    assert "desc" in result


def test_get_weather_url_and_params():
    """get_weather must call GET with city as query param."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"city": "Tokyo", "temp": 60, "desc": "cloudy"}

    with patch("service.requests.get", return_value=mock_response) as mock_get:
        service.get_weather("Tokyo")

    mock_get.assert_called_once()
    # Verify city param is passed
    _, kwargs = mock_get.call_args
    assert kwargs.get("params") == {"city": "Tokyo"}


# ─── send_notification ─────────────────────────────────────────────────────

def test_send_notification_success():
    """send_notification should POST and return response on success."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success", "message": "sent"}

    with patch("service.requests.post", return_value=mock_response) as mock_post:
        result = service.send_notification("1", "Hello")

    mock_post.assert_called_once()
    assert result == {"status": "success", "message": "sent"}


def test_send_notification_timeout():
    """send_notification must return error dict on Timeout, not crash."""
    with patch("service.requests.post", side_effect=requests.exceptions.Timeout):
        result = service.send_notification("1", "test")

    assert result == {"status": "error", "message": "timeout"}


def test_send_notification_connection_error():
    """send_notification must return error dict on ConnectionError, not crash."""
    with patch("service.requests.post", side_effect=requests.exceptions.ConnectionError):
        result = service.send_notification("1", "test")

    assert result["status"] == "error"
    assert "connection" in result["message"]


def test_send_notification_payload():
    """send_notification must POST correct JSON payload."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success"}

    with patch("service.requests.post", return_value=mock_response) as mock_post:
        service.send_notification("5", "Hi there")

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["user_id"] == "5"
    assert kwargs["json"]["message"] == "Hi there"
