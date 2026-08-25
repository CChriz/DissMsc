"""Mock-based tests for the external API calls in service.py."""
import requests
import pytest
from unittest.mock import Mock, patch

import service


@patch("service.requests.get")
def test_get_user_success(mock_get):
    resp = Mock()
    resp.json.return_value = {"id": "u_123", "name": "Alice", "email": "alice@example.com"}
    resp.status_code = 200
    mock_get.return_value = resp

    result = service.get_user("u_123")

    assert isinstance(result, dict)
    assert result == {"id": "u_123", "name": "Alice", "email": "alice@example.com"}
    mock_get.assert_called_once()


@patch("service.requests.get")
def test_get_user_calls_correct_url_and_params(mock_get):
    resp = Mock()
    resp.json.return_value = {}
    mock_get.return_value = resp

    service.get_user("u_123")

    url = mock_get.call_args.args[0]
    assert url == "https://api.users.example.com/v1/users/u_123"
    assert "u_123" in url
    mock_get.assert_called_once()


@patch("service.requests.get")
def test_get_weather_success(mock_get):
    resp = Mock()
    resp.json.return_value = {"city": "London", "temp": 72, "condition": "Cloudy"}
    resp.status_code = 200
    mock_get.return_value = resp

    result = service.get_weather("London")

    assert isinstance(result, dict)
    assert result == {"city": "London", "temp": 72, "condition": "Cloudy"}
    mock_get.assert_called_once()


@patch("service.requests.get")
def test_get_weather_calls_correct_url_and_params(mock_get):
    resp = Mock()
    resp.json.return_value = {}
    mock_get.return_value = resp

    service.get_weather("London")

    assert mock_get.call_args.args[0] == "https://api.weather.example.com/v2/current"
    assert mock_get.call_args.kwargs["params"] == {"city": "London"}
    mock_get.assert_called_once()


@patch("service.requests.post")
def test_send_notification_success(mock_post):
    resp = Mock()
    resp.json.return_value = {"status": "sent", "message_id": "msg_1"}
    resp.status_code = 200
    mock_post.return_value = resp

    result = service.send_notification("u_123", "Hello")

    assert isinstance(result, dict)
    assert result == {"status": "sent", "message_id": "msg_1"}
    assert mock_post.call_args.args[0] == "https://api.notify.example.com/v1/send"
    assert mock_post.call_args.kwargs["json"] == {"user_id": "u_123", "message": "Hello"}
    mock_post.assert_called_once()


@patch("service.requests.post", side_effect=requests.exceptions.Timeout("boom"))
def test_send_notification_timeout_returns_error_dict(mock_post):
    result = service.send_notification("u_123", "Hello")

    assert result == {"status": "error", "reason": "timeout"}
    assert result["status"] == "error"
    mock_post.assert_called_once()


@patch("service.requests.post", side_effect=requests.exceptions.ConnectionError("refused"))
def test_send_notification_connection_error_returns_error_dict(mock_post):
    result = service.send_notification("u_123", "Hello")

    assert result == {"status": "error", "reason": "connection_error"}
    assert result["status"] == "error"
    mock_post.assert_called_once()


@patch("service.requests.get")
def test_get_user_http_error_raises(mock_get):
    resp = Mock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error")
    mock_get.return_value = resp

    with pytest.raises(requests.exceptions.HTTPError):
        service.get_user("u_123")


@patch("service.requests.get")
def test_get_weather_http_error_raises(mock_get):
    resp = Mock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    mock_get.return_value = resp

    with pytest.raises(requests.exceptions.HTTPError):
        service.get_weather("London")


@patch("service.requests.post")
def test_send_notification_http_error_raises(mock_post):
    resp = Mock()
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Bad Request")
    mock_post.return_value = resp

    with pytest.raises(requests.exceptions.HTTPError):
        service.send_notification("u_123", "Hello")
