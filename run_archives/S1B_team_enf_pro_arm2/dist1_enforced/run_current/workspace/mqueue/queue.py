"""
Task message queue with acknowledgment support.

Fixed race conditions:
- Bug 1 (TOCTOU capacity check): the capacity check and the enqueue are now
  performed atomically inside the same lock-held critical section, so
  concurrent producers can never push the pending queue past its capacity.
- Bug 2 (missing acknowledgment pattern): get() returns (message, receipt) and
  moves the message into an in-flight set instead of deleting it. The consumer
  must call ack() to confirm (permanent removal) or nack() to re-queue the
  message for redelivery.

Synchronization contract:
- A single threading.Lock (self._lock) guards all shared state:
  self._queue (pending FIFO deque of PriorityTask), self._inflight
  (receipt -> PriorityTask awaiting ack/nack) and self._seq (monotonic
  counter). Every access to shared state happens under `with self._lock:`.
- put() is non-blocking: raises QueueFull when the pending queue is at
  capacity (matches tests).
- get() is non-blocking: returns (None, None) when empty (matches tests).
- Capacity only constrains the pending _queue. get moves pending -> in-flight;
  ack deletes in-flight; nack moves in-flight back to pending.
"""
import itertools
import threading
import uuid
from collections import deque
from typing import Any, Optional, Tuple

from mqueue.priority import PriorityTask


class QueueFull(Exception):
    """Raised when the queue has reached its capacity."""


class QueueEmpty(Exception):
    """Raised when the queue is empty."""


class TaskQueue:
    """Thread-safe task queue with configurable capacity and ack/nack support."""

    def __init__(self, capacity: int = 500):
        self._capacity = capacity
        self._queue: deque = deque()  # pending FIFO queue of PriorityTask
        self._inflight: dict = {}  # receipt(uuid) -> PriorityTask awaiting ack
        self._seq = itertools.count()  # monotonic insertion seq for PriorityTask
        self._lock = threading.Lock()

    def put(self, message: Any, priority: int = 0) -> None:
        """
        Enqueue a task message atomically.

        Raises QueueFull if the pending queue is at capacity.
        """
        with self._lock:
            if len(self._queue) >= self._capacity:
                raise QueueFull(
                    f"TaskQueue at capacity ({self._capacity})"
                )
            item = PriorityTask(
                urgency=priority,
                seq=next(self._seq),
                message=message,
            )
            self._queue.append(item)

    def get(self) -> Tuple[Optional[Any], Optional[Any]]:
        """
        Dequeue and return the next task message as (message, receipt).

        Returns (None, None) if empty. The message is moved into in-flight and
        is NOT permanently removed until ack() is called.
        """
        with self._lock:
            if not self._queue:
                return (None, None)
            item = self._queue.popleft()
            receipt = uuid.uuid4()
            self._inflight[receipt] = item
            return (item.message, receipt)

    def ack(self, receipt) -> bool:
        """
        Confirm successful processing; permanently remove the message.

        Returns True if the receipt was valid; False if unknown or already
        acked/nacked (idempotent, never raises).
        """
        with self._lock:
            if receipt not in self._inflight:
                return False
            del self._inflight[receipt]
            return True

    def nack(self, receipt) -> bool:
        """
        Re-queue an in-flight message (simulating a consumer crash).

        The message is re-queued at the tail of the pending FIFO with a fresh
        seq, preserving FIFO fairness. Returns True if the receipt was valid;
        False otherwise (idempotent, never raises).
        """
        with self._lock:
            item = self._inflight.pop(receipt, None)
            if item is None:
                return False
            requeued = PriorityTask(
                urgency=item.urgency,
                seq=next(self._seq),
                message=item.message,
            )
            self._queue.append(requeued)
            return True

    def size(self) -> int:
        """Return the current number of pending tasks in the queue."""
        with self._lock:
            return len(self._queue)

    def is_empty(self) -> bool:
        """Return True if there are no pending and no in-flight tasks."""
        with self._lock:
            return not self._queue and not self._inflight

    def is_full(self) -> bool:
        """Return True if the pending queue is at capacity."""
        with self._lock:
            return len(self._queue) >= self._capacity
