"""Data formatting utilities."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def format_date(dt):
    """Format a datetime for display in reports.

    Args:
        dt: datetime object (may be in any timezone)

    Returns:
        Formatted date string YYYY-MM-DD
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(ZoneInfo("America/New_York"))
    return local.strftime("%Y-%m-%d")
