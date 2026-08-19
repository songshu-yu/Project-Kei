"""Public request models for QQ control and scheduler configuration."""
from __future__ import annotations

from pydantic import BaseModel


class DailyBriefingScheduleUpdate(BaseModel):
    enabled: bool = False
    prebuild_time: str = "07:00"
    send_time: str = "08:00"

    class Config:
        extra = "forbid"


class LifeSupportScheduleUpdate(BaseModel):
    enabled: bool = False
    start_time: str = "08:00"
    end_time: str = "22:00"
    interval_hours: int = 2
    interval_minutes: int = 0

    class Config:
        extra = "forbid"


class LifeSupportReminderRequest(BaseModel):
    kind: str

    class Config:
        extra = "forbid"
