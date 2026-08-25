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

    # Bug 1 FIXED: int64 — removed 32-bit mask, Python int handles arbitrary precision
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 FIXED: bytes field — base64-decode the JSON string to raw bytes
    payload_b64 = data.get("payload", "")
    msg.payload = base64.b64decode(payload_b64)

    # Bug 3 FIXED: oneof — only set one content variant based on input keys
    if "text_content" in data:
        msg.text_content = data["text_content"]
    elif "binary_content" in data:
        msg.binary_content = data["binary_content"]

    # Bug 4 FIXED: enum — map string name to integer code via STATUS_MAP
    msg.status = STATUS_MAP.get(data.get("status", "STATUS_UNKNOWN"), 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
