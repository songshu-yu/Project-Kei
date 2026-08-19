"""Public HTTP and domain models for affection and long-term memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class StrictRequest(BaseModel):
    class Config:
        extra = "forbid"


class RelationshipEventRequest(StrictRequest):
    context: str = ""
    force_event: str = ""
    seed: Optional[int] = None


class RelationshipChoiceRequest(StrictRequest):
    choice_id: str
    with_audio: bool = True


class MemoryAddRequest(StrictRequest):
    content: str
    tags: List[str] = Field(default_factory=list)
    source: str = "api"
    request_id: Optional[str] = None


@dataclass
class RelationshipResult:
    status: str
    event: Optional[dict[str, Any]]
    stats: dict[str, Any]
    message: str
    reply: str = ""
    effects: Optional[dict[str, int]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "event": self.event,
            "stats": self.stats,
            "message": self.message,
            "reply": self.reply,
            "effects": self.effects or {},
        }


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    content: str
    tags: list[str] = field(default_factory=list)
    source: str = "user"
    created_at: str = ""
    request_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, "created_at", datetime.now().isoformat(timespec="seconds"))

    def to_storage_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if not self.request_id:
            value.pop("request_id", None)
        return value

    def to_public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("request_id", None)
        return value


@dataclass(frozen=True)
class MemoryCommand:
    action: str
    content: str = ""
    index: Optional[int] = None


@dataclass(frozen=True)
class MemoryCommandReply:
    text: str
    emotion: str
    timestamp: str


__all__ = [
    "MemoryAddRequest",
    "MemoryCommand",
    "MemoryCommandReply",
    "MemoryEntry",
    "RelationshipChoiceRequest",
    "RelationshipEventRequest",
    "RelationshipResult",
]
