"""
Tests for bridge/translator.py — each test targets one of the 4 translation bugs.
"""
import pytest
import base64
from bridge.translator import translate_event


def test_int64_not_truncated():
    """Bug 1: Large int64 values must not be truncated to 32-bit.

    9007199254740993 = 2^53 + 1, which exceeds int32 range (2^31 - 1 = 2147483647).
    After & 0xFFFFFFFF the value becomes 1, which is wrong.
    """
    large_id = 9007199254740993
    data = {
        "event_id": large_id,
        "event_type": "test",
        "payload": "dGVzdA==",
        "status": "STATUS_ACTIVE",
        "occurred_at": 0,
    }
    msg = translate_event(data)
    assert msg.event_id == large_id, (
        f"int64 truncated: got {msg.event_id}, expected {large_id}. "
        "Remove the & 0xFFFFFFFF mask."
    )


def test_bytes_field_base64_decoded():
    """Bug 2: Payload must be base64-decoded bytes, not a raw string."""
    raw = b"binary data here"
    b64 = base64.b64encode(raw).decode()
    data = {
        "event_id": 1,
        "event_type": "test",
        "payload": b64,
        "status": "STATUS_ACTIVE",
        "occurred_at": 0,
    }
    msg = translate_event(data)
    assert isinstance(msg.payload, bytes), (
        f"payload must be bytes, got {type(msg.payload)}. "
        "Use base64.b64decode()."
    )
    assert msg.payload == raw, (
        f"Decoded payload mismatch: {msg.payload!r} != {raw!r}"
    )


def test_oneof_single_variant_text():
    """Bug 3: When text_content is present, only content_text must be set."""
    data = {
        "event_id": 1,
        "event_type": "test",
        "payload": "dGVzdA==",
        "status": "STATUS_ACTIVE",
        "occurred_at": 0,
        "text_content": "hello world",
        # binary_content absent
    }
    msg = translate_event(data)
    assert not (msg.text_content and msg.binary_content), (
        f"oneof violation: both variants set "
        f"(text={msg.text_content!r}, binary={msg.binary_content!r}). "
        "Only set one oneof variant."
    )
    assert msg.text_content == "hello world", (
        f"content_text not set: {msg.text_content!r}"
    )


def test_oneof_single_variant_empty():
    """Bug 3: When neither content field present, both must remain falsy."""
    data = {
        "event_id": 1,
        "event_type": "test",
        "payload": "dGVzdA==",
        "status": "STATUS_ACTIVE",
        "occurred_at": 0,
    }
    msg = translate_event(data)
    assert not (msg.text_content and msg.binary_content), (
        "oneof violation: both variants truthy when neither content key is in input"
    )


def test_enum_mapped_to_int():
    """Bug 4: Status must be an integer code, not a string name."""
    status_map = {
        "STATUS_UNKNOWN": 0,
        "STATUS_ACTIVE": 1,
        "STATUS_INACTIVE": 2,
        "STATUS_PENDING": 3,
    }
    for status_str, expected_int in status_map.items():
        data = {
            "event_id": 1,
            "event_type": "test",
            "payload": "dGVzdA==",
            "status": status_str,
            "occurred_at": 0,
        }
        msg = translate_event(data)
        assert isinstance(msg.status, int), (
            f"status must be int, got {type(msg.status)}: {msg.status!r}. "
            "Map string through STATUS_MAP."
        )
        assert msg.status == expected_int, (
            f"{status_str} -> expected {expected_int}, got {msg.status}"
        )
