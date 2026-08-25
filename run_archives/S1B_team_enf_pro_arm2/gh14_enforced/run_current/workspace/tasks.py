"""
Individual stage tasks for the ETL pipeline.

Each task processes one item and either returns a result dict or raises
ValueError if the item is the designated error trigger ('POISON_PILL').
"""


class StageError(Exception):
    """Raised when a stage task fails to process an item."""
    pass


def extract_item(item: str) -> dict:
    """Extract records from source.

    Raises StageError if item == 'POISON_PILL'.
    """
    if item == "POISON_PILL":
        raise StageError(f"Stage 'extract' failed: invalid item {item!r}")
    return {"stage": "extract", "item": item, "status": "ok"}


def transform_item(result: dict) -> dict:
    """Transform each record.

    Raises StageError if upstream result indicates failure.
    """
    if result.get("status") == "error":
        raise StageError(f"Stage 'transform' received failed upstream result: {result}")
    return {"stage": "transform", "item": result["item"], "status": "ok"}


def load_item(result: dict) -> dict:
    """Load records into destination.

    Raises StageError if upstream result indicates failure.
    """
    if result.get("status") == "error":
        raise StageError(f"Stage 'load' received failed upstream result: {result}")
    return {"stage": "load", "item": result["item"], "status": "ok"}
