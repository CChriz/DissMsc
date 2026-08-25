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

    # Bug 1 FIXED: int64 — no truncation, Python int has arbitrary precision
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 FIXED: bytes field base64-decoded from JSON string
    payload_raw = data.get("payload", "")
    msg.payload = base64.b64decode(payload_raw) if payload_raw else b""

    # Bug 3 FIXED: oneof — only set one variant, prioritize text over binary
    text_val = data.get("text_content")
    binary_val = data.get("binary_content")
    if text_val:
        msg.text_content = text_val
    elif binary_val:
        msg.binary_content = base64.b64decode(binary_val) if isinstance(binary_val, str) else binary_val

    # Bug 4 FIXED: enum string mapped to integer via STATUS_MAP
    status_str = data.get("status", "STATUS_UNKNOWN")
    msg.status = STATUS_MAP.get(status_str, 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
