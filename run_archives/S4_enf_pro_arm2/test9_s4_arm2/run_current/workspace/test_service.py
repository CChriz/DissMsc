"""Mock-based tests for service.py — 10 test functions covering all 3 API calls."""

import pytest
import requests
from unittest.mock import MagicMock, Mock

from service import get_user, get_weather, send_notification, process_user_weather


# ================================================================
# Fixtures
# ================================================================

@pytest.fixture
def mock_user_data():
    """get_user 成功返回的示例数据."""
    return {"id": "123", "name": "Alice", "email": "alice@example.com"}


@pytest.fixture
def mock_weather_data():
    """get_weather 成功返回的示例数据."""
    return {"city": "Beijing", "temp": 72, "condition": "Sunny"}


@pytest.fixture
def mock_notification_success():
    """send_notification 成功返回的示例数据."""
    return {"status": "success", "message_id": "msg_456"}


# ================================================================
# Helper
# ================================================================

def _make_mock_response(json_data, status_code=200):
    """创建 mock requests.Response，包含 json() 和 raise_for_status().

    Args:
        json_data: response.json() 返回的数据
        status_code: HTTP 状态码，默认 200

    Returns:
        Mock 对象，模拟 requests.Response
    """
    mock_resp = Mock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ================================================================
# 1-2: get_user tests
# ================================================================

def test_get_user_success(mocker, mock_user_data):
    """Mock get_user 成功返回用户数据，验证 URL/参数/返回值."""
    # Arrange
    mock_response = _make_mock_response(mock_user_data)
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    # Act
    result = get_user("123")

    # Assert — URL
    mock_get.assert_called_once()
    assert "api.users.example.com/v1/users/123" in mock_get.call_args[0][0]

    # Assert — timeout 参数
    assert mock_get.call_args[1]["timeout"] == 10

    # Assert — 返回值结构与内容
    assert result == {"id": "123", "name": "Alice", "email": "alice@example.com"}
    assert "id" in result and "name" in result and "email" in result


def test_get_user_http_error(mocker):
    """Mock get_user 返回 404 HTTP 错误，验证异常传播."""
    # Arrange
    mock_response = _make_mock_response({"error": "not found"}, status_code=404)
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "404 Client Error"
    )
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    # Act & Assert — raise_for_status() 抛出 HTTPError
    with pytest.raises(requests.exceptions.HTTPError):
        get_user("999")

    # 验证仍调用了正确的 URL
    mock_get.assert_called_once()
    assert "api.users.example.com/v1/users/999" in mock_get.call_args[0][0]


# ================================================================
# 3-4: get_weather tests
# ================================================================

def test_get_weather_success(mocker, mock_weather_data):
    """Mock get_weather 成功返回天气数据，验证 params 参数传递."""
    # Arrange
    mock_response = _make_mock_response(mock_weather_data)
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    # Act
    result = get_weather("Beijing")

    # Assert — URL
    mock_get.assert_called_once()
    assert "api.weather.example.com/v2/current" in mock_get.call_args[0][0]

    # Assert — params 参数（关键：使用 params= 而非 query string）
    assert mock_get.call_args[1]["params"] == {"city": "Beijing"}
    assert mock_get.call_args[1]["timeout"] == 10

    # Assert — 返回值结构（注意：temp 不是 temperature）
    assert result == {"city": "Beijing", "temp": 72, "condition": "Sunny"}
    assert "city" in result and "temp" in result and "condition" in result


def test_get_weather_city_not_found(mocker):
    """Mock get_weather 返回 404 — 城市未找到，验证异常传播."""
    # Arrange
    mock_response = _make_mock_response({"error": "city not found"}, status_code=404)
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "404 Client Error"
    )
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    # Act & Assert
    with pytest.raises(requests.exceptions.HTTPError):
        get_weather("Atlantis")

    # 验证 URL 和 params
    mock_get.assert_called_once()
    assert "api.weather.example.com/v2/current" in mock_get.call_args[0][0]
    assert mock_get.call_args[1]["params"] == {"city": "Atlantis"}


# ================================================================
# 5-7: send_notification tests (by executor2, enhanced)
# ================================================================

def test_send_notification_success(mocker):
    """Mock send_notification 成功：验证 endpoint / json body / timeout / 返回值."""
    # Arrange
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"status": "success", "message_id": "msg_456"}
    mock_post = mocker.patch("service.requests.post", return_value=mock_response)

    # Act
    result = send_notification("user123", "Hello World")

    # Assert — endpoint
    mock_post.assert_called_once()
    assert "api.notify.example.com/v1/send" in mock_post.call_args[0][0]

    # Assert — json body 参数
    assert mock_post.call_args[1]["json"] == {
        "user_id": "user123",
        "message": "Hello World",
    }

    # Assert — timeout 参数
    assert mock_post.call_args[1]["timeout"] == 5

    # Assert — 返回值
    assert result == {"status": "success", "message_id": "msg_456"}


def test_send_notification_timeout(mocker):
    """Mock Timeout 异常：函数不抛异常，返回 {"status": "error", "reason": "timeout"}."""
    # Arrange
    mocker.patch("service.requests.post", side_effect=requests.exceptions.Timeout)

    # Act — 关键：不抛异常
    result = send_notification("user123", "test message")

    # Assert — 错误响应 shape 一致
    assert result == {"status": "error", "reason": "timeout"}


def test_send_notification_connection_error(mocker):
    """Mock ConnectionError：函数不抛异常，返回 {"status": "error", "reason": "timeout"}."""
    # Arrange
    mocker.patch(
        "service.requests.post", side_effect=requests.exceptions.ConnectionError
    )

    # Act — 关键：不抛异常
    result = send_notification("user123", "test message")

    # Assert — 与 Timeout 相同的错误响应 shape
    assert result == {"status": "error", "reason": "timeout"}


# ================================================================
# 8-10: process_user_weather tests（组合函数）
# ================================================================

def test_process_user_weather_success(mocker, mock_user_data, mock_weather_data):
    """Mock process_user_weather 端到端成功：验证三次 API 调用及嵌套返回值."""
    # Arrange
    user_response = _make_mock_response(mock_user_data)
    weather_response = _make_mock_response(mock_weather_data)
    notify_response = _make_mock_response(
        {"status": "success", "message_id": "msg_789"}
    )

    # side_effect 区分两次 requests.get 调用
    mock_get = mocker.patch(
        "service.requests.get", side_effect=[user_response, weather_response]
    )
    mock_post = mocker.patch("service.requests.post", return_value=notify_response)

    # Act
    result = process_user_weather("123", "Beijing")

    # Assert — 调用次数
    assert mock_get.call_count == 2
    assert mock_post.call_count == 1

    # Assert — 第一次 get（get_user）
    assert "api.users.example.com/v1/users/123" in mock_get.call_args_list[0][0][0]
    assert mock_get.call_args_list[0][1]["timeout"] == 10

    # Assert — 第二次 get（get_weather）
    assert "api.weather.example.com/v2/current" in mock_get.call_args_list[1][0][0]
    assert mock_get.call_args_list[1][1]["params"] == {"city": "Beijing"}

    # Assert — post（send_notification）
    assert "api.notify.example.com/v1/send" in mock_post.call_args[0][0]
    assert mock_post.call_args[1]["json"]["user_id"] == "123"
    expected_msg = "Hi Alice, weather in Beijing: 72F"
    assert mock_post.call_args[1]["json"]["message"] == expected_msg

    # Assert — 嵌套返回值结构
    assert result["user"] == mock_user_data
    assert result["weather"] == mock_weather_data
    assert result["notification"] == {"status": "success", "message_id": "msg_789"}
    assert set(result.keys()) == {"user", "weather", "notification"}


def test_process_user_weather_notification_timeout(
    mocker, mock_user_data, mock_weather_data
):
    """Mock send_notification 超时：get 调用正常完成，不崩溃."""
    # Arrange
    user_response = _make_mock_response(mock_user_data)
    weather_response = _make_mock_response(mock_weather_data)

    mock_get = mocker.patch(
        "service.requests.get", side_effect=[user_response, weather_response]
    )
    mock_post = mocker.patch(
        "service.requests.post", side_effect=requests.exceptions.Timeout
    )

    # Act — 关键：不抛异常
    result = process_user_weather("123", "Beijing")

    # Assert — get 仍然正常调用 2 次
    assert mock_get.call_count == 2
    assert mock_post.call_count == 1

    # Assert — user 和 weather 正常返回
    assert result["user"] == mock_user_data
    assert result["weather"] == mock_weather_data

    # Assert — notification 返回错误 dict（被 send_notification 内部捕获）
    assert result["notification"] == {"status": "error", "reason": "timeout"}


def test_process_user_weather_user_api_failure(mocker):
    """Mock get_user 返回 500 错误：异常向上传播，后续调用不执行."""
    # Arrange
    mock_response = _make_mock_response(
        {"error": "internal server error"}, status_code=500
    )
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "500 Server Error"
    )
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    # Act & Assert — get_user 失败导致 HTTPError 传播
    with pytest.raises(requests.exceptions.HTTPError):
        process_user_weather("123", "Beijing")

    # 验证只调用了 1 次 get（未到达 get_weather 和 send_notification）
    assert mock_get.call_count == 1
    assert "api.users.example.com/v1/users/123" in mock_get.call_args[0][0]
