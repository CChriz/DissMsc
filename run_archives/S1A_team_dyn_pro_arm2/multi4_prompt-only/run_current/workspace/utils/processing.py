"""
Processing utilities for utils.

Contains process_item() which was moved here from core.processing
in v1.2.
"""
from core.base import BaseProcessor


def process_item(item: dict) -> dict:
    """Process a single item and return the result.

    This function was moved from core.processing in v1.2.
    """
    result = dict(item)
    result["processed"] = True
    result["processor"] = "utils.processing.process_item"
    return result


def batch_process(items: list[dict]) -> list[dict]:
    """Process multiple items."""
    return [process_item(item) for item in items]
