"""Internal provider contracts; credentials never cross this boundary."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol, Sequence

from ..models import LLMProfile


class LLMUpstreamError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ConversationClient(Protocol):
    model: str
    system_prompt: str

    async def chat_completion(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        presence_penalty: float | None = None,
    ) -> str:
        ...

    async def complete(
        self,
        system_prompt: str,
        user_input: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.6,
    ) -> str:
        ...

    async def test(self) -> None:
        ...

    async def close(self) -> None:
        ...


ConversationClientFactory = Callable[[LLMProfile], ConversationClient]
