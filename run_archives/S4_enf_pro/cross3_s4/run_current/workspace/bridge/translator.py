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

    # Bug 1 fix: int64 — no truncation; Python int natively supports arbitrary precision
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 fix: bytes field — base64 decode from JSON string (RFC 4648)
    payload_str = data.get("payload", "")
    msg.payload = base64.b64decode(payload_str) if payload_str else b""

    # Bug 3 fix: oneof — only set the last variant present (proto3 JSON behaviour)
    oneof_keys = [k for k in data if k in ("text_content", "binary_content")]
    if oneof_keys:
        last_key = oneof_keys[-1]  # last variant wins per proto3 spec
        if last_key == "binary_content":
            bin_val = data["binary_content"]
            msg.binary_content = base64.b64decode(bin_val) if bin_val else b""
            msg.text_content = ""
        else:
            msg.text_content = data["text_content"]
            msg.binary_content = b""
    else:
        msg.text_content = ""
        msg.binary_content = b""

    # Bug 4 fix: enum — map string name to integer value
    status_str = data.get("status", "STATUS_UNKNOWN")
    msg.status = STATUS_MAP.get(status_str, 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
