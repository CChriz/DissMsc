"""
Task message queue with acknowledgment support.

Thread-safe task queue featuring:
- Atomic capacity enforcement (TOCTOU fix)
- Ack/Nack acknowledgment pattern for reliable message delivery
- In-flight message tracking with unique receipt tokens
"""
import threading
import uuid
from collections import deque
from typing import Any


class QueueFull(Exception):
    """Raised when the queue has reached its capacity."""


class QueueEmpty(Exception):
    """Raised when the queue is empty."""


class InvalidReceipt(Exception):
    """Raised when an invalid or unknown receipt token is used."""


class TaskQueue:
    """Thread-safe task queue with configurable capacity and ack/nack support."""

    def __init__(self, capacity: int = 500):
        self._capacity = capacity
        self._queue: deque = deque()
        self._in_flight: dict = {}  # token -> message
        self._lock = threading.Lock()

    def put(self, message: Any) -> None:
        """
        Enqueue a task message.

        Raises QueueFull if the queue is at capacity.

        The capacity check and append are atomic (same lock) — fixes TOCTOU (Bug 1).
        """
        with self._lock:
            if len(self._queue) >= self._capacity:
                raise QueueFull(
                    f"TaskQueue at capacity ({self._capacity})"
                )
            self._queue.append(message)

    def get(self):
        """
        Dequeue and return the next task message with a receipt.

        Returns (message, Receipt) on success, or (None, None) if the queue
        is empty. The message is moved to in-flight storage; call ack() to
        confirm delivery or nack() to requeue on failure.

        Fixes Bug 2: messages are never lost — they remain in _in_flight
        until explicitly acknowledged.
        """
        with self._lock:
            if not self._queue:
                return (None, None)
            message = self._queue.popleft()
            token = str(uuid.uuid4())
            self._in_flight[token] = message
            receipt = Receipt(message=message, token=token)
            return (message, receipt)

    def ack(self, receipt) -> None:
        """
        Acknowledge successful processing of a message.

        Removes the message from in-flight storage permanently.
        Raises InvalidReceipt if the token is unknown.
        """
        with self._lock:
            if receipt.token in self._in_flight:
                del self._in_flight[receipt.token]
            else:
                raise InvalidReceipt("unknown receipt token")

    def nack(self, receipt) -> None:
        """
        Negative-acknowledge: requeue the message for retry.

        Moves the message from in-flight back to the tail of the queue.
        Raises InvalidReceipt if the token is unknown.
        """
        with self._lock:
            if receipt.token in self._in_flight:
                message = self._in_flight.pop(receipt.token)
                self._queue.append(message)
            else:
                raise InvalidReceipt("unknown receipt token")

    def requeue(self, receipt) -> None:
        """
        Requeue the message to the front of the queue (priority retry).

        Raises InvalidReceipt if the token is unknown.
        """
        with self._lock:
            if receipt.token in self._in_flight:
                message = self._in_flight.pop(receipt.token)
                self._queue.appendleft(message)
            else:
                raise InvalidReceipt("unknown receipt token")

    def size(self) -> int:
        """Return the total count of tasks (waiting + in-flight)."""
        with self._lock:
            return len(self._queue) + len(self._in_flight)

    def is_empty(self) -> bool:
        """Return True if no tasks are waiting or in-flight."""
        with self._lock:
            return len(self._queue) == 0 and len(self._in_flight) == 0

    def is_full(self) -> bool:
        """Return True if the waiting queue is at capacity."""
        with self._lock:
            return len(self._queue) >= self._capacity


# Late import to break circular dependency: consumer.py imports TaskQueue,
# and queue.py needs Receipt from consumer.py.  Placing this import after
# the class definition ensures TaskQueue is fully defined before consumer.py
# tries to import it.
from mqueue.consumer import Receipt  # noqa: E402
