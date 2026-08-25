"""
Response formatters for api.

format_response() has been moved to utils.formatters as the canonical
location to break the circular dependency with models.
It is re-exported here for backward compatibility.
"""
import json

from utils.formatters import format_response  # moved to utils, re-exported for backward compatibility


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
