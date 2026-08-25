"""
Response formatters for api.

format_response() is now re-exported from utils.formatters for backward
compatibility. The canonical implementation lives in utils.formatters.
"""
from utils.formatters import format_response  # re-export for backward compatibility


def format_error(message: str, code: int = 500) -> str:
    """Format an error response."""
    import json
    output = {
        "status": "error",
        "message": message,
        "code": code,
    }
    return json.dumps(output, indent=2)
