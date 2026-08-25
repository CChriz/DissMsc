"""Mock-based tests for service.py — covers all 3 external API calls."""
import pytest
import requests
from unittest.mock import patch, Mock

import service


# ===== get_user tests =====

@patch('service.requests.get')
def test_get_user_calls_correct_url(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {"id": "42", "name": "Alice"}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    service.get_user("42")

    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == "https://api.users.example.com/v1/users/42"
    assert mock_get.call_args[1]['timeout'] == 10


@patch('service.requests.get')
def test_get_user_returns_expected_shape(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "42", "name": "Alice", "email": "alice@example.com"
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = service.get_user("42")

    assert isinstance(result, dict)
    assert result["id"] == "42"
    assert result["name"] == "Alice"
    assert "email" in result


@patch('service.requests.get')
def test_get_user_raises_on_http_error(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    mock_get.return_value = mock_response

    with pytest.raises(requests.HTTPError):
        service.get_user("999")


# ===== get_weather tests =====

@patch('service.requests.get')
def test_get_weather_calls_correct_url_with_params(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {"city": "London", "temp": 65}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    service.get_weather("London")

    mock_get.assert_called_once()
    assert mock_get.call_args[0][0] == "https://api.weather.example.com/v2/current"
    assert mock_get.call_args[1]['params'] == {"city": "London"}
    assert mock_get.call_args[1]['timeout'] == 10


@patch('service.requests.get')
def test_get_weather_returns_expected_shape(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {
        "city": "London", "temp": 65, "condition": "cloudy", "humidity": 80
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = service.get_weather("London")

    assert isinstance(result, dict)
    assert result["city"] == "London"
    assert isinstance(result["temp"], (int, float))
    assert isinstance(result["condition"], str)


@patch('service.requests.get')
def test_get_weather_raises_on_http_error(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mock_get.return_value = mock_response

    with pytest.raises(requests.HTTPError):
        service.get_weather("InvalidCity")


# ===== send_notification tests =====

@patch('service.requests.post')
def test_send_notification_calls_correct_url_and_body(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = {"status": "sent"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    service.send_notification("42", "Hello!")

    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == "https://api.notify.example.com/v1/send"
    assert mock_post.call_args[1]['json'] == {
        "user_id": "42", "message": "Hello!"
    }
    assert mock_post.call_args[1]['timeout'] == 5


@patch('service.requests.post')
def test_send_notification_returns_expected_shape(mock_post):
    mock_response = Mock()
    mock_response.json.return_value = {
        "status": "sent", "message_id": "msg_abc123"
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    result = service.send_notification("42", "Hello!")

    assert isinstance(result, dict)
    assert result["status"] == "sent"
    assert "message_id" in result


# ===== process_user_weather tests =====

@patch('service.get_user')
@patch('service.get_weather')
@patch('service.send_notification')
def test_process_user_weather_chains_all_three_apis(
    mock_notify, mock_weather, mock_user
):
    mock_user.return_value = {"id": "1", "name": "Bob", "email": "bob@test.com"}
    mock_weather.return_value = {"city": "Tokyo", "temp": 75, "condition": "clear"}
    mock_notify.return_value = {"status": "sent"}

    service.process_user_weather("1", "Tokyo")

    mock_user.assert_called_once_with("1")
    mock_weather.assert_called_once_with("Tokyo")
    mock_notify.assert_called_once()


@patch('service.get_user')
@patch('service.get_weather')
@patch('service.send_notification')
def test_process_user_weather_message_format_and_return(
    mock_notify, mock_weather, mock_user
):
    mock_user.return_value = {"id": "1", "name": "Bob", "email": "bob@test.com"}
    mock_weather.return_value = {"city": "Tokyo", "temp": 75, "condition": "clear"}
    mock_notify.return_value = {"status": "sent"}

    result = service.process_user_weather("1", "Tokyo")

    # 验证通知消息格式
    assert mock_notify.call_args[0][0] == "1"
    assert mock_notify.call_args[0][1] == "Hi Bob, weather in Tokyo: 75F"

    # 验证返回值结构
    assert result["user"] == {"id": "1", "name": "Bob", "email": "bob@test.com"}
    assert result["weather"] == {"city": "Tokyo", "temp": 75, "condition": "clear"}
    assert result["notification"] == {"status": "sent"}
    assert set(result.keys()) == {"user", "weather", "notification"}

    # 验证回退默认值：name 缺失 → "User"
    mock_user.return_value = {"id": "2"}
    mock_notify.reset_mock()
    result2 = service.process_user_weather("2", "Tokyo")
    assert mock_notify.call_args[0][1] == "Hi User, weather in Tokyo: 75F"

    # 验证回退默认值：temp 缺失 → "?"
    mock_user.return_value = {"id": "3", "name": "Charlie"}
    mock_weather.return_value = {"city": "Tokyo", "condition": "rain"}
    mock_notify.reset_mock()
    result3 = service.process_user_weather("3", "Tokyo")
    assert mock_notify.call_args[0][1] == "Hi Charlie, weather in Tokyo: ?F"


# ===== send_notification error handling test =====

@patch('service.requests.post')
def test_send_notification_handles_timeout(mock_post):
    """Verify send_notification catches Timeout and returns error dict."""
    mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

    result = service.send_notification("42", "Hello!")

    # 不应抛出异常
    assert result == {"status": "error", "reason": "timeout"}
    mock_post.assert_called_once()
