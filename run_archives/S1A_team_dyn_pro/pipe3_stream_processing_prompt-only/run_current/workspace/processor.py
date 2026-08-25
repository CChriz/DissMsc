"""
Event processor for user_analytics pipeline.

Reads JSON events from producer, transforms them, and writes processed output.

Bug 2: Wraps output in {"data": ...} envelope, but sink expects bare objects.
Bug 3: Writes output with latin-1 encoding, but sink reads UTF-8.
"""
import json
import os
from datetime import datetime


def parse_timestamp(ts_str: str) -> datetime:
    """Parse a timestamp string into a datetime object.

    Expects ISO 8601 format: "YYYY-MM-DDTHH:MM:SS"
    Will fail on "YYYY-MM-DD HH:MM:SS" (space instead of T).
    """
    return datetime.fromisoformat(ts_str)


def transform_event(event_data: dict) -> dict:
    """Transform a raw event dict into processed output.

    Adds a processed_at timestamp and normalizes fields.
    """
    processed = dict(event_data)
    # Parse and re-format the timestamp to ensure consistency
    ts = parse_timestamp(event_data["timestamp"])
    processed["timestamp"] = ts.isoformat()
    processed["processed_at"] = datetime.utcnow().isoformat()
    processed["action"] = event_data["action"].upper()
    return processed


def process_events(input_path: str, output_path: str) -> int:
    """Read events, transform, and write to output.

    Bug 2: Wraps each output line in {"data": ...} envelope.
    Bug 3: Opens output file with latin-1 encoding.

    Returns number of events processed.
    """
    count = 0
    # Bug 3: latin-1 encoding — will corrupt non-ASCII characters for UTF-8 reader
    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            event_data = json.loads(line)
            processed = transform_event(event_data)
            # Fix: emit bare objects, no envelope wrapping
            fout.write(json.dumps(processed, ensure_ascii=False) + "\n")
            count += 1
    return count
