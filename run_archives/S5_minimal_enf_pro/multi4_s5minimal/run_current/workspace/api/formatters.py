"""
Response formatters for api.

Re-exports from utils.formatters for backward compatibility.
The canonical location for format_response() is utils.formatters.
"""
import json

# Re-export from utils.formatters (canonical location)
from utils.formatters import format_response


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
