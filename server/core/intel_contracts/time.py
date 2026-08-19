"""Timezone helpers shared by optional intelligence modules."""
from __future__ import annotations

from datetime import datetime

try:  # Python 3.9+
    from zoneinfo import ZoneInfo

    def get_timezone(name: str):
        return ZoneInfo(name)

    def localize(value: datetime, timezone_name: str) -> datetime:
        return value.replace(tzinfo=ZoneInfo(timezone_name))

except ImportError:  # Project Kei's supported Python 3.8 environment
    import pytz

    def get_timezone(name: str):
        return pytz.timezone(name)

    def localize(value: datetime, timezone_name: str) -> datetime:
        return pytz.timezone(timezone_name).localize(value)


__all__ = ["get_timezone", "localize"]
