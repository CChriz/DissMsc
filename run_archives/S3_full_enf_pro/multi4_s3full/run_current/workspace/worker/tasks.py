"""
Background tasks for worker.

Bug 3: Imports process_item from core.processing, but that
function was moved to utils.processing in v1.2.

Fix: Change import to `from utils.processing import process_item`
"""
from core.base import BaseProcessor
# Bug 3: process_item was moved to utils.processing
from utils.processing import process_item


class RunBatchTask(BaseProcessor):
    """Background task that processes items."""

    def __init__(self, name: str = "batch"):
        super().__init__(name)
        self.results = []

    def run(self, data: dict) -> dict:
        """Process a batch of items."""
        self.initialize()
        items = data.get("items", [])
        processed = []
        for item in items:
            result = process_item(item)
            processed.append(result)
        self.results.extend(processed)
        return {"processed": len(processed), "results": processed}


def run_batch(items: list[dict]) -> list[dict]:
    """Convenience function to process a batch."""
    task = RunBatchTask()
    result = task.run({"items": items})
    return result["results"]
