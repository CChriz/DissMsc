"""
Response formatters for api.

format_response() lives in utils.formatters (canonical location) and is
re-exported here for backward compatibility with external consumers.
format_error() remains api-specific.
"""
import json

from utils.formatters import format_response

__all__ = ["format_response", "format_error"]


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
