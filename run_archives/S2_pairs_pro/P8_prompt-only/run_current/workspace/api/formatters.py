"""
Response formatters for api.

format_response() is re-exported from utils.formatters to avoid
circular dependencies with models.
"""
import json

# Re-export format_response from its canonical location in utils
from utils.formatters import format_response  # noqa: F401


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
