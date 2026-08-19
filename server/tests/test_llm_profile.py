"""Isolated LLM profile, upstream failure and hot-switch checks."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx

TEST_LOCAL_ROOT = Path(tempfile.gettempdir()) / "project-kei-pk200-tests"
os.environ["PROJECT_KEI_ENV_FILE"] = str(TEST_LOCAL_ROOT / "missing.env")
os.environ["PROJECT_KEI_LLM_PROFILE_PATH"] = str(TEST_LOCAL_ROOT / "missing-profile.json")
os.environ["LLM_API_KEY"] = "test-key"

import _path_setup  # noqa: E402,F401

from features.conversation.client import LLMEngine
from features.conversation.models import LLMProfile
from features.conversation.provider.contracts import LLMUpstreamError
from features.conversation.repository import (
    LLMProfileRepository,
    ProfilePersistenceError,
    ProfileValidationError,
    normalize_profile,
)
from features.conversation.runtime import ConversationClosedError, ConversationRuntime
from features.conversation.service import ConversationService, ProfileApplyError


class FakeClient:
    system_prompt = "测试角色"

    def __init__(self, model: str, *, raw: str | None = None, test_error: Exception | None = None, close_error: bool = False):
        self.model = model
        self.raw = raw or f"[emotion:calm] {model}"
        self.test_error = test_error
        self.close_error = close_error
        self.closed = False
        self.close_calls = 0
        self.test_calls = 0
        self.chat_calls = 0
        self.complete_calls = 0

    async def chat_completion(self, _messages, **_kwargs) -> str:
        assert not self.closed
        self.chat_calls += 1
        return self.raw

    async def complete(self, _system: str, _user: str, **_kwargs) -> str:
        assert not self.closed
        self.complete_calls += 1
        return self.raw

    async def test(self) -> None:
        self.test_calls += 1
        if self.test_error:
            raise self.test_error

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True
        if self.close_error:
            raise RuntimeError("close details must stay private")


class BlockingClient(FakeClient):
    def __init__(self, model: str):
        super().__init__(model)
        self.test_started = asyncio.Event()
        self.test_release = asyncio.Event()

    async def test(self) -> None:
        self.test_calls += 1
        self.test_started.set()
        await self.test_release.wait()


class BlockingCloseClient(FakeClient):
    def __init__(self, model: str):
        super().__init__(model)
        self.close_started = asyncio.Event()
        self.close_release = asyncio.Event()
        self.calls_after_close = 0

    async def chat_completion(self, messages, **kwargs) -> str:
        if self.closed:
            self.calls_after_close += 1
        return await super().chat_completion(messages, **kwargs)

    async def complete(self, system: str, user: str, **kwargs) -> str:
        if self.closed:
            self.calls_after_close += 1
        return await super().complete(system, user, **kwargs)

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True
        self.close_started.set()
        await self.close_release.wait()


class BlockingChatClient(FakeClient):
    def __init__(self, model: str):
        super().__init__(model)
        self.chat_started = asyncio.Event()
        self.chat_release = asyncio.Event()

    async def chat_completion(self, _messages, **_kwargs) -> str:
        assert not self.closed
        self.chat_calls += 1
        self.chat_started.set()
        await self.chat_release.wait()
        assert not self.closed
        return self.raw


class FailingRepository:
    def save(self, _profile):
        raise ProfilePersistenceError("private filesystem detail")


def profile(model: str, provider: str = "custom") -> LLMProfile:
    return LLMProfile(provider, "http://127.0.0.1:9999/v1", model)


def build_service(repository, active: FakeClient, factory) -> ConversationService:
    runtime = ConversationRuntime(active, profile(active.model), max_history=4)
    return ConversationService(runtime, repository, factory)


def check_normalization_and_repository() -> None:
    custom = normalize_profile({
        "provider": "custom",
        "base_url": "http://127.0.0.1:11434/v1/",
        "model": "local-model",
        "thinking_mode": "enabled",
    })
    assert custom.base_url == "http://127.0.0.1:11434/v1"
    assert custom.thinking_mode == "disabled"

    invalid_values = [
        {"provider": "other", "base_url": "https://example.com/v1", "model": "m"},
        {"provider": "custom", "base_url": "ftp://example.com/v1", "model": "m"},
        {"provider": "custom", "base_url": "https://user:pass@example.com/v1", "model": "m"},
        {"provider": "custom", "base_url": "https://example.com/v1?api_key=secret", "model": "m"},
        {"provider": "custom", "base_url": "https://example.com/v1#secret", "model": "m"},
        {"provider": "custom", "base_url": "https://example.com/v1", "model": ""},
        {"provider": "custom", "base_url": ["https://example.com/v1"], "model": "m"},
        {"provider": "custom", "base_url": "https://example.com/v1", "model": ["m"]},
        {"provider": "custom", "base_url": "https://example.com/v1", "model": "m", "api_key": "secret"},
        {"provider": "custom", "base_url": "https://example.com/v1", "model": "m", "updated_at": "not-a-time"},
    ]
    for value in invalid_values:
        try:
            normalize_profile(value)
        except ProfileValidationError:
            pass
        else:
            raise AssertionError(f"invalid profile accepted: {value!r}")

    with tempfile.TemporaryDirectory(prefix="kei-profile-repository-") as temp_dir:
        root = Path(temp_dir)
        path = root / "profile.json"
        fallback = profile("fallback")
        path.write_text("{broken", encoding="utf-8")
        repository = LLMProfileRepository(path)
        assert repository.load(fallback) == fallback
        assert path.read_text(encoding="utf-8") == "{broken"

        saved = repository.save(custom)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert set(payload) == {"provider", "base_url", "model", "thinking_mode", "updated_at"}
        assert saved.updated_at and "api_key" not in payload

        original = path.read_text(encoding="utf-8")
        failing = LLMProfileRepository(path, replace=lambda _source, _target: (_ for _ in ()).throw(OSError("denied")))
        try:
            failing.save(profile("not-saved"))
        except ProfilePersistenceError:
            pass
        else:
            raise AssertionError("replace failure should fail")
        assert path.read_text(encoding="utf-8") == original
        assert not list(root.glob("*.tmp")) and not list(root.glob(".*.tmp"))


async def check_http_failures() -> None:
    cases = [
        (lambda _request: httpx.Response(401, json={"secret": "body"}), "authentication_failed"),
        (lambda _request: httpx.Response(403, json={"secret": "body"}), "authentication_failed"),
        (lambda _request: httpx.Response(429, json={"secret": "body"}), "rate_limited"),
        (lambda _request: httpx.Response(503, text="upstream-secret"), "upstream_unavailable"),
        (lambda _request: httpx.Response(200, text="not-json"), "invalid_json"),
        (lambda _request: httpx.Response(200, json={"object": "chat.completion"}), "missing_choices"),
        (lambda _request: httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}), "empty_response"),
    ]
    for handler, expected in cases:
        engine = LLMEngine(
            "test-secret-key",
            base_url="https://example.invalid/v1",
            model="fake",
            transport=httpx.MockTransport(handler),
        )
        try:
            await engine.test()
        except LLMUpstreamError as exc:
            assert exc.code == expected
            assert "secret" not in str(exc).lower()
        else:
            raise AssertionError(f"expected {expected}")
        finally:
            await engine.close()

    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("private timeout", request=request)

    def connect_handler(request: httpx.Request):
        raise httpx.ConnectError("private dns", request=request)

    for handler, expected in ((timeout_handler, "timeout"), (connect_handler, "connection_failed")):
        engine = LLMEngine(
            "test-secret-key",
            base_url="https://example.invalid/v1",
            model="fake",
            transport=httpx.MockTransport(handler),
        )
        try:
            await engine.test()
        except LLMUpstreamError as exc:
            assert exc.code == expected and "private" not in str(exc)
        finally:
            await engine.close()


async def check_switching() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-profile-switch-") as temp_dir:
        repository = LLMProfileRepository(Path(temp_dir) / "profile.json")

        old = FakeClient("old")
        failed = FakeClient("failed", test_error=LLMUpstreamError("rate_limited", "private response"))
        service = build_service(repository, old, lambda _value: failed)
        await service.chat("保留的历史")
        before_profile = await service.get_profile()
        before_history = await service.history()
        try:
            await service.update_profile(profile("failed").to_dict())
        except ProfileApplyError as exc:
            assert exc.stage == "test" and exc.code == "rate_limited"
            assert "private" not in str(exc)
        else:
            raise AssertionError("failed candidate should not switch")
        assert await service.get_profile() == before_profile
        assert await service.history() == before_history
        assert failed.closed and not old.closed

        unsaved = FakeClient("unsaved")
        unsaved_service = build_service(FailingRepository(), old, lambda _value: unsaved)
        try:
            await unsaved_service.update_profile(profile("unsaved").to_dict())
        except ProfileApplyError as exc:
            assert exc.stage == "save" and "private" not in str(exc)
        else:
            raise AssertionError("save failure should not switch")
        assert unsaved.closed and (await unsaved_service.get_profile()).model == "old"

        previous = FakeClient("old-close-warning", close_error=True)
        candidate = FakeClient("new")
        successful = build_service(repository, previous, lambda _value: candidate)
        await successful.chat("切换前")
        updated = await successful.update_profile(profile("new").to_dict())
        assert updated.model == "new" and previous.closed
        assert len(await successful.history()) == 2
        generated = await successful.generate_text("受控指令", "消费者输入", fallback="fallback")
        assert generated.generated and generated.model == "new"


async def check_concurrency() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-profile-concurrency-") as temp_dir:
        repository = LLMProfileRepository(Path(temp_dir) / "profile.json")
        old = FakeClient("old", raw="[emotion:calm] old reply")
        candidate = BlockingClient("new")
        service = build_service(repository, old, lambda _value: candidate)

        update = asyncio.create_task(service.update_profile(profile("new").to_dict()))
        await candidate.test_started.wait()
        during = await service.chat("候选测试期间")
        assert during.text == "old reply" and not old.closed
        candidate.test_release.set()
        await update
        after = await service.chat("切换以后")
        assert after.text == "new" and old.closed

        active = FakeClient("base")
        first = BlockingClient("first")
        second = FakeClient("second")
        clients = iter((first, second))
        serialized = build_service(repository, active, lambda _value: next(clients))
        first_update = asyncio.create_task(serialized.update_profile(profile("first").to_dict()))
        await first.test_started.wait()
        second_update = asyncio.create_task(serialized.update_profile(profile("second").to_dict()))
        await asyncio.sleep(0)
        assert second.test_calls == 0
        first.test_release.set()
        await asyncio.gather(first_update, second_update)
        assert (await serialized.get_profile()).model == "second"
        assert active.closed and first.closed and not second.closed


async def check_shutdown_races() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-profile-shutdown-") as temp_dir:
        root = Path(temp_dir)

        blocking_close = BlockingCloseClient("runtime-old")
        runtime = ConversationRuntime(blocking_close, profile("runtime-old"))
        first_close = asyncio.create_task(runtime.close())
        await blocking_close.close_started.wait()
        second_close = asyncio.create_task(runtime.close())
        await asyncio.sleep(0)
        assert blocking_close.close_calls == 1

        try:
            await runtime.chat("关闭后聊天")
        except ConversationClosedError:
            pass
        else:
            raise AssertionError("closed runtime accepted chat")
        try:
            await runtime.generate_text(
                "受控指令",
                "关闭后生成",
                max_tokens=32,
                temperature=0.2,
                fallback="fallback",
            )
        except ConversationClosedError:
            pass
        else:
            raise AssertionError("closed runtime accepted generation")
        assert blocking_close.calls_after_close == 0
        assert await runtime.history() == []
        blocking_close.close_release.set()
        await asyncio.gather(first_close, second_close)
        assert blocking_close.close_calls == 1

        active_chat = BlockingChatClient("active-chat")
        chat_service = build_service(
            LLMProfileRepository(root / "chat-profile.json"),
            active_chat,
            lambda value: FakeClient(value.model),
        )
        chat_task = asyncio.create_task(chat_service.chat("已进入的请求"))
        await active_chat.chat_started.wait()
        close_task = asyncio.create_task(chat_service.close())
        await asyncio.sleep(0)
        assert not active_chat.closed
        active_chat.chat_release.set()
        reply, _ = await asyncio.gather(chat_task, close_task)
        assert reply.text == "active-chat" and active_chat.close_calls == 1
        history_before = await chat_service.history()
        try:
            await chat_service.chat("关闭后的请求")
        except ConversationClosedError:
            pass
        else:
            raise AssertionError("closed service accepted chat")
        generated = await chat_service.generate_text(
            "受控指令",
            "关闭后的生成",
            fallback="safe fallback",
        )
        assert generated.generated is False
        assert generated.error_code == "service_closed"
        assert generated.text == "safe fallback"
        assert await chat_service.history() == history_before
        await chat_service.close()
        assert active_chat.close_calls == 1

        old = FakeClient("old")
        candidate = BlockingClient("candidate")
        profile_path = root / "blocked-profile.json"
        repository = LLMProfileRepository(profile_path)
        service = build_service(repository, old, lambda _value: candidate)
        update = asyncio.create_task(service.update_profile(profile("candidate").to_dict()))
        await candidate.test_started.wait()
        await service.close()
        assert old.closed and old.close_calls == 1
        assert candidate.closed and candidate.close_calls == 1
        candidate.test_release.set()
        try:
            await update
        except ProfileApplyError as exc:
            assert exc.stage == "lifecycle" and exc.code == "service_closed"
        else:
            raise AssertionError("profile update committed after service close")
        assert candidate.closed and candidate.close_calls == 1
        assert (await service.get_profile()).model == "old"
        assert not profile_path.exists()
        assert await service.history() == []

        factory_calls = 0

        def after_close_factory(value):
            nonlocal factory_calls
            factory_calls += 1
            return FakeClient(value.model)

        rejected = build_service(
            LLMProfileRepository(root / "after-close.json"),
            FakeClient("closed"),
            after_close_factory,
        )
        await rejected.close()
        try:
            await rejected.update_profile(profile("never-created").to_dict())
        except ProfileApplyError as exc:
            assert exc.code == "service_closed"
        else:
            raise AssertionError("closed service accepted profile update")
        assert factory_calls == 0
        assert not (root / "after-close.json").exists()


def main() -> int:
    check_normalization_and_repository()
    asyncio.run(check_http_failures())
    asyncio.run(check_switching())
    asyncio.run(check_concurrency())
    asyncio.run(check_shutdown_races())
    print("LLM profile tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
