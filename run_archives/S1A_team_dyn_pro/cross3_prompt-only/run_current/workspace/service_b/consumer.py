"""
Event Queue Consumer — message consumer stub.

In production this would read from a queue (Kafka, Pub/Sub, etc.).
For the benchmark this is a simple in-memory collector.
"""
from __future__ import annotations
from service_b.schema import EventMessage, StatusMessage
from typing import List


class MessageConsumer:
    """Receives and validates EventMessage objects."""

    def __init__(self):
        self._received: List[EventMessage] = []
        self._errors: List[StatusMessage] = []

    def consume(self, msg: EventMessage) -> None:
        """Accept a message after validation."""
        msg.validate_oneof()
        if not isinstance(msg.payload, bytes):
            raise TypeError(f"payload must be bytes, got {type(msg.payload)}")
        if not isinstance(msg.status, int):
            raise TypeError(f"status must be int, got {type(msg.status)}")
        self._received.append(msg)

    def consume_error(self, status: StatusMessage) -> None:
        self._errors.append(status)

    @property
    def received(self) -> List[EventMessage]:
        return list(self._received)

    @property
    def errors(self) -> List[StatusMessage]:
        return list(self._errors)
