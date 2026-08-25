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

    # Bug 1 FIXED: int64 fields must be translated as Python int (no truncation)
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 FIXED: bytes field must be base64-decoded from JSON strings
    payload_str = data.get("payload", "")
    msg.payload = base64.b64decode(payload_str) if payload_str else b""

    # Bug 3 FIXED: oneof — only set the variant that has data, not both
    text = data.get("text_content", "")
    binary = data.get("binary_content", "")
    if text:
        msg.text_content = text
    elif binary:
        msg.binary_content = base64.b64decode(binary)

    # Bug 4 FIXED: enum fields must be mapped from string names to integer values
    msg.status = STATUS_MAP.get(data.get("status", "STATUS_UNKNOWN"), 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
