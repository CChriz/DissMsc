"""
Bridge translator: converts Service A JSON dicts into Service B messages.

Handles 4 type-semantic conversions between JSON (Service A) and
proto3-style messages (Service B):
  1. int64  — no 32-bit truncation
  2. bytes  — base64 decode from JSON string
  3. oneof  — exactly one variant set
  4. enum   — string name mapped to integer code
"""
import base64
import logging
from service_b.schema import EventMessage, EventStatus

logger = logging.getLogger(__name__)


def _safe_b64decode(s: str) -> bytes:
    """Decode a base64 string, adding padding if needed.

    RFC 4648 base64 encoders may omit trailing '=' padding.
    Uses validate=True to reject invalid base64 characters;
    a ValueError is raised for the caller to handle.
    """
    if not s:
        return b""
    # Pad to a multiple of 4 characters
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s, validate=True)


STATUS_MAP = {
    "STATUS_UNKNOWN": 0,
    "STATUS_ACTIVE": 1,
    "STATUS_INACTIVE": 2,
    "STATUS_PENDING": 3,
}


def translate_event_streaming(data: dict) -> EventMessage:
    """Translate JSON data from Service A to EventMessage for Service B.

    Args:
        data: JSON dict from Service A Event Streaming API.

    Returns:
        EventMessage with properly converted proto3-style fields.
    """
    msg = EventMessage()

    # Bug 1 FIX: int64 — no 32-bit truncation.
    # Python int has arbitrary precision; removing & 0xFFFFFFFF mask
    # preserves full int64 range for values like Snowflake IDs.
    msg.event_id = int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = int(data.get("occurred_at", 0))

    # Bug 2 FIX: bytes — base64-decode from JSON string.
    # JSON represents bytes as RFC 4648 base64 strings;
    # Service B expects raw bytes.
    payload_b64 = data.get("payload", "")
    try:
        msg.payload = _safe_b64decode(payload_b64)
    except (ValueError, TypeError) as e:
        logger.warning("Base64 decode failed for payload: %s", e)
        msg.payload = b""

    # Bug 3 FIX: oneof — exactly one of text_content / binary_content.
    # proto3 oneof requires mutual exclusion: if text_content is provided,
    # only text_content is set; if binary_content is provided (and no
    # text_content), only binary_content is set after base64-decoding.
    text_val = data.get("text_content", "")
    binary_val = data.get("binary_content", "")

    if text_val:
        # text_content present — set it, leave binary_content as default (b"")
        msg.text_content = text_val
        msg.binary_content = b""
    elif binary_val:
        # binary_content present — base64-decode to bytes, leave text_content default
        try:
            msg.binary_content = _safe_b64decode(binary_val)
        except (ValueError, TypeError) as e:
            logger.warning("Base64 decode failed for binary_content: %s", e)
            msg.binary_content = b""
        msg.text_content = ""
    # else: neither content field — both remain defaults ("" and b""), which is valid

    # Bug 4 FIX: enum — map string name to integer code.
    # JSON carries enum as string name ("STATUS_ACTIVE");
    # proto3 stores enum as integer. Defaults to 0 (STATUS_UNKNOWN)
    # for unknown or missing names.
    status_str = data.get("status", "STATUS_UNKNOWN")
    msg.status = STATUS_MAP.get(status_str, 0)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
