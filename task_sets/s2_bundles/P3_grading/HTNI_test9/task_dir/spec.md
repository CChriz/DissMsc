# TEST9: Mock-Based API Testing

## Goal
A Python application (`service.py`) calls 3 external APIs. Write comprehensive
mock-based tests that cover all 3 API interactions without making real network calls.

## Hard Requirements

1. **Mock all 3 API calls** in `service.py`:
   - `get_user(user_id)` — calls a user API, returns user dict
   - `get_weather(city)` — calls a weather API, returns weather dict
   - `send_notification(user_id, message)` — calls a notification API, returns status
2. **Test file**: `test_service.py` using `unittest.mock` or `pytest-mock`.
3. **Response mocking**: Mock successful responses for `get_user` and `get_weather`.
4. **Error simulation**: Mock a network timeout for `send_notification` and verify the app handles it gracefully (returns error dict, does not crash).
5. **Assertions**: Each test must assert on:
   - The correct URL/endpoint was called
   - The correct parameters were passed
   - The return value matches expected shape
6. **Fix the error handling** in `service.py`: the `send_notification` function is missing a try/except for timeout errors.
7. **Run**: `python -m pytest test_service.py -v` must pass with 0 failures.
8. **Minimum 8 test functions** total.

## Deliverables
- `test_service.py` with all mock-based tests
- Fixed `service.py` with proper error handling
- Verifier confirms all tests pass.
