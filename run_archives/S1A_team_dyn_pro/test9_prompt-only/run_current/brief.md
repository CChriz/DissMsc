# Implementation Plan: Mock-Based Tests for service.py

## 1. Fix service.py: send_notification Error Handling

The current `send_notification()` has no try/except. Add error handling:

```python
def send_notification(user_id: str, message: str) -> dict:
    """Send a notification to a user.

    Catches Timeout and ConnectionError, returning an error dict
    instead of crashing.
    """
    try:
        response = requests.post(
            BASE_NOTIFY_URL,
            json={"user_id": user_id, "message": message},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        return {"status": "error", "reason": "timeout"}
```

The key changes:
- Wrap the entire `requests.post(...)` block in `try`
- Catch both `requests.exceptions.Timeout` and `requests.exceptions.ConnectionError`
- Return `{"status": "error", "reason": "timeout"}` on either exception
- `response.raise_for_status()` stays inside the try block

## 2. Mock Strategy for Each API

All tests use `unittest.mock.patch` on `requests.get` and `requests.post` within the `service` module. The target paths are:

- `service.requests.get` — for `get_user()` and `get_weather()`
- `service.requests.post` — for `send_notification()`

### get_user(user_id)
- Mock `requests.get` to return a `Mock` with `.raise_for_status()` no-op and `.json()` returning `{"id": user_id, "name": "Alice", "email": "alice@example.com"}`
- Assert: called with URL `"https://api.users.example.com/v1/users/{user_id}"` and `timeout=10`

### get_weather(city)
- Mock `requests.get` to return a `Mock` with `.raise_for_status()` no-op and `.json()` returning `{"city": city, "temp": 72, "condition": "sunny"}`
- Assert: called with URL `"https://api.weather.example.com/v2/current"`, `params={"city": city}`, `timeout=10`

### send_notification(user_id, message)
- **Success case**: Mock `requests.post` → `.raise_for_status()` no-op, `.json()` → `{"status": "ok", "message_id": "msg_123"}`
- **Error cases**: Mock `requests.post` to `side_effect=requests.exceptions.Timeout()` or `requests.exceptions.ConnectionError()`

## 3. Test Cases (10 total)

### Test 1: `test_get_user_calls_correct_endpoint`
- **Mock**: `requests.get` → mock response with `{"id": "42", "name": "Alice"}`
- **Call**: `service.get_user("42")`
- **Assert**: `requests.get` called once with `"https://api.users.example.com/v1/users/42"` and `timeout=10`

### Test 2: `test_get_user_returns_expected_shape`
- **Mock**: `requests.get` → `{"id": "99", "name": "Bob", "email": "bob@test.com"}`
- **Call**: `result = service.get_user("99")`
- **Assert**: `result == {"id": "99", "name": "Bob", "email": "bob@test.com"}`
- **Assert**: `"id" in result`, `"name" in result`, `"email" in result`

### Test 3: `test_get_weather_calls_correct_endpoint`
- **Mock**: `requests.get` → `{"city": "London", "temp": 55}`
- **Call**: `service.get_weather("London")`
- **Assert**: `requests.get` called once
- **Assert**: First positional arg is `"https://api.weather.example.com/v2/current"`
- **Assert**: `params={"city": "London"}` in kwargs, `timeout=10` in kwargs

### Test 4: `test_get_weather_returns_expected_shape`
- **Mock**: `requests.get` → `{"city": "Tokyo", "temp": 80, "condition": "cloudy"}`
- **Call**: `result = service.get_weather("Tokyo")`
- **Assert**: `result["city"] == "Tokyo"`, `result["temp"] == 80`, `result["condition"] == "cloudy"`

### Test 5: `test_send_notification_success_calls_correct_endpoint`
- **Mock**: `requests.post` → `{"status": "ok", "message_id": "abc"}`
- **Call**: `service.send_notification("user1", "Hello!")`
- **Assert**: `requests.post` called once with `"https://api.notify.example.com/v1/send"`
- **Assert**: `json={"user_id": "user1", "message": "Hello!"}` in kwargs
- **Assert**: `timeout=5` in kwargs

### Test 6: `test_send_notification_success_returns_response`
- **Mock**: `requests.post` → `{"status": "ok", "message_id": "xyz789"}`
- **Call**: `result = service.send_notification("u2", "Test msg")`
- **Assert**: `result == {"status": "ok", "message_id": "xyz789"}`

### Test 7: `test_send_notification_handles_timeout`
- **Mock**: `requests.post` → `side_effect=requests.exceptions.Timeout()`
- **Call**: `result = service.send_notification("u3", "msg")`
- **Assert**: `result == {"status": "error", "reason": "timeout"}`
- **Assert**: Function does NOT raise (no crash)

### Test 8: `test_send_notification_handles_connection_error`
- **Mock**: `requests.post` → `side_effect=requests.exceptions.ConnectionError()`
- **Call**: `result = service.send_notification("u4", "msg")`
- **Assert**: `result == {"status": "error", "reason": "timeout"}`
- **Assert**: Function does NOT raise (no crash)

### Test 9: `test_get_user_different_ids`
- **Mock**: `requests.get` → dynamic: if user_id "1" → Alice, if user_id "2" → Bob
- **Call**: `service.get_user("1")` then `service.get_user("2")`
- **Assert**: URL called with "1" first, "2" second; returns differ accordingly
- This verifies the mock is called with the correct user_id each time

### Test 10: `test_process_user_weather_integration`
- **Mock**: All 3 calls at module level with `patch.multiple` or sequential patches
  - `requests.get` → side_effect that returns user on 1st call, weather on 2nd call
  - `requests.post` → `{"status": "ok", "message_id": "n_1"}`
- **Call**: `result = service.process_user_weather("42", "Paris")`
- **Assert**: `result["user"]["name"]` present, `result["weather"]["temp"]` present
- **Assert**: `result["notification"]["status"] == "ok"`
- **Assert**: `result["notification"]["message_id"]` present

## 4. Implementation Notes

- File: `/srv/jwteam_clone/shared/run_current/workspace/test_service.py`
- Use `import service` and `from unittest.mock import patch, Mock`
- Use `import pytest` (optional but nice to have)
- Every test uses `@patch("service.requests.get")` or `@patch("service.requests.post")` decorator
- For the integration test, either use `@patch("service.requests.post")` + `@patch("service.requests.get")` stacked decorators, or use `with patch(...)` context managers
- Mock `.raise_for_status()` to be a `Mock(return_value=None)` or just `lambda: None`
- Mock `.json()` on the mock response to return the expected dict

## 5. Verification

Run: `cd /srv/jwteam_clone/shared/run_current/workspace && python -m pytest test_service.py -v`

Expected: all 10 tests pass, 0 failures.
