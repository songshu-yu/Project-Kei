"""Domain and HTTP models for conversation and non-secret LLM profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


VALID_EMOTIONS = frozenset({"happy", "shy", "calm", "angry", "sad", "surprised"})
PROFILE_PROVIDERS = frozenset({"deepseek", "custom"})
THINKING_MODES = frozenset({"enabled", "disabled"})


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    emotion: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass(frozen=True)
class ConversationReply:
    text: str
    emotion: str
    timestamp: str


@dataclass(frozen=True)
class TextGenerationResult:
    text: str
    generated: bool
    fallback: bool
    model: Optional[str]
    error_code: Optional[str] = None


@dataclass(frozen=True)
class LLMProfile:
    provider: str
    base_url: str
    model: str
    thinking_mode: str = "disabled"
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "thinking_mode": self.thinking_mode,
            "updated_at": self.updated_at,
        }


class ConversationChatRequest(BaseModel):
    message: str

    class Config:
        extra = "forbid"


class ConversationChatResponse(BaseModel):
    text: str
    emotion: str
    timestamp: str


class LegacyChatRequest(BaseModel):
    message: str
    with_audio: bool = True

    class Config:
        extra = "forbid"


class LegacyChatResponse(ConversationChatResponse):
    audio_base64: str = ""


class HistoryMessageResponse(BaseModel):
    role: str
    content: str
    emotion: str = ""


class HistoryResponse(BaseModel):
    count: int
    messages: List[HistoryMessageResponse]


class HistoryClearResponse(BaseModel):
    status: str
    cleared: int


class LLMProfileUpdate(BaseModel):
    provider: str = "deepseek"
    base_url: str
    model: str
    thinking_mode: str = "disabled"

    class Config:
        extra = "forbid"


class LLMProfileResponse(BaseModel):
    provider: str
    base_url: str
    model: str
    thinking_mode: str
    updated_at: Optional[str] = None
