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

    # Bug 1 FIXED: int64 values preserved without 32-bit truncation
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 FIXED: base64-decode payload from JSON string to bytes
    raw_payload = data.get("payload", "")
    msg.payload = base64.b64decode(raw_payload) if raw_payload else b""

    # Bug 3 FIXED: oneof — only set the variant present in input; binary also base64-decoded
    text_val = data.get("text_content", "")
    binary_val = data.get("binary_content", "")
    if text_val:
        msg.text_content = text_val
    elif binary_val:
        msg.binary_content = base64.b64decode(binary_val) if binary_val else b""

    # Bug 4 FIXED: map enum string name to integer code via STATUS_MAP
    msg.status = STATUS_MAP.get(data.get("status", ""), 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
