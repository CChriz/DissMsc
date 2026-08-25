"""Mock-based tests for the 3 external API calls in ``service.py``.

Every ``requests.*`` call made by the functions under test is patched at the
module-reference level (``service.requests.get`` / ``service.requests.post``)
so that no real network request is ever issued.
"""
from unittest.mock import Mock, patch

import requests

import service


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------

@patch("service.requests.get")
def test_get_user_calls_correct_endpoint(mock_get):
    mock_resp = Mock()
    mock_resp.json.return_value = {"id": "123", "name": "Alice"}
    mock_get.return_value = mock_resp

    service.get_user("123")

    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "https://api.users.example.com/v1/users/123"


@patch("service.requests.get")
def test_get_user_includes_user_id_in_path(mock_get):
    mock_resp = Mock()
    mock_resp.json.return_value = {"id": "42", "name": "Bob"}
    mock_get.return_value = mock_resp

    service.get_user("42")

    url = mock_get.call_args.args[0]
    assert url.endswith("/42")
    # user_id is embedded in the path, not passed as a query parameter
    assert mock_get.call_args.kwargs.get("params") is None


@patch("service.requests.get")
def test_get_user_returns_expected_shape(mock_get):
    expected = {"id": "123", "name": "Alice"}
    mock_resp = Mock()
    mock_resp.json.return_value = expected
    mock_get.return_value = mock_resp

    result = service.get_user("123")

    assert result == expected
    assert set(result.keys()) == {"id", "name"}


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------

@patch("service.requests.get")
def test_get_weather_calls_correct_endpoint(mock_get):
    mock_resp = Mock()
    mock_resp.json.return_value = {"city": "London", "temp": 72, "condition": "Sunny"}
    mock_get.return_value = mock_resp

    service.get_weather("London")

    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "https://api.weather.example.com/v2/current"


@patch("service.requests.get")
def test_get_weather_passes_city_param(mock_get):
    mock_resp = Mock()
    mock_resp.json.return_value = {"city": "Paris", "temp": 68, "condition": "Cloudy"}
    mock_get.return_value = mock_resp

    service.get_weather("Paris")

    assert mock_get.call_args.kwargs["params"] == {"city": "Paris"}


@patch("service.requests.get")
def test_get_weather_returns_expected_shape(mock_get):
    expected = {"city": "Paris", "temp": 68, "condition": "Cloudy"}
    mock_resp = Mock()
    mock_resp.json.return_value = expected
    mock_get.return_value = mock_resp

    result = service.get_weather("Paris")

    assert result == expected
    assert set(result.keys()) == {"city", "temp", "condition"}


# ---------------------------------------------------------------------------
# send_notification
# ---------------------------------------------------------------------------

@patch("service.requests.post")
def test_send_notification_calls_correct_endpoint(mock_post):
    mock_resp = Mock()
    mock_resp.json.return_value = {"status": "ok", "delivered": True}
    mock_post.return_value = mock_resp

    service.send_notification("user1", "hello")

    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://api.notify.example.com/v1/send"


@patch("service.requests.post")
def test_send_notification_passes_user_and_message(mock_post):
    mock_resp = Mock()
    mock_resp.json.return_value = {"status": "ok"}
    mock_post.return_value = mock_resp

    service.send_notification("user1", "hello world")

    assert mock_post.call_args.kwargs["json"] == {
        "user_id": "user1",
        "message": "hello world",
    }


@patch("service.requests.post")
def test_send_notification_returns_status_on_success(mock_post):
    expected = {"status": "ok", "delivered": True}
    mock_resp = Mock()
    mock_resp.json.return_value = expected
    mock_post.return_value = mock_resp

    result = service.send_notification("user1", "hello")

    assert result == expected


@patch("service.requests.post")
def test_send_notification_timeout_returns_error_dict(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout("connection timed out")

    result = service.send_notification("user1", "hello")

    assert result == {"status": "error", "reason": "timeout"}
