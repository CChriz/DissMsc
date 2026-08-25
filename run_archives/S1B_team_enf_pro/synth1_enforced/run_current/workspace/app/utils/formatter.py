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
    eastern = ZoneInfo("US/Eastern")
    local_dt = dt.astimezone(eastern)
    return local_dt.strftime("%Y-%m-%d")
