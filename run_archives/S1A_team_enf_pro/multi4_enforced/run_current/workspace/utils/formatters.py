"""
Formatting utilities for utils.

This is the canonical location for format_response() to avoid
circular dependencies between models and api.
"""


def format_response(data, status=200):
    """Format a standard API response dictionary."""
    return {"status": status, "data": data}
