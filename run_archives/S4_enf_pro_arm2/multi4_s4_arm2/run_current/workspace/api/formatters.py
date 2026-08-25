"""
Response formatters for api.

format_response is now re-exported from utils.formatters (the canonical
location) to maintain backward compatibility for any existing importers.
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
