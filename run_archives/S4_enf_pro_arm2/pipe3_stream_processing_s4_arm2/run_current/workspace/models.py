"""
Shared event schema for user_analytics pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


VALID_ACTIONS = ["page_view", "click", "scroll", "purchase"]


@dataclass
class UserEvent:
    """UserEvent data model."""
    event_id: str
    timestamp: datetime
    user_name: str
    action: str
    page_url: str

    def validate(self) -> bool:
        """Check that the event has valid fields."""
        if not self.event_id:
            raise ValueError("event_id is required")
        if self.action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {self.action}")
        return True