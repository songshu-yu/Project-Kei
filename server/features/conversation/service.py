"""Conversation use cases and serialized profile reconfiguration."""

from __future__ import annotations

import asyncio
from typing import Protocol

from .locks import LazyAsyncLock
from .models import (
    ChatMessage,
    ConversationReply,
    LLMProfile,
    TextGenerationResult,
)
from .provider.contracts import ConversationClient, ConversationClientFactory, LLMUpstreamError
from .repository import (
    LLMProfileRepository,
    ProfilePersistenceError,
    ProfileValidationError,
    normalize_profile,
)
from .runtime import ConversationClosedError, ConversationRuntime


class ProfileApplyError(RuntimeError):
    def __init__(self, stage: str, code: str, message: str, *, status_code: int = 502):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.status_code = status_code


class TextGenerator(Protocol):
    @property
    def system_prompt(self) -> str:
        ...

    async def generate_text(
        self,
        system_instruction: str,
        user_input: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.6,
        fallback: str = "",
    ) -> TextGenerationResult:
        ...


class ConversationService:
    def __init__(
        self,
        runtime: ConversationRuntime,
        repository: LLMProfileRepository,
        client_factory: ConversationClientFactory,
    ):
        self._runtime = runtime
        self._repository = repository
        self._client_factory = client_factory
        self._update_lock = LazyAsyncLock()
        self._lifecycle_lock = LazyAsyncLock()
        self._closed = False
        self._candidate: ConversationClient | None = None
        self._candidate_close_tasks: dict[int, asyncio.Task] = {}

    def _ensure_open(self) -> None:
        if self._closed:
            raise ConversationClosedError()

    def _candidate_close_task_locked(self, candidate: ConversationClient) -> asyncio.Task:
        key = id(candidate)
        task = self._candidate_close_tasks.get(key)
        if task is None:
            task = asyncio.create_task(candidate.close())
            self._candidate_close_tasks[key] = task
        if self._candidate is candidate:
            self._candidate = None
        return task

    async def _safe_close_candidate(self, candidate: ConversationClient, label: str) -> None:
        async with self._lifecycle_lock:
            task = self._candidate_close_task_locked(candidate)
        try:
            await asyncio.shield(task)
        except Exception:
            print(f"[Conversation] {label} close warning")

    async def _is_closed(self) -> bool:
        async with self._lifecycle_lock:
            return self._closed

    @property
    def system_prompt(self) -> str:
        return self._runtime.system_prompt

    @property
    def max_history(self) -> int:
        return self._runtime.max_history

    async def chat(self, message: str) -> ConversationReply:
        value = str(message or "").strip()
        if not value:
            raise ValueError("消息不能为空")
        if len(value) > 20_000:
            raise ValueError("消息长度不能超过 20000")
        async with self._lifecycle_lock:
            self._ensure_open()
            return await self._runtime.chat(value)

    async def history(self, *, limit: int | None = None) -> list[ChatMessage]:
        return await self._runtime.history(limit=limit)

    async def clear_history(self) -> int:
        async with self._lifecycle_lock:
            self._ensure_open()
            return await self._runtime.clear_history()

    async def generate_text(
        self,
        system_instruction: str,
        user_input: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.6,
        fallback: str = "",
    ) -> TextGenerationResult:
        system = str(system_instruction or "").strip()
        user = str(user_input or "").strip()
        try:
            bounded_tokens = int(max_tokens)
            bounded_temperature = float(temperature)
        except (TypeError, ValueError):
            bounded_tokens = 0
            bounded_temperature = -1
        if (
            not system
            or len(system) > 40_000
            or not user
            or len(user) > 100_000
            or not 1 <= bounded_tokens <= 4096
            or not 0 <= bounded_temperature <= 2
        ):
            active = await self.get_profile()
            return TextGenerationResult(
                text=str(fallback or ""),
                generated=False,
                fallback=True,
                model=active.model,
                error_code="invalid_generation_request",
            )
        async with self._lifecycle_lock:
            if self._closed:
                active = await self._runtime.get_profile()
                return TextGenerationResult(
                    text=str(fallback or ""),
                    generated=False,
                    fallback=True,
                    model=active.model,
                    error_code="service_closed",
                )
            return await self._runtime.generate_text(
                system,
                user,
                max_tokens=bounded_tokens,
                temperature=bounded_temperature,
                fallback=str(fallback or ""),
            )

    async def get_profile(self) -> LLMProfile:
        return await self._runtime.get_profile()

    async def probe_active(self) -> tuple[bool, str | None]:
        async with self._lifecycle_lock:
            if self._closed:
                return False, "service_closed"
            try:
                await self._runtime.probe()
                return True, None
            except LLMUpstreamError as exc:
                return False, exc.code
            except ConversationClosedError:
                return False, "service_closed"
            except Exception:
                return False, "probe_failed"

    async def update_profile(self, value: object) -> LLMProfile:
        profile = normalize_profile(value, updated_at=None)
        async with self._update_lock:
            candidate: ConversationClient | None = None
            try:
                async with self._lifecycle_lock:
                    self._ensure_open()
                    candidate = self._client_factory(profile)
                    self._candidate = candidate
                await candidate.test()
            except ConversationClosedError as exc:
                if candidate is not None:
                    await self._safe_close_candidate(candidate, "closed candidate")
                raise ProfileApplyError(
                    "lifecycle",
                    "service_closed",
                    "对话服务已关闭",
                    status_code=503,
                ) from exc
            except asyncio.CancelledError:
                if candidate is not None:
                    await self._safe_close_candidate(candidate, "cancelled candidate")
                raise
            except LLMUpstreamError as exc:
                if candidate is not None:
                    await self._safe_close_candidate(candidate, "failed candidate")
                if await self._is_closed():
                    raise ProfileApplyError(
                        "lifecycle",
                        "service_closed",
                        "对话服务已关闭",
                        status_code=503,
                    ) from exc
                raise ProfileApplyError(
                    "test",
                    exc.code,
                    "候选模型测试失败",
                    status_code=502,
                ) from exc
            except Exception as exc:
                if candidate is not None:
                    await self._safe_close_candidate(candidate, "failed candidate")
                if await self._is_closed():
                    raise ProfileApplyError(
                        "lifecycle",
                        "service_closed",
                        "对话服务已关闭",
                        status_code=503,
                    ) from exc
                raise ProfileApplyError(
                    "test",
                    "candidate_failed",
                    "候选模型测试失败",
                    status_code=502,
                ) from exc

            try:
                async with self._lifecycle_lock:
                    self._ensure_open()
                    previous, saved = await self._runtime.commit(
                        candidate,
                        profile,
                        self._repository,
                    )
                    self._candidate = None
            except ConversationClosedError as exc:
                await self._safe_close_candidate(candidate, "closed candidate")
                raise ProfileApplyError(
                    "lifecycle",
                    "service_closed",
                    "对话服务已关闭，候选方案未应用",
                    status_code=503,
                ) from exc
            except asyncio.CancelledError:
                await self._safe_close_candidate(candidate, "cancelled candidate")
                raise
            except (ProfilePersistenceError, OSError) as exc:
                await self._safe_close_candidate(candidate, "unsaved candidate")
                raise ProfileApplyError(
                    "save",
                    "profile_save_failed",
                    "模型方案保存失败，原方案保持不变",
                    status_code=500,
                ) from exc
            except Exception as exc:
                await self._safe_close_candidate(candidate, "uncommitted candidate")
                raise ProfileApplyError(
                    "commit",
                    "profile_commit_failed",
                    "模型方案未能应用，原方案保持不变",
                    status_code=500,
                ) from exc

            await self._safe_close(previous, "previous client")
            return saved

    @staticmethod
    async def _safe_close(client: ConversationClient, label: str) -> None:
        try:
            await client.close()
        except Exception:
            print(f"[Conversation] {label} close warning")

    async def close(self) -> None:
        candidate_close_task = None
        async with self._lifecycle_lock:
            self._closed = True
            if self._candidate is not None:
                candidate_close_task = self._candidate_close_task_locked(self._candidate)
            await self._runtime.close()
        if candidate_close_task is not None:
            try:
                await asyncio.shield(candidate_close_task)
            except Exception:
                print("[Conversation] candidate close warning")


__all__ = [
    "ConversationService",
    "ConversationClosedError",
    "ProfileApplyError",
    "ProfileValidationError",
    "TextGenerator",
]
