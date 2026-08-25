"""
End-to-end pipeline tests for user_analytics.
"""
import json
import os
import tempfile
import pytest
from datetime import datetime
from models import UserEvent
from producer import serialize_event, produce_events
from processor import process_events
from sink import load_processed_events, write_summary


def _make_event(**overrides):
    defaults = {
        "event_id": "evt-001",
        "timestamp": datetime(2023, 11, 14, 22, 13, 20),
        "user_name": "Müller",
        "action": "page_view",
        "page_url": "https://example.com/café",
    }
    defaults.update(overrides)
    return UserEvent(**defaults)


class TestEndToEnd:
    """Full pipeline: produce -> process -> sink."""

    def test_full_pipeline(self, tmp_path):
        """Events flow through all 3 stages without error."""
        produced = tmp_path / "produced.jsonl"
        processed = tmp_path / "processed.jsonl"
        summary = tmp_path / "summary.json"

        events = [
            _make_event(event_id="evt-001"),
            _make_event(
                event_id="evt-002",
                user_name="Müller",
                action="click",
            ),
        ]

        produce_events(events, str(produced))
        count = process_events(str(produced), str(processed))
        assert count == 2

        loaded = load_processed_events(str(processed))
        assert len(loaded) == 2

        result = write_summary(loaded, str(summary))
        assert result["total_events"] == 2

    def test_non_ascii_survives_pipeline(self, tmp_path):
        """Non-ASCII characters (accents, euro sign) must survive the full pipeline."""
        produced = tmp_path / "produced.jsonl"
        processed = tmp_path / "processed.jsonl"

        events = [_make_event(
            user_name="Müller",
            page_url="https://example.com/café",
        )]

        produce_events(events, str(produced))
        process_events(str(produced), str(processed))
        loaded = load_processed_events(str(processed))

        assert loaded[0]["user_name"] == "Müller"
        assert loaded[0]["page_url"] == "https://example.com/café"

    def test_multiple_events_correct_count(self, tmp_path):
        produced = tmp_path / "produced.jsonl"
        processed = tmp_path / "processed.jsonl"
        summary = tmp_path / "summary.json"

        events = [
            _make_event(event_id=f"evt-{i:03d}")
            for i in range(5)
        ]

        produce_events(events, str(produced))
        process_events(str(produced), str(processed))
        loaded = load_processed_events(str(processed))
        result = write_summary(loaded, str(summary))

        assert result["total_events"] == 5
