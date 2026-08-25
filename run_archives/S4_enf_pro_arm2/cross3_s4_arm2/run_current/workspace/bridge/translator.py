"""
Bridge translator: converts Service A JSON dicts into Service B messages.

All 4 translation bugs fixed:
- Bug 1: int64 — no truncation, full Python int precision
- Bug 2: bytes — base64-decoded from JSON string
- Bug 3: oneof — exactly one variant set based on input keys
- Bug 4: enum — string name mapped to integer via STATUS_MAP
"""
import base64
import logging
from service_b.schema import EventMessage, EventStatus

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "STATUS_UNKNOWN": 0,
    "STATUS_ACTIVE": 1,
    "STATUS_INACTIVE": 2,
    "STATUS_PENDING": 3,
}


def translate_event_streaming(data: dict) -> EventMessage:
    """Translate JSON data from Service A to EventMessage for Service B."""
    msg = EventMessage()

    # Bug 1 fix: int64 — Python int has arbitrary precision, no mask/truncation
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 fix: bytes — base64-decode the payload string from JSON
    payload_str = data.get("payload", "")
    msg.payload = base64.b64decode(payload_str) if payload_str else b""

    # Bug 3 fix: oneof — set exactly one variant based on which keys are present
    text_val = data.get("text_content", "")
    binary_val = data.get("binary_content", "")
    text_present = "text_content" in data and bool(text_val)
    binary_present = "binary_content" in data and bool(binary_val)

    if text_present and binary_present:
        # Multiple variants: set only the first, log warning
        logger.warning(
            "oneof ambiguity: both text_content and binary_content present, "
            "selecting text_content"
        )
        msg.text_content = text_val
    elif text_present:
        msg.text_content = text_val
    elif binary_present:
        # binary_content is base64-encoded in JSON, decode to bytes
        msg.binary_content = base64.b64decode(binary_val) if binary_val else b""

    # Bug 4 fix: enum — map string name to integer via STATUS_MAP
    status_str = data.get("status", "STATUS_UNKNOWN")
    msg.status = STATUS_MAP.get(status_str, 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
