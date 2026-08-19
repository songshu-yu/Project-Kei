"""Concurrency boundary for chat history and the active provider client."""

from __future__ import annotations

import asyncio
from typing import Sequence

from .client import LLMEngine
from .context import ConversationContextProvider, EmptyConversationContextProvider
from .locks import LazyAsyncLock
from .models import ChatMessage, ConversationReply, LLMProfile, TextGenerationResult
from .provider.contracts import ConversationClient, LLMUpstreamError
from .repository import LLMProfileRepository


CHAT_FALLBACK = "呜……网络好像出了点问题，老师等一下再试试？"


class ConversationClosedError(RuntimeError):
    """Raised when work is submitted after the runtime entered its terminal state."""

    def __init__(self):
        super().__init__("对话服务已关闭")


class ConversationRuntime:
    def __init__(
        self,
        client: ConversationClient,
        profile: LLMProfile,
        *,
        context_provider: ConversationContextProvider | None = None,
        max_history: int = 20,
    ):
        self._client = client
        self._profile = profile
        self._context_provider = context_provider or EmptyConversationContextProvider()
        self._max_history = max(1, min(int(max_history), 100))
        self._history: list[ChatMessage] = []
        self._operation_lock = LazyAsyncLock()
        self._closed = False
        self._close_task: asyncio.Task | None = None
        self._system_prompt = client.system_prompt

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def max_history(self) -> int:
        return self._max_history

    def _safe_context(self) -> str:
        try:
            value = self._context_provider.get_context()
            return value.strip() if isinstance(value, str) else ""
        except Exception:
            print("[Conversation] context provider failed; continuing without context")
            return ""

    def _ensure_open(self) -> None:
        if self._closed:
            raise ConversationClosedError()

    def _messages(self, user_input: str) -> list[dict[str, str]]:
        system_prompt = self._client.system_prompt
        context = self._safe_context()
        if context:
            system_prompt = f"{system_prompt}\n\n{context}"
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(
            {"role": item.role, "content": item.content}
            for item in self._history[-(self._max_history * 2):]
        )
        messages.append({"role": "user", "content": user_input})
        return messages

    async def chat(self, user_input: str) -> ConversationReply:
        async with self._operation_lock:
            self._ensure_open()
            messages = self._messages(user_input)
            try:
                raw = await self._client.chat_completion(
                    messages,
                    max_tokens=256,
                    temperature=0.8,
                    presence_penalty=0.6,
                )
                emotion, clean = LLMEngine.parse_emotion(raw)
                if not clean:
                    clean = CHAT_FALLBACK
                    emotion = "sad"
            except Exception:
                clean = CHAT_FALLBACK
                emotion = "sad"

            user_message = ChatMessage(role="user", content=user_input)
            assistant_message = ChatMessage(
                role="assistant",
                content=clean,
                emotion=emotion,
            )
            self._history.extend((user_message, assistant_message))
            limit = self._max_history * 2
            if len(self._history) > limit:
                del self._history[:-limit]
            return ConversationReply(
                text=clean,
                emotion=emotion,
                timestamp=assistant_message.timestamp,
            )

    async def generate_text(
        self,
        system_instruction: str,
        user_input: str,
        *,
        max_tokens: int,
        temperature: float,
        fallback: str,
    ) -> TextGenerationResult:
        async with self._operation_lock:
            self._ensure_open()
            model = self._client.model
            try:
                text = await self._client.complete(
                    system_instruction,
                    user_input,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if not text.strip():
                    raise LLMUpstreamError("empty_response", "模型服务返回了空回复")
                return TextGenerationResult(
                    text=text.strip(),
                    generated=True,
                    fallback=False,
                    model=model,
                )
            except LLMUpstreamError as exc:
                code = exc.code
            except Exception:
                code = "generation_failed"
            return TextGenerationResult(
                text=fallback,
                generated=False,
                fallback=True,
                model=model,
                error_code=code,
            )

    async def get_profile(self) -> LLMProfile:
        async with self._operation_lock:
            return self._profile

    async def history(self, *, limit: int | None = None) -> list[ChatMessage]:
        async with self._operation_lock:
            values: Sequence[ChatMessage] = self._history
            if limit is not None:
                values = values[-max(0, limit):]
            return list(values)

    async def clear_history(self) -> int:
        async with self._operation_lock:
            self._ensure_open()
            count = len(self._history)
            self._history.clear()
            return count

    async def probe(self) -> None:
        async with self._operation_lock:
            self._ensure_open()
            await self._client.test()

    async def commit(
        self,
        candidate: ConversationClient,
        profile: LLMProfile,
        repository: LLMProfileRepository,
    ) -> tuple[ConversationClient, LLMProfile]:
        async with self._operation_lock:
            self._ensure_open()
            saved = repository.save(profile)
            previous = self._client
            self._client = candidate
            self._profile = saved
            return previous, saved

    async def close(self) -> None:
        async with self._operation_lock:
            if not self._closed:
                self._closed = True
                self._close_task = asyncio.create_task(self._client.close())
            close_task = self._close_task
        if close_task is not None:
            await asyncio.shield(close_task)


__all__ = [
    "CHAT_FALLBACK",
    "ConversationClosedError",
    "ConversationRuntime",
]
