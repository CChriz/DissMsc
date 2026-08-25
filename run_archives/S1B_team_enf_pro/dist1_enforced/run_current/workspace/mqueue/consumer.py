"""Consumer interface for the task queue.

Supports the ack/nack acknowledgment pattern: after get() returns a (message, Receipt)
tuple, call ack() on success or nack() on failure to requeue for retry.
"""
import threading
import time
from typing import Any, Callable

from mqueue.queue import TaskQueue


class Receipt:
    """Message delivery receipt — consumers use this to ack/nack messages."""

    def __init__(self, message: Any, token: str):
        self.message = message   # Original message object
        self.token = token       # Unique delivery token (UUID string)

    def __repr__(self):
        return f"Receipt(token={self.token})"


class TaskConsumer:
    """
    Consumes tasks from a TaskQueue with ack/nack support.

    On handler success the message is acked (permanently removed).
    On handler failure the message is nacked (requeued for retry).
    """

    def __init__(
        self,
        queue: TaskQueue,
        handler: Callable[[Any], None],
        consumer_id: int = 0,
    ):
        self._queue = queue
        self._handler = handler
        self._consumer_id = consumer_id
        self._processed: list = []
        self._lock = threading.Lock()
        self._running = False

    def run_once(self) -> bool:
        """
        Process one task from the queue.

        Returns True if a task was processed, False if the queue was empty.
        Uses ack/nack pattern: acks on success, nacks on failure.
        """
        result = self._queue.get()

        # Handle the tuple (message, receipt) returned by ack/nack-aware queue
        if isinstance(result, tuple):
            msg, receipt = result
            if msg is None:
                return False
            try:
                self._handler(msg)
            except Exception:
                # Handler failed — nack to requeue for retry
                if receipt is not None:
                    self._queue.nack(receipt)
                raise
            else:
                # Handler succeeded — ack to confirm delivery
                if receipt is not None:
                    self._queue.ack(receipt)
            with self._lock:
                self._processed.append(msg)
            return True

        # Legacy mode (pre-ack/nack): fire-and-forget
        msg = result
        if msg is None:
            return False
        self._handler(msg)
        with self._lock:
            self._processed.append(msg)
        return True

    def run_until_empty(self, max_idle_cycles: int = 10) -> None:
        """Drain the queue, stopping after max_idle_cycles consecutive empty polls."""
        idle = 0
        while idle < max_idle_cycles:
            if self.run_once():
                idle = 0
            else:
                idle += 1
                time.sleep(0.001)

    @property
    def processed_count(self) -> int:
        return len(self._processed)

    @property
    def processed_messages(self) -> list:
        with self._lock:
            return list(self._processed)
