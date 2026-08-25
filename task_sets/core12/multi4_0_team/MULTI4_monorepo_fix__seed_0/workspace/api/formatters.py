"""
Response formatters for api.

The format_response() function is defined here but SHOULD live in
utils.formatters to avoid the circular dependency with models.
"""
import json


def format_response(data: dict) -> str:
    """Format a response dict as a JSON string with standard fields."""
    output = {
        "status": "ok",
        "data": data,
        "version": "1.0",
    }
    return json.dumps(output, indent=2)


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
