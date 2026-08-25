"""
Response formatters for api.

format_response() is re-exported from utils.formatters (canonical location)
to maintain backward compatibility for existing callers.
"""
import json

# Re-export for backward compatibility
from utils.formatters import format_response  # noqa: F401


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
