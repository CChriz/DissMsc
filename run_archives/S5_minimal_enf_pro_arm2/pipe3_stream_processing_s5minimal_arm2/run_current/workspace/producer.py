"""
Event producer for user_analytics pipeline.

Generates JSON-serialized events and writes them to an output file.

Fixed: Uses DateTimeEncoder with .isoformat() to produce ISO 8601
       "2023-11-14T22:13:20" format for datetime fields.
"""
import json
import os
from datetime import datetime, date
from models import UserEvent


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that serializes datetime as ISO 8601 strings."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def serialize_event(event: UserEvent) -> str:
    """Serialize an event to JSON string.

    Uses DateTimeEncoder to produce ISO 8601 "YYYY-MM-DDTHH:MM:SS" format
    for datetime fields, matching the processor's expectations.
    """
    data = {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "user_name": event.user_name,
        "action": event.action,
        "page_url": event.page_url,
    }
    return json.dumps(data, cls=DateTimeEncoder)


def produce_events(events: list[UserEvent], output_path: str) -> None:
    """Write events to output file, one JSON object per line."""
    with open(output_path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(serialize_event(event) + "\n")
