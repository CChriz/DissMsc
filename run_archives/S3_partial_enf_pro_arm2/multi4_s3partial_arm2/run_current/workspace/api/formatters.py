"""
Response formatters for api.

The format_response() function is defined here but SHOULD live in
utils.formatters to avoid the circular dependency with models.
"""
import json


# format_response re-exported from canonical location in utils.formatters
from utils.formatters import format_response  # noqa: F401


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
