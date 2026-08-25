"""Consumer interface for the task queue.

Two public classes are provided:

* ``Consumer`` — the canonical ack/nack consumer.  It owns no queue state; it
  delegates ``get``/``ack``/``nack`` straight through to the queue and simply
  forwards the opaque receipt token.

* ``TaskConsumer`` — retained for backward compatibility.  It wraps a handler
  and processes tasks with the ack/nack pattern: ack on success, nack on
  handler failure (simulating crash recovery).
"""
import threading
import time
from typing import Any, Callable

# NOTE: no import of the concrete queue class here — the consumer is a thin
# delegating wrapper and works with any object exposing get/ack/nack.


class Consumer:
    """A thin ack/nack-aware consumer over a ``MessageQueue``/``TaskQueue``.

    The consumer holds no counters and does not generate receipts; all queue
    state and receipt management live in the queue.  ``receive()`` returns the
    exact ``(message, receipt)`` tuple from ``queue.get()``, and the receipt is
    meant to be passed back verbatim to ``ack()`` / ``nack()``.
    """

    def __init__(self, queue):
        self._queue = queue

    def receive(self):
        """Return ``(message, receipt)`` from the underlying queue."""
        return self._queue.get()

    def ack(self, receipt) -> bool:
        """Acknowledge ``receipt``, removing its message from the queue."""
        return self._queue.ack(receipt)

    def nack(self, receipt) -> bool:
        """Negative-acknowledge ``receipt``, requeueing its message."""
        return self._queue.nack(receipt)


class TaskConsumer:
    """Consumes tasks from a ``TaskQueue`` using the ack/nack pattern.

    ``run_once`` acks a successfully processed task and nacks (requeues) a task
    whose handler raised, so a crashing consumer no longer loses the message.
    """

    def __init__(
        self,
        queue,
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
        """
        result = self._queue.get()
        if isinstance(result, tuple):
            message, receipt = result
        else:
            message, receipt = result, None

        if message is None:
            return False

        try:
            self._handler(message)
        except Exception:
            # Simulate crash recovery: put the unprocessed message back.
            if receipt is not None and hasattr(self._queue, "nack"):
                self._queue.nack(receipt)
            raise

        if receipt is not None and hasattr(self._queue, "ack"):
            self._queue.ack(receipt)

        with self._lock:
            self._processed.append(message)
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
