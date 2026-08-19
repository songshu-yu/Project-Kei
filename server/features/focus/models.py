"""Request and response models for the focus module."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class FocusStartRequest(BaseModel):
    mode: str = "pomodoro"
    minutes: Optional[float] = None
    task: str = ""
    force: bool = False
    with_audio: bool = True

    class Config:
        extra = "forbid"


class FocusEncouragementRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    start_at: str = Field(min_length=1, max_length=64)

    class Config:
        extra = "forbid"


class FocusEncouragementResponse(BaseModel):
    eligible: bool
    generated: bool
    text: str = ""
    error_code: Optional[str] = None


class TimerResult(BaseModel):
    status: str
    active: bool
    mode: str
    label: str
    task: str
    started: bool
    already_active: bool
    stopped: bool
    completed: bool
    session_id: str
    start_at: str
    end_at: str
    duration_minutes: float
    remaining_seconds: int
    elapsed_seconds: int
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """Keep the legacy systems.focus_timer return contract."""
        return self.dict()
