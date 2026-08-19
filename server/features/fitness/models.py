"""HTTP and domain models for the built-in fitness module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


@dataclass(frozen=True)
class FitnessCheckinResult:
    checked_in: bool
    already_checked_in: bool
    date: str
    streak: int
    total_checkins: int
    reward_unlocked: bool
    reward_text: str
    next_reward_in: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checked_in": self.checked_in,
            "already_checked_in": self.already_checked_in,
            "date": self.date,
            "streak": self.streak,
            "total_checkins": self.total_checkins,
            "reward_unlocked": self.reward_unlocked,
            "reward_text": self.reward_text,
            "next_reward_in": self.next_reward_in,
        }


class FitnessCheckinRequest(BaseModel):
    date: Optional[str] = None
    note: str = ""


class LegacyFitnessCheckinRequest(FitnessCheckinRequest):
    with_audio: bool = True


class FitnessCheckinResponse(BaseModel):
    checked_in: bool
    already_checked_in: bool
    date: str
    streak: int
    total_checkins: int
    reward_unlocked: bool
    reward_text: str
    next_reward_in: int


class LegacyFitnessCheckinResponse(FitnessCheckinResponse):
    audio_base64: str = ""


class FitnessStatusResponse(BaseModel):
    date: str
    checked_today: bool
    streak: int
    total_checkins: int
    next_reward_in: int
    reward_streak_days: int
    recent_checkins: List[str]
    rewards: List[Dict[str, Any]]


class FitnessResetResponse(BaseModel):
    status: str
    cleared_checkins: int
    cleared_rewards: int


__all__ = [
    "FitnessCheckinRequest",
    "FitnessCheckinResponse",
    "FitnessCheckinResult",
    "FitnessResetResponse",
    "FitnessStatusResponse",
    "LegacyFitnessCheckinRequest",
    "LegacyFitnessCheckinResponse",
]
