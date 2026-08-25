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

    # Fix 1: int64 — keep full precision, remove 32-bit mask
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Fix 2: bytes — base64-decode payload string to raw bytes
    payload_str = data.get("payload", "")
    msg.payload = base64.b64decode(payload_str) if payload_str else b""

    # Fix 3: oneof — set exactly one variant based on input presence
    has_text = bool(data.get("text_content"))
    has_binary = bool(data.get("binary_content"))
    if has_text:
        msg.text_content = data["text_content"]
    elif has_binary:
        msg.binary_content = base64.b64decode(data["binary_content"])

    # Fix 4: enum — map string name to integer code via STATUS_MAP
    msg.status = STATUS_MAP.get(data.get("status", "STATUS_UNKNOWN"), 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
