"""
Formatting utilities for utils.

This is where format_response() should be imported from to avoid
circular dependencies with api.
"""
import json


def format_response(data: dict) -> str:
    """Format a response dict as a JSON string with standard fields.

    This is the canonical location for this function.
    api.formatters should re-export from here.
    """
    output = {
        "status": "ok",
        "data": data,
        "version": "1.0",
    }
    return json.dumps(output, indent=2)
