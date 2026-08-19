"""HTTP and domain models for the calendar module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


@dataclass
class CalendarEvent:
    id: str
    title: str
    date: str
    repeat: str = "none"
    note: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date,
            "repeat": self.repeat,
            "note": self.note,
            "tags": list(self.tags),
        }


class CalendarEventRequest(BaseModel):
    title: str
    date: str
    repeat: str = "none"
    note: str = ""
    tags: List[str] = Field(default_factory=list)


class PracticeLogRequest(BaseModel):
    skill: str
    hours: float
    date: Optional[str] = None
    note: str = ""


class CalendarResetRequest(BaseModel):
    confirmation: str
