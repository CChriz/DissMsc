"""
Task message queue with acknowledgment support.

WARNING: This implementation contains known race conditions for testing purposes.
"""
import threading
import uuid
from collections import deque
from typing import Any, Optional, Tuple


class QueueFull(Exception):
    """Raised when the queue has reached its capacity."""


class QueueEmpty(Exception):
    """Raised when the queue is empty."""


class TaskQueue:
    """Thread-safe task queue with configurable capacity."""

    def __init__(self, capacity: int = 500):
        self._capacity = capacity
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._in_flight: dict = {}

    def put(self, message: Any) -> None:
        """
        Enqueue a task message.

        Raises QueueFull if the queue is at capacity.
        """
        with self._lock:
            if len(self._queue) >= self._capacity:
                raise QueueFull(
                    f"TaskQueue at capacity ({self._capacity})"
                )
            self._queue.append(message)

    def get(self) -> tuple:
        """
        Dequeue and return (message, receipt), or (None, None) if empty.

        The message is held in-flight until ack() or nack() is called.
        """
        with self._lock:
            if not self._queue:
                return (None, None)
            message = self._queue.popleft()
            receipt = str(uuid.uuid4())
            self._in_flight[receipt] = message
            return (message, receipt)

    def ack(self, receipt: str) -> None:
        """
        Acknowledge successful processing. Removes the message from in-flight.
        """
        with self._lock:
            if receipt in self._in_flight:
                del self._in_flight[receipt]

    def nack(self, receipt: str) -> None:
        """
        Negative-acknowledge (simulate crash). Re-queues the message for
        re-delivery at the front of the queue to preserve ordering.
        """
        with self._lock:
            if receipt in self._in_flight:
                message = self._in_flight.pop(receipt)
                self._queue.appendleft(message)

    def size(self) -> int:
        """Return the current number of tasks in the queue (waiting + in-flight)."""
        with self._lock:
            return len(self._queue) + len(self._in_flight)

    def is_empty(self) -> bool:
        """Return True if the queue has no tasks waiting or in-flight."""
        with self._lock:
            return len(self._queue) == 0 and len(self._in_flight) == 0

    def is_full(self) -> bool:
        """Return True if the queue is at capacity (waiting + in-flight)."""
        with self._lock:
            return len(self._queue) + len(self._in_flight) >= self._capacity
