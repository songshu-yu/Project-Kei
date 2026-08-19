"""HTTP and public result models for the demon-slayer module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel


@dataclass(frozen=True)
class CheckinResult:
    goal_id: str
    date: str
    done: bool
    points_awarded: int
    total_points: int
    message: str
    duplicate: bool = False
    repeat_mode: str = "recurring"
    active_since: Optional[str] = None
    active_days: Optional[int] = None
    current_streak: int = 0
    longest_streak: int = 0
    streak_unit: str = "day"
    encouragement: str = ""
    kei_generated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "date": self.date,
            "done": self.done,
            "points_awarded": self.points_awarded,
            "total_points": self.total_points,
            "message": self.message,
            "duplicate": self.duplicate,
            "repeat_mode": self.repeat_mode,
            "active_since": self.active_since,
            "active_days": self.active_days,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "streak_unit": self.streak_unit,
            "encouragement": self.encouragement,
            "kei_generated": self.kei_generated,
        }


class GoalCreateRequest(BaseModel):
    title: str
    cadence: str = "auto"
    category: str = "auto"
    repeat_mode: str = "recurring"
    target_date: Optional[str] = None


class GoalUpdateRequest(BaseModel):
    title: Optional[str] = None
    cadence: Optional[str] = None
    category: Optional[str] = None
    repeat_mode: Optional[str] = None
    target_date: Optional[str] = None


class CheckinRequest(BaseModel):
    goal_id: str
    date: Optional[str] = None
    done: bool = True
    note: str = ""
    with_encouragement: bool = False


class RewardCreateRequest(BaseModel):
    title: str
    cost: int = 120
    description: str = ""


class RewardRedeemRequest(BaseModel):
    request_id: Optional[str] = None


class LegacyPlanRequest(BaseModel):
    text: str
    reset_existing: bool = False
    cadence: Optional[str] = None
    category: Optional[str] = None
    repeat_mode: str = "recurring"
    target_date: Optional[str] = None
    with_audio: bool = False


class LegacyCheckinRequest(CheckinRequest):
    with_audio: bool = False


class LegacyRedeemRequest(BaseModel):
    wish_id: str
    request_id: Optional[str] = None


__all__ = [
    "CheckinRequest",
    "CheckinResult",
    "GoalCreateRequest",
    "GoalUpdateRequest",
    "LegacyCheckinRequest",
    "LegacyPlanRequest",
    "LegacyRedeemRequest",
    "RewardCreateRequest",
    "RewardRedeemRequest",
]
