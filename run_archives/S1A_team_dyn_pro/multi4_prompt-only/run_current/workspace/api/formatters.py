"""
Response formatters for api.

format_response() is re-exported from utils.formatters
to avoid circular dependency with models.
"""
import json
from utils.formatters import format_response


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
