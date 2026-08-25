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

    # Bug 1 fix: int64 — no 32-bit mask, preserve full precision
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 fix: bytes — base64-decode JSON string to raw bytes
    msg.payload = base64.b64decode(data.get("payload", ""))

    # Bug 3 fix: oneof — set exactly one variant based on which key is present
    text_val = data.get("text_content", "")
    binary_val = data.get("binary_content", "")
    if binary_val:
        msg.binary_content = base64.b64decode(binary_val) if isinstance(binary_val, str) else binary_val
    elif text_val:
        msg.text_content = text_val

    # Bug 4 fix: enum — map string name to integer code via STATUS_MAP
    msg.status = STATUS_MAP.get(data.get("status", "STATUS_UNKNOWN"), 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
