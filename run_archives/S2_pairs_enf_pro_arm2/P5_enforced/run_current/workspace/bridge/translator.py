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


def _to_int(value):
    """Convert a JSON int64 value to an arbitrary-precision Python int.

    proto3 JSON mapping permits int64 to be serialized as a decimal string to
    avoid JavaScript precision loss, so both JSON numbers and strings must be
    accepted. The result must never be masked or narrowed to 32 bits.
    """
    if isinstance(value, str):
        return int(value)
    return int(value)


def _decode_bytes(value):
    """Base64-decode a JSON bytes value into raw bytes.

    proto3 bytes fields are base64-encoded in JSON using the RFC 4648 standard
    alphabet with padding. Use validate=True so invalid characters raise an
    error instead of being silently ignored.
    """
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return base64.b64decode(value.encode("ascii"), validate=True)
    raise TypeError(f"expected str or bytes for base64 field, got {type(value)!r}")


def _map_status(status):
    """Map a proto3 enum name to its integer code.

    proto3 JSON uses the enum value *name* (canonical form). Known names are
    looked up in STATUS_MAP; unknown names raise ValueError instead of silently
    defaulting to 0. Integer inputs are passed through unchanged.
    """
    if isinstance(status, bool):
        raise ValueError(f"invalid status: {status!r}")
    if isinstance(status, int):
        return status
    if isinstance(status, str):
        if status in STATUS_MAP:
            return STATUS_MAP[status]
        raise ValueError(f"unknown status name: {status!r}")
    raise TypeError(f"invalid status type: {type(status)!r}")


def translate_event_streaming(data: dict) -> EventMessage:
    """Translate JSON data from Service A to EventMessage for Service B."""
    msg = EventMessage()

    # Bug 1 (fixed): int64 must keep arbitrary precision — no 32-bit mask.
    msg.event_id = _to_int(data.get("event_id", 0))

    msg.event_type = data.get("event_type", "")
    msg.occurred_at = _to_int(data.get("occurred_at", 0))

    # Bug 2 (fixed): bytes fields are base64-encoded in JSON; decode to raw bytes.
    msg.payload = _decode_bytes(data.get("payload", ""))

    # Bug 4 (fixed): enum names must map to integer codes, not stay as strings.
    msg.status = _map_status(data.get("status", "STATUS_UNKNOWN"))

    # Bug 3 (fixed): oneof — set exactly one variant. Prefer text_content
    # (declared first in the schema) when both keys are present.
    text_content = data.get("text_content")
    binary_content = data.get("binary_content")
    if text_content:
        msg.text_content = str(text_content)
    elif binary_content:
        msg.binary_content = _decode_bytes(binary_content)

    return msg


# Alias used by tests
translate_event = translate_event_streaming
