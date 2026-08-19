"""Optional provider seams used by the installable briefing module."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol


class TextGenerationResult(Protocol):
    text: str
    generated: bool


class BriefingTextGenerator(Protocol):
    @property
    def system_prompt(self) -> str:
        ...

    async def generate_text(
        self,
        system_instruction: str,
        user_input: str,
        *,
        max_tokens: int,
        temperature: float,
        fallback: str,
    ) -> TextGenerationResult:
        ...


class BriefingVoiceProvider(Protocol):
    async def synthesize_briefing(
        self,
        text: str,
        *,
        local_date: str,
    ) -> Dict[str, Any]:
        ...


BriefingVoiceProviderResolver = Callable[[], Optional[BriefingVoiceProvider]]


__all__ = [
    "BriefingTextGenerator",
    "BriefingVoiceProvider",
    "BriefingVoiceProviderResolver",
    "TextGenerationResult",
]
