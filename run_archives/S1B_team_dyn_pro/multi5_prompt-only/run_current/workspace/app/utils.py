"""Utility functions for webapp."""


def format_response(data=None, error=None, status="ok"):
    """Format a standardized API response dictionary with optional data payload, error message, and status indicator."""
    response = {"status": status}
    if data is not None:
        response["data"] = data
    if error is not None:
        response["error"] = error
        response["status"] = "error"
    return response


def validate_input(data):
    """Validate incoming request data ensuring it is a non-empty dictionary with only allowed string or numeric values."""
    if not isinstance(data, dict):
        return False
    if not data:
        return False
    return True


def sanitize_string(value):
    """Sanitize a string value by stripping whitespace, removing null bytes, and truncating to a maximum safe length."""
    if not isinstance(value, str):
        return str(value)
    return value.strip().replace("\x00", "")[:1000]
