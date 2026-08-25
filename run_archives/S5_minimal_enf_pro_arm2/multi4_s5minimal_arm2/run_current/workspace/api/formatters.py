"""
Response formatters for api.

format_response is re-exported from utils.formatters to avoid the
circular dependency with models. The canonical implementation lives in
utils.formatters.
"""
import json

from utils.formatters import format_response  # re-export for backward compatibility


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
