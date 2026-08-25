"""
Event producer for user_analytics pipeline.

Generates JSON-serialized events and writes them to an output file.
"""
import json
import os
from datetime import datetime, date
from models import UserEvent


def _serialize_datetime(obj):
    """Custom JSON serializer: convert datetime/date to ISO 8601 format."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def serialize_event(event: UserEvent) -> str:
    """Serialize an event to JSON string with ISO 8601 timestamps."""
    data = {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "user_name": event.user_name,
        "action": event.action,
        "page_url": event.page_url,
    }
    return json.dumps(data, default=_serialize_datetime)


def produce_events(events: list[UserEvent], output_path: str) -> None:
    """Write events to output file, one JSON object per line."""
    with open(output_path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(serialize_event(event) + "\n")
