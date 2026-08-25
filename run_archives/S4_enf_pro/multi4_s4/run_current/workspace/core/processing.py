"""
Processing utilities for core.

NOTE: process_item() was moved to utils.processing in v1.2.
This module retains other processing helpers.
"""


def validate_input(data: dict) -> bool:
    """Validate that input data has required fields."""
    required = ["id", "type", "payload"]
    return all(k in data for k in required)


def normalize_output(result: dict) -> dict:
    """Normalize output fields."""
    return {k.lower(): v for k, v in result.items()}


# process_item was here but moved to utils.processing in v1.2
# Keeping this comment for historical reference.
