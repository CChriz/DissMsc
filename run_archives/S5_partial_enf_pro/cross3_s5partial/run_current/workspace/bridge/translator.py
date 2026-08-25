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
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2: bytes field now base64-decoded
    msg.payload = base64.b64decode(data.get("payload", ""))

    # Bug 3: oneof — only set one variant (text_content OR binary_content)
    text_val = data.get("text_content", "")
    binary_val = data.get("binary_content", "")
    if text_val:
        msg.text_content = text_val
    elif binary_val:
        msg.binary_content = base64.b64decode(binary_val)

    # Bug 4: enum string now mapped to int via STATUS_MAP
    msg.status = STATUS_MAP.get(data.get("status", "STATUS_UNKNOWN"), 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
