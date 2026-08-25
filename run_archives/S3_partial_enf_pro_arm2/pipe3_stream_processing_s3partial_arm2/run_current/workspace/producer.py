"""
Event producer for user_analytics pipeline.

Generates JSON-serialized events and writes them to an output file.

Bug 1: Uses json.dumps(default=str) for datetime serialization, which produces
       "2023-11-14 22:13:20" format instead of ISO 8601 "2023-11-14T22:13:20".
"""
import json
import os
from datetime import datetime, date
from models import UserEvent


def json_serializer(obj):
    """Serialize datetime/date objects via .isoformat() for ISO 8601 output."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def serialize_event(event: UserEvent) -> str:
    """Serialize an event to JSON string.

    Bug: default=str converts datetime to "YYYY-MM-DD HH:MM:SS" (space-separated).
    The processor expects ISO 8601 format "YYYY-MM-DDTHH:MM:SS" (T-separated).
    Fix: use .isoformat() for datetime fields.
    """
    data = {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "user_name": event.user_name,
        "action": event.action,
        "page_url": event.page_url,
    }
    return json.dumps(data, default=json_serializer)


def produce_events(events: list[UserEvent], output_path: str) -> None:
    """Write events to output file, one JSON object per line."""
    with open(output_path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(serialize_event(event) + "\n")
