"""Mock-based tests for service.py API calls."""
import requests
import service


# ---------------------------------------------------------------------------
# Test group 1: get_user
# ---------------------------------------------------------------------------

def test_get_user_success(mocker):
    """Mock get_user("123"), assert URL, params, and return shape."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "id": "123", "name": "Alice", "email": "alice@example.com"
    }
    mock_response.raise_for_status.return_value = None
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    result = service.get_user("123")

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/123", timeout=10
    )
    assert result == {"id": "123", "name": "Alice", "email": "alice@example.com"}
    assert result["id"] == "123"
    assert result["name"] == "Alice"
    assert result["email"] == "alice@example.com"


def test_get_user_different_user_id(mocker):
    """Mock get_user("456"), verify URL embeds the right user_id."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"id": "456", "name": "Bob"}
    mock_response.raise_for_status.return_value = None
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    result = service.get_user("456")

    mock_get.assert_called_once_with(
        "https://api.users.example.com/v1/users/456", timeout=10
    )
    assert result == {"id": "456", "name": "Bob"}


def test_get_user_http_error(mocker):
    """Mock a 404 HTTPError – should propagate."""
    mock_response = mocker.Mock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
    mocker.patch("service.requests.get", return_value=mock_response)

    import pytest
    with pytest.raises(requests.exceptions.HTTPError):
        service.get_user("999")


# ---------------------------------------------------------------------------
# Test group 2: get_weather
# ---------------------------------------------------------------------------

def test_get_weather_success(mocker):
    """Mock get_weather("London"), assert URL + params + return shape."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "city": "London", "temp": 72, "condition": "cloudy"
    }
    mock_response.raise_for_status.return_value = None
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    result = service.get_weather("London")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "London"},
        timeout=10,
    )
    assert result == {"city": "London", "temp": 72, "condition": "cloudy"}
    assert result["city"] == "London"
    assert result["temp"] == 72
    assert result["condition"] == "cloudy"


def test_get_weather_different_city(mocker):
    """Mock get_weather("Tokyo"), verify params carry the city."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"city": "Tokyo", "temp": 85}
    mock_response.raise_for_status.return_value = None
    mock_get = mocker.patch("service.requests.get", return_value=mock_response)

    result = service.get_weather("Tokyo")

    mock_get.assert_called_once_with(
        "https://api.weather.example.com/v2/current",
        params={"city": "Tokyo"},
        timeout=10,
    )
    assert result == {"city": "Tokyo", "temp": 85}


def test_get_weather_http_error(mocker):
    """Mock a 500 HTTPError – should propagate."""
    mock_response = mocker.Mock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
    mocker.patch("service.requests.get", return_value=mock_response)

    import pytest
    with pytest.raises(requests.exceptions.HTTPError):
        service.get_weather("Nowhere")


# ---------------------------------------------------------------------------
# Test group 3: send_notification
# ---------------------------------------------------------------------------

def test_send_notification_success(mocker):
    """Mock POST success – assert URL, json payload, timeout, return shape."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"status": "sent", "id": "notif_001"}
    mock_response.raise_for_status.return_value = None
    mock_post = mocker.patch("service.requests.post", return_value=mock_response)

    result = service.send_notification("123", "Hello!")

    mock_post.assert_called_once_with(
        "https://api.notify.example.com/v1/send",
        json={"user_id": "123", "message": "Hello!"},
        timeout=5,
    )
    assert result == {"status": "sent", "id": "notif_001"}
    assert result["status"] == "sent"
    assert result["id"] == "notif_001"


def test_send_notification_timeout_handling(mocker):
    """Mock requests.exceptions.Timeout – must return error dict, NOT crash."""
    mocker.patch(
        "service.requests.post",
        side_effect=requests.exceptions.Timeout,
    )

    result = service.send_notification("123", "Hello!")

    assert result == {"status": "error", "reason": "timeout"}


def test_send_notification_connection_error(mocker):
    """Mock requests.exceptions.ConnectionError – must return error dict."""
    mocker.patch(
        "service.requests.post",
        side_effect=requests.exceptions.ConnectionError,
    )

    result = service.send_notification("456", "Test")

    assert result == {"status": "error", "reason": "timeout"}


def test_send_notification_params(mocker):
    """Mock send_notification – verify json body and timeout=5."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"status": "sent"}
    mock_response.raise_for_status.return_value = None
    mock_post = mocker.patch("service.requests.post", return_value=mock_response)

    result = service.send_notification("789", "System alert")

    mock_post.assert_called_once_with(
        "https://api.notify.example.com/v1/send",
        json={"user_id": "789", "message": "System alert"},
        timeout=5,
    )
    assert result == {"status": "sent"}
