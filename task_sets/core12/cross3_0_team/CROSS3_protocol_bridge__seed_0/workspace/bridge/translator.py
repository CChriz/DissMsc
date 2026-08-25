"""
Bridge translator: converts Service A JSON dicts into Service B messages.

Contains 4 bugs — see spec.md for details.
"""
import base64
from service_b.schema import EventMessage, EventStatus

STATUS_MAP = {
    "STATUS_UNKNOWN": 0,
    "STATUS_ACTIVE": 1,
    "STATUS_INACTIVE": 2,
    "STATUS_PENDING": 3,
}


def translate_event_streaming(data: dict) -> EventMessage:
    """Translate JSON data from Service A to EventMessage for Service B."""
    msg = EventMessage()

    # Bug 1: int64 truncation — masks large IDs to 32-bit
    msg.event_id = int(data.get("event_id", 0)) & 0xFFFFFFFF

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2: bytes field not base64-decoded — assigns raw string instead of bytes
    msg.payload = data.get("payload", "")

    # Bug 3: oneof — sets both content fields instead of exactly one
    msg.text_content = data.get("text_content", "")
    msg.binary_content = data.get("binary_content", b"")

    # Bug 4: enum string not mapped to int — assigns string directly
    msg.status = data.get("status", "STATUS_UNKNOWN")

    return msg


# Alias used by tests
translate_event = translate_event_streaming
