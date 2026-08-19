"""Isolated conversation runtime and new/legacy HTTP contract checks."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

TEST_LOCAL_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk200-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_LOCAL_ROOT / "missing.env")
os.environ["PROJECT_KEI_LLM_PROFILE_PATH"] = str(TEST_LOCAL_ROOT / "missing-profile.json")
os.environ["LLM_API_KEY"] = "test-key"

import _path_setup  # noqa: E402,F401

from features.conversation.context import EmptyConversationContextProvider
from features.affection_memory import MemoryRepository, MemoryService
from features.conversation.models import LLMProfile
from features.conversation.provider.contracts import LLMUpstreamError
from features.conversation.repository import LLMProfileRepository
from features.conversation.router import create_conversation_router
from features.conversation.runtime import CHAT_FALLBACK, ConversationRuntime
from features.conversation.service import ConversationService


class FakeClient:
    system_prompt = "你是测试用 Kei。"

    def __init__(self, model: str = "fake-model", raw: str = "[emotion:happy] 收到。"):
        self.model = model
        self.raw = raw
        self.failure: Exception | None = None
        self.messages: list[list[dict[str, str]]] = []
        self.closed = False

    async def chat_completion(self, messages, **_kwargs) -> str:
        assert not self.closed
        self.messages.append([dict(item) for item in messages])
        if self.failure:
            raise self.failure
        return self.raw

    async def complete(self, _system: str, _user: str, **_kwargs) -> str:
        assert not self.closed
        if self.failure:
            raise self.failure
        return self.raw

    async def test(self) -> None:
        if self.failure:
            raise self.failure

    async def close(self) -> None:
        self.closed = True


class StaticContext:
    def __init__(self, text: str):
        self.text = text

    def get_context(self) -> str:
        return self.text


class BrokenContext:
    def get_context(self) -> str:
        raise RuntimeError("private-memory-must-not-leak")


def build_service(root: Path, client: FakeClient, *, context=None, max_history: int = 20) -> ConversationService:
    profile = LLMProfile("custom", "http://127.0.0.1:9999/v1", client.model)
    repository = LLMProfileRepository(root / "profile.json")
    runtime = ConversationRuntime(
        client,
        profile,
        context_provider=context or EmptyConversationContextProvider(),
        max_history=max_history,
    )
    return ConversationService(runtime, repository, lambda candidate: FakeClient(model=candidate.model))


async def check_runtime() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-conversation-") as temp_dir:
        root = Path(temp_dir)

        client = FakeClient(raw="[emotion:unknown] 不认识的标签也会清理。")
        service = build_service(root, client, context=StaticContext("只读测试上下文"), max_history=2)
        first = await service.chat("第一条")
        assert first.text == "不认识的标签也会清理。"
        assert first.emotion == "calm"
        assert client.messages[0][0]["role"] == "system"
        assert "只读测试上下文" in client.messages[0][0]["content"]
        assert "[emotion:" not in first.text

        client.raw = "[emotion:happy] 第二条回复"
        await service.chat("第二条")
        await service.chat("第三条")
        history = await service.history()
        assert len(history) == 4
        assert [item.content for item in history] == ["第二条", "第二条回复", "第三条", "第二条回复"]
        assert await service.clear_history() == 4
        assert await service.history() == []

        broken_client = FakeClient()
        broken_service = build_service(root, broken_client, context=BrokenContext())
        reply = await broken_service.chat("上下文故障仍应回复")
        assert reply.text == "收到。"
        assert "private-memory-must-not-leak" not in str(broken_client.messages)

        failed_client = FakeClient()
        failed_client.failure = LLMUpstreamError("timeout", "secret-upstream-body")
        failed_service = build_service(root, failed_client)
        fallback = await failed_service.chat("触发失败")
        assert fallback.text == CHAT_FALLBACK and fallback.emotion == "sad"
        assert "secret-upstream-body" not in fallback.text
        generated = await failed_service.generate_text(
            "受控指令",
            "输入",
            fallback="本地兜底",
        )
        assert generated.text == "本地兜底"
        assert generated.generated is False and generated.fallback is True
        assert generated.error_code == "timeout"
        assert len(await failed_service.history()) == 2

        ordered_client = FakeClient(raw="[emotion:calm] 并发回复")
        ordered_service = build_service(root, ordered_client, max_history=4)
        await asyncio.gather(
            ordered_service.chat("并发一"),
            ordered_service.chat("并发二"),
        )
        ordered = await ordered_service.history()
        assert len(ordered) == 4
        assert all(ordered[index].role == "user" and ordered[index + 1].role == "assistant" for index in (0, 2))


class LegacyChatRequest(BaseModel):
    message: str
    with_audio: bool = True


async def check_http_contracts() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-conversation-api-") as temp_dir:
        service = build_service(Path(temp_dir), FakeClient())
        app = FastAPI()
        app.include_router(create_conversation_router(lambda: service, local_control_guard=lambda _request: True))

        async def legacy_reply(payload: LegacyChatRequest, *, include_audio: bool) -> dict:
            try:
                reply = await service.chat(payload.message)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            result = {"text": reply.text, "emotion": reply.emotion, "timestamp": reply.timestamp}
            if include_audio:
                result["audio_base64"] = ""
            return result

        @app.post("/chat/text-only")
        async def legacy_text(payload: LegacyChatRequest):
            return await legacy_reply(payload, include_audio=False)

        @app.post("/chat")
        async def legacy_chat(payload: LegacyChatRequest):
            return await legacy_reply(payload, include_audio=True)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            versioned = await client.post("/api/v1/conversation", json={"message": "新接口"})
            legacy = await client.post("/chat/text-only", json={"message": "QQ bridge", "with_audio": False})
            audio_legacy = await client.post("/chat", json={"message": "旧音频装配", "with_audio": False})
            history = await client.get("/api/v1/conversation/history")
            cleared = await client.delete("/api/v1/conversation/history")
            empty = await client.post("/api/v1/conversation", json={"message": "   "})

        assert versioned.status_code == legacy.status_code == audio_legacy.status_code == 200
        assert set(versioned.json()) == {"text", "emotion", "timestamp"}
        assert set(legacy.json()) == {"text", "emotion", "timestamp"}
        assert audio_legacy.json()["audio_base64"] == ""
        assert legacy.json()["text"] == versioned.json()["text"] == "收到。"
        assert history.json()["count"] == 6
        assert cleared.json() == {"status": "ok", "cleared": 6}
        assert empty.status_code == 422


async def _legacy_static_application_integration() -> None:
    import api

    with tempfile.TemporaryDirectory(prefix="kei-conversation-app-") as temp_dir:
        service = build_service(Path(temp_dir), FakeClient())
        original_service = api.conversation_service
        original_tts = api.tts
        original_memories = api.memory_service
        api.conversation_service = service
        api.tts = None
        api.memory_service = MemoryService(MemoryRepository(Path(temp_dir) / "memories.json"))
        try:
            transport = httpx.ASGITransport(app=api.app, client=("127.0.0.1", 53000))
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
                versioned = await client.post("/api/v1/conversation", json={"message": "版本化"})
                qq_legacy = await client.post("/chat/text-only", json={"message": "QQ", "with_audio": False})
                memory_command = await client.post(
                    "/chat/text-only",
                    json={"message": "请记住：文字接缝的虚构记忆", "with_audio": False},
                )
                profile_get = await client.get("/api/v1/llm-profile")
                legacy_profile = await client.get("/dashboard/llm/profile")
                same_site = await client.get(
                    "/api/v1/llm-profile",
                    headers={"Origin": "http://127.0.0.1:8000"},
                )
                cross_site = await client.get(
                    "/api/v1/llm-profile",
                    headers={"Origin": "https://attacker.example"},
                )
                secret_value = "must-not-echo-test-secret"
                rejected_secret = await client.put(
                    "/api/v1/llm-profile",
                    json={
                        "provider": "custom",
                        "base_url": "http://127.0.0.1:9999/v1",
                        "model": "fake-model",
                        "thinking_mode": "disabled",
                        "api_key": secret_value,
                    },
                )
                switched = await client.put(
                    "/api/v1/llm-profile",
                    json={
                        "provider": "custom",
                        "base_url": "http://127.0.0.1:9998/v1",
                        "model": "switched-model",
                        "thinking_mode": "enabled",
                    },
                )
                switched_legacy = await client.get("/dashboard/llm/profile")
        finally:
            api.conversation_service = original_service
            api.tts = original_tts
            api.memory_service = original_memories

        assert versioned.status_code == qq_legacy.status_code == 200
        assert versioned.json()["text"] == qq_legacy.json()["text"] == "收到。"
        assert memory_command.status_code == 200 and "我记住了" in memory_command.json()["text"]
        assert profile_get.status_code == legacy_profile.status_code == 200
        assert same_site.status_code == 200
        assert profile_get.json() == legacy_profile.json()
        assert set(profile_get.json()) == {"provider", "base_url", "model", "thinking_mode", "updated_at"}
        assert cross_site.status_code == 403
        assert rejected_secret.status_code == 422
        assert secret_value not in rejected_secret.text
        assert switched.status_code == 200
        assert switched.json()["model"] == "switched-model"
        assert switched.json()["thinking_mode"] == "disabled"
        assert switched_legacy.json() == switched.json()


def main() -> int:
    asyncio.run(check_runtime())
    asyncio.run(check_http_contracts())
    print("conversation module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
