"""
Targeted serialization tests for each of the 3 bugs.
"""
import json
import os
import tempfile
import pytest
from datetime import datetime
from models import UserEvent
from producer import serialize_event
from processor import parse_timestamp, transform_event, process_events
from sink import load_processed_events


def _make_event(**overrides):
    defaults = {
        "event_id": "evt-001",
        "timestamp": datetime(2023, 11, 14, 22, 13, 20),
        "user_name": "TestUser",
        "action": "page_view",
        "page_url": "test-value",
    }
    defaults.update(overrides)
    return UserEvent(**defaults)


class TestBug1DatetimeFormat:
    """Bug 1: Producer must use ISO 8601 (T-separated), not space-separated."""

    def test_serialized_timestamp_has_T_separator(self):
        event = _make_event()
        serialized = serialize_event(event)
        data = json.loads(serialized)
        ts = data["timestamp"]
        assert "T" in ts, (
            f"Timestamp must use ISO 8601 T separator, got: {ts!r}. "
            "Use .isoformat() instead of default=str."
        )

    def test_serialized_timestamp_parseable_by_fromisoformat(self):
        event = _make_event()
        serialized = serialize_event(event)
        data = json.loads(serialized)
        ts = data["timestamp"]
        # This must not raise
        parsed = datetime.fromisoformat(ts)
        assert parsed.year == 2023
        assert parsed.month == 11

    def test_processor_can_parse_producer_output(self):
        """The processor's parse_timestamp must work on producer output."""
        event = _make_event()
        serialized = serialize_event(event)
        data = json.loads(serialized)
        # Must not raise ValueError
        parsed = parse_timestamp(data["timestamp"])
        assert isinstance(parsed, datetime)


class TestBug2NoEnvelope:
    """Bug 2: Processor must emit bare objects, not wrapped in {"data": ...}."""

    def test_processed_output_is_bare_object(self, tmp_path):
        produced = tmp_path / "produced.jsonl"
        processed = tmp_path / "processed.jsonl"

        event = _make_event(user_name="SimpleUser")
        with open(produced, "w") as f:
            f.write(serialize_event(event) + "\n")

        process_events(str(produced), str(processed))

        with open(processed, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        data = json.loads(line)

        assert "data" not in data or isinstance(data.get("data"), str), (
            f"Processor output must be bare object, not envelope. "
            f"Got key 'data' wrapping: {list(data.keys())}"
        )
        assert "event_id" in data, (
            f"Bare object must have 'event_id' at top level, got: {list(data.keys())}"
        )

    def test_sink_can_load_processed(self, tmp_path):
        produced = tmp_path / "produced.jsonl"
        processed = tmp_path / "processed.jsonl"

        event = _make_event(user_name="SimpleUser")
        with open(produced, "w") as f:
            f.write(serialize_event(event) + "\n")

        process_events(str(produced), str(processed))
        loaded = load_processed_events(str(processed))
        assert len(loaded) == 1
        assert loaded[0]["event_id"] == "evt-001"


class TestBug3Utf8Encoding:
    """Bug 3: Processor must write UTF-8, not latin-1."""

    def test_non_ascii_roundtrip(self, tmp_path):
        produced = tmp_path / "produced.jsonl"
        processed = tmp_path / "processed.jsonl"

        event = _make_event(
            user_name="Müller",
            page_url="https://example.com/café",
        )
        with open(produced, "w", encoding="utf-8") as f:
            f.write(serialize_event(event) + "\n")

        process_events(str(produced), str(processed))

        # Sink reads UTF-8 — must not raise UnicodeDecodeError
        loaded = load_processed_events(str(processed))
        assert loaded[0]["user_name"] == "Müller"

    def test_euro_sign_preserved(self, tmp_path):
        """Euro sign and other non-latin1 chars must survive."""
        produced = tmp_path / "produced.jsonl"
        processed = tmp_path / "processed.jsonl"

        event = _make_event(page_url="Price: \u20ac99.99")
        with open(produced, "w", encoding="utf-8") as f:
            f.write(serialize_event(event) + "\n")

        process_events(str(produced), str(processed))
        loaded = load_processed_events(str(processed))
        assert "\u20ac" in loaded[0]["page_url"]
