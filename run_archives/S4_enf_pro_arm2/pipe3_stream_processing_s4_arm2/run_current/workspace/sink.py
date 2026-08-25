"""
Output sink for user_analytics pipeline.

Reads processed events and writes final output. Expects:
  - Bare JSON objects (no envelope wrapping)
  - UTF-8 encoded input
  - ISO 8601 timestamps
"""
import json
import os
from datetime import datetime


def load_processed_events(input_path: str) -> list[dict]:
    """Load processed events from a JSONL file.

    Expects:
      - Each line is a bare JSON object (NOT wrapped in {"data": ...})
      - File is UTF-8 encoded
      - Timestamps are ISO 8601
    """
    events = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            # Expect bare object with direct field access
            _ = event["event_id"]  # Will KeyError if wrapped in envelope
            _ = event["timestamp"]
            events.append(event)
    return events


def write_summary(events: list[dict], output_path: str) -> dict:
    """Write a summary of processed events."""
    summary = {
        "total_events": len(events),
        "actions": {},
        "users": set(),
    }
    for evt in events:
        action = evt["action"]
        summary["actions"][action] = summary["actions"].get(action, 0) + 1
        summary["users"].add(evt["user_name"])

    summary["unique_users"] = len(summary["users"])
    summary["users"] = sorted(summary["users"])

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary