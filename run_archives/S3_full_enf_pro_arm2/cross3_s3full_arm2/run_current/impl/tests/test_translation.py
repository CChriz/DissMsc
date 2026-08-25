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


# ── Bug 1 boundary cases: int64 ──────────────────────────────────

class TestInt64Boundary:
    """Verify int64 values are not truncated at any boundary."""

    def _make_data(self, event_id):
        return {
            "event_id": event_id,
            "event_type": "test",
            "payload": "",
            "status": "STATUS_UNKNOWN",
            "occurred_at": 0,
        }

    def test_zero(self):
        msg = translate_event(self._make_data(0))
        assert msg.event_id == 0

    def test_int32_max(self):
        msg = translate_event(self._make_data(2**31 - 1))
        assert msg.event_id == 2147483647

    def test_above_32bit(self):
        """Values above 2^32 must survive without truncation."""
        msg = translate_event(self._make_data(2**32))
        assert msg.event_id == 4294967296

    def test_int64_max(self):
        msg = translate_event(self._make_data(2**63 - 1))
        assert msg.event_id == 9223372036854775807

    def test_int64_min(self):
        msg = translate_event(self._make_data(-(2**63)))
        assert msg.event_id == -9223372036854775808

    def test_negative_value(self):
        msg = translate_event(self._make_data(-1000))
        assert msg.event_id == -1000

    def test_snowflake_id(self):
        """Snowflake-style large integer IDs must not be damaged."""
        snowflake_id = 1759288472991170632
        msg = translate_event(self._make_data(snowflake_id))
        assert msg.event_id == snowflake_id


# ── Bug 2 boundary cases: bytes base64 ───────────────────────────

class TestBytesBase64Edge:
    """Verify base64 decoding handles edge cases correctly."""

    def _make_data(self, payload):
        return {
            "event_id": 1,
            "event_type": "test",
            "payload": payload,
            "status": "STATUS_ACTIVE",
            "occurred_at": 0,
        }

    def test_empty_payload(self):
        msg = translate_event(self._make_data(""))
        assert msg.payload == b""

    def test_unpadded(self):
        """b64decode should handle missing padding automatically."""
        msg = translate_event(self._make_data("SGVsbG8"))
        assert msg.payload == b"Hello"

    def test_null_bytes(self):
        msg = translate_event(self._make_data("AAEC"))
        assert msg.payload == b"\x00\x01\x02"

    def test_high_bytes(self):
        msg = translate_event(self._make_data("//79"))
        assert msg.payload == b"\xff\xfe\xfd"

    def test_invalid_base64(self):
        """Invalid base64 must not crash — should fall back to empty bytes."""
        msg = translate_event(self._make_data("!!!invalid!!!"))
        assert msg.payload == b""


# ── Bug 3 boundary cases: oneof ──────────────────────────────────

class TestOneofBinary:
    """Verify oneof with binary_content variant."""

    def _make_data(self, text_content="", binary_content=""):
        data = {
            "event_id": 1,
            "event_type": "test",
            "payload": "",
            "status": "STATUS_ACTIVE",
            "occurred_at": 0,
        }
        if text_content:
            data["text_content"] = text_content
        if binary_content:
            data["binary_content"] = binary_content
        return data

    def test_binary_variant(self):
        """When binary_content is present (and no text), only binary set."""
        raw = b"\x00\x01\x02"
        b64 = base64.b64encode(raw).decode()
        msg = translate_event(self._make_data(binary_content=b64))
        assert msg.binary_content == raw
        assert not msg.text_content

    def test_text_wins_over_binary(self):
        """When both present, text_content takes priority (exactly one set)."""
        raw = b"\x00\x01\x02"
        b64 = base64.b64encode(raw).decode()
        msg = translate_event(self._make_data(
            text_content="hello",
            binary_content=b64,
        ))
        assert msg.text_content == "hello"
        assert msg.binary_content == b""

    def test_unknown_content_not_crash(self):
        """Neither content — both remain default/empty."""
        msg = translate_event(self._make_data())
        assert msg.text_content == ""
        assert msg.binary_content == b""


# ── Bug 4 boundary cases: enum ───────────────────────────────────

class TestEnumEdge:
    """Verify enum string-to-int mapping edge cases."""

    def _make_data(self, status):
        return {
            "event_id": 1,
            "event_type": "test",
            "payload": "",
            "status": status,
            "occurred_at": 0,
        }

    def test_unknown_name_defaults_to_zero(self):
        """Unrecognized enum name defaults to 0 (proto3 behavior)."""
        msg = translate_event(self._make_data("STATUS_DELETED"))
        assert msg.status == 0

    def test_empty_string_defaults_to_zero(self):
        msg = translate_event(self._make_data(""))
        assert msg.status == 0

    def test_missing_status_defaults_to_zero(self):
        data = {
            "event_id": 1,
            "event_type": "test",
            "payload": "",
            "occurred_at": 0,
        }
        msg = translate_event(data)
        assert isinstance(msg.status, int)
        assert msg.status == 0
