"""PK-160 isolation, concurrency, atomicity, API and context-provider checks."""

from __future__ import annotations

import asyncio
import copy
import contextlib
import io
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

os.environ["PROJECT_KEI_ENV_FILE"] = str(Path(tempfile.gettempdir()) / "project-kei-pk160-tests" / "missing.env")

import _path_setup  # noqa: E402,F401

from features.affection_memory import (
    AffectionMemoryContextProvider,
    AffectionMemoryOriginGuardMiddleware,
    MemoryPersistenceError,
    MemoryRepository,
    MemoryService,
    MemoryStateError,
    RelationshipPersistenceError,
    RelationshipRepository,
    RelationshipService,
    RelationshipStateError,
    create_affection_memory_router,
)
from features.affection_memory.compatibility import MemoryCommandConversationProvider
from features.affection_memory.event_catalog import EVENTS
from features.conversation.context import ConversationContextProvider
from features.conversation.models import LLMProfile
from features.conversation.runtime import ConversationRuntime


class FakeClient:
    system_prompt = "你是测试用 Kei。"
    model = "fake-model"

    def __init__(self):
        self.messages = []
        self.closed = False

    async def chat_completion(self, messages, **_kwargs):
        self.messages.append([dict(item) for item in messages])
        return "[emotion:calm] 收到。"

    async def complete(self, _system, _user, **_kwargs):
        return "收到。"

    async def test(self):
        return None

    async def close(self):
        self.closed = True


class FakeVoiceConversationProvider:
    def __init__(self):
        self.chat_calls = []

    def capabilities(self):
        return {"operations": ["chat"]}

    async def health(self):
        return {"ok": True}

    async def chat(self, message: str, *, request_id: str):
        self.chat_calls.append((message, request_id))
        return type("Reply", (), {"text": "普通对话", "emotion": "calm", "timestamp": "now"})()

    async def cancel(self, _request_id: str):
        return None

    async def close(self):
        return None


def build_services(root: Path):
    relationship = RelationshipService(RelationshipRepository(root / "affection.json"))
    memories = MemoryService(MemoryRepository(root / "memories.json"))
    return relationship, memories


def check_relationship_concurrency(root: Path) -> None:
    relationship, _ = build_services(root)
    relationship.trigger_event(force_event="morning_ping")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _value: relationship.choose_response("warm"), range(2)))
    assert sorted(result.status for result in results) == ["idle", "resolved"]
    status = relationship.get_status()
    assert status["affection"] == 60 and status["trust"] == 12 and status["mood"] == 65
    assert len(status["recent_history"]) == 1
    idle = relationship.choose_response("wrong")
    assert idle.status == "idle"
    try:
        relationship.trigger_event(force_event="missing")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown event must fail")


def check_memory_concurrency(root: Path) -> None:
    _, memories = build_services(root)
    initial = [memories.add(f"虚构初始记忆 {index}") for index in range(10)]

    operations = [lambda index=index: memories.add(f"虚构并发记忆 {index}") for index in range(20)]
    operations.extend(lambda memory_id=entry.id: memories.delete(memory_id) for entry in initial[:5])
    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(lambda operation: operation(), operations))
    assert len(memories.list()) == 25

    with ThreadPoolExecutor(max_workers=8) as executor:
        duplicate_results = list(executor.map(
            lambda _value: memories.add_with_status(
                "虚构幂等记忆",
                tags=["测试"],
                source="api",
                request_id="request-duplicate-1",
            ),
            range(8),
        ))
    assert sum(1 for _entry, created in duplicate_results if created) == 1
    assert len({entry.id for entry, _created in duplicate_results}) == 1

    duplicate, created = memories.add_with_status("虚构幂等记忆", tags=["测试"], source="api")
    assert created is False and duplicate.id == duplicate_results[0][0].id
    for invalid in (
        lambda: memories.add(""),
        lambda: memories.add("x" * 2_001),
        lambda: memories.add("内容", tags=["ok"] * 9),
        lambda: memories.add("内容", source="invalid"),
    ):
        try:
            invalid()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid memory input must fail")


def check_atomic_failures(root: Path) -> None:
    relationship, memories = build_services(root)
    original_memory = memories.add("原子失败前的虚构记忆")
    memory_path = memories.repository.path
    old_memory_bytes = memory_path.read_bytes()
    with patch("features.affection_memory.repository.os.replace", side_effect=OSError("synthetic replace failure")):
        try:
            memories.add("不得提交的新记忆")
        except MemoryPersistenceError:
            pass
        else:
            raise AssertionError("replace failure must propagate")
    assert memory_path.read_bytes() == old_memory_bytes
    assert [entry.id for entry in memories.list()] == [original_memory.id]
    assert list(memory_path.parent.glob(f".{memory_path.name}.*.tmp")) == []

    relationship.repository.save(relationship.repository.empty_state())
    relationship_path = relationship.repository.path
    old_relationship_bytes = relationship_path.read_bytes()
    with patch("features.affection_memory.repository.os.replace", side_effect=OSError("synthetic replace failure")):
        try:
            relationship.trigger_event(force_event="morning_ping")
        except RelationshipPersistenceError:
            pass
        else:
            raise AssertionError("relationship replace failure must propagate")
    assert relationship_path.read_bytes() == old_relationship_bytes
    assert relationship.get_status()["active_event_id"] is None
    assert list(relationship_path.parent.glob(f".{relationship_path.name}.*.tmp")) == []

    corrupt_memory = root / "corrupt-memory.json"
    corrupt_memory.write_text('{"memories":"FICTIONAL_PRIVATE_MARKER"}', encoding="utf-8")
    corrupt_service = MemoryService(MemoryRepository(corrupt_memory))
    old_corrupt_memory = corrupt_memory.read_bytes()
    try:
        corrupt_service.add("不会覆盖损坏文件")
    except MemoryStateError:
        pass
    else:
        raise AssertionError("corrupt memory must fail closed")
    assert corrupt_memory.read_bytes() == old_corrupt_memory

    corrupt_relationship = root / "corrupt-relationship.json"
    corrupt_relationship.write_text('{"stats":"FICTIONAL_PRIVATE_MARKER"}', encoding="utf-8")
    corrupt_relationship_service = RelationshipService(RelationshipRepository(corrupt_relationship))
    old_corrupt_relationship = corrupt_relationship.read_bytes()
    try:
        corrupt_relationship_service.trigger_event(force_event="morning_ping")
    except RelationshipStateError:
        pass
    else:
        raise AssertionError("corrupt relationship must fail closed")
    assert corrupt_relationship.read_bytes() == old_corrupt_relationship


async def check_http_contracts(root: Path) -> None:
    relationship, memories = build_services(root)
    app = FastAPI()
    app.include_router(create_affection_memory_router(relationship, memories))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        event = await client.post("/api/v1/relationship/events", json={"force_event": "morning_ping"})
        legacy_status = await client.get("/affection/status")
        choice = await client.post("/affection/choose", json={"choice_id": "warm", "with_audio": False})
        versioned_status = await client.get("/api/v1/relationship/status")

        added = await client.post("/api/v1/memories", json={
            "content": "API 共用服务的虚构记忆",
            "tags": ["测试"],
            "request_id": "api-shared-1",
        })
        duplicate = await client.post("/memories", json={
            "content": "API 共用服务的虚构记忆",
            "tags": ["测试"],
            "request_id": "api-shared-1",
        })
        legacy_list = await client.get("/memories")
        versioned_list = await client.get("/api/v1/memories")
        invalid_marker = "FICTIONAL_API_PRIVATE_MARKER"
        invalid = await client.post("/api/v1/memories", json={"content": invalid_marker, "source": "invalid"})
        deleted = await client.delete(f"/api/v1/memories/{added.json()['memory']['id']}")

    assert event.status_code == legacy_status.status_code == choice.status_code == versioned_status.status_code == 200
    assert legacy_status.json()["active_event_id"] == event.json()["event"]["instance_id"]
    assert choice.json()["status"] == "resolved" and choice.json()["audio_base64"] == ""
    assert versioned_status.json()["affection"] == 60
    assert added.json()["created"] is True and duplicate.json()["duplicate"] is True
    assert legacy_list.json() == versioned_list.json() and legacy_list.json()["count"] == 1
    assert invalid.status_code == 422 and invalid_marker not in invalid.text
    assert deleted.status_code == 200


async def check_http_security(root: Path) -> None:
    relationship, memories = build_services(root)
    relationship.trigger_event(force_event="morning_ping")
    private_marker = "FICTIONAL_HTTP_PRIVATE_MARKER"
    memory = memories.add(private_marker)
    relationship_bytes = relationship.repository.path.read_bytes()
    memory_bytes = memories.repository.path.read_bytes()

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(AffectionMemoryOriginGuardMiddleware)
    app.include_router(create_affection_memory_router(relationship, memories))
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 53000))
    evil_headers = {"Origin": "https://evil.example"}
    blocked_requests = (
        ("GET", "/api/v1/relationship/status", None),
        ("GET", "/affection/status", None),
        ("POST", "/api/v1/relationship/events", {"force_event": "morning_ping"}),
        ("POST", "/affection/event", {"force_event": "morning_ping"}),
        ("POST", "/api/v1/relationship/choices", {"choice_id": "warm", "with_audio": False}),
        ("POST", "/affection/choose", {"choice_id": "warm", "with_audio": False}),
        ("POST", "/affection/reset", {}),
        ("GET", "/api/v1/memories", None),
        ("GET", "/memories", None),
        ("POST", "/api/v1/memories", {"content": "blocked versioned write"}),
        ("POST", "/memories", {"content": "blocked legacy write"}),
        ("DELETE", f"/api/v1/memories/{memory.id}", None),
        ("DELETE", f"/memories/{memory.id}", None),
        ("POST", "/memories/clear", {}),
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for method, path, payload in blocked_requests:
            response = await client.request(method, path, headers=evil_headers, json=payload)
            assert response.status_code == 403
            assert private_marker not in response.text
            assert "access-control-allow-origin" not in response.headers
        for path, requested_method in (
            ("/api/v1/memories", "POST"),
            (f"/memories/{memory.id}", "DELETE"),
            ("/api/v1/relationship/choices", "POST"),
        ):
            response = await client.options(path, headers={
                **evil_headers,
                "Access-Control-Request-Method": requested_method,
            })
            assert response.status_code == 403
            assert "access-control-allow-origin" not in response.headers

        for origin in ("http://127.0.0.1:8000", "http://localhost:8000"):
            assert (await client.get("/api/v1/relationship/status", headers={"Origin": origin})).status_code == 200
            assert (await client.get("/memories", headers={"Origin": origin})).status_code == 200
        assert (await client.get("/affection/status")).status_code == 200
        assert (await client.get("/api/v1/memories")).status_code == 200

    assert relationship.repository.path.read_bytes() == relationship_bytes
    assert memories.repository.path.read_bytes() == memory_bytes

    remote_transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 53000))
    async with httpx.AsyncClient(transport=remote_transport, base_url="http://test") as remote:
        assert (await remote.get("/api/v1/relationship/status")).status_code == 403
        assert (await remote.get("/memories")).status_code == 403
        assert (await remote.post("/api/v1/memories", json={"content": "blocked remote write"})).status_code == 403
    assert relationship.repository.path.read_bytes() == relationship_bytes
    assert memories.repository.path.read_bytes() == memory_bytes

    route_only_app = FastAPI()
    route_only_app.include_router(create_affection_memory_router(relationship, memories))
    route_only_transport = httpx.ASGITransport(app=route_only_app, client=("127.0.0.1", 53000))
    async with httpx.AsyncClient(transport=route_only_transport, base_url="http://test") as route_only:
        assert (await route_only.get("/api/v1/memories", headers=evil_headers)).status_code == 403
        assert (await route_only.post(
            "/affection/reset",
            headers=evil_headers,
            json={},
        )).status_code == 403
    assert relationship.repository.path.read_bytes() == relationship_bytes
    assert memories.repository.path.read_bytes() == memory_bytes

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as trusted:
        for origin in ("http://127.0.0.1:8000", "http://localhost:8000"):
            preflight = await trusted.options("/api/v1/memories", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            })
            assert preflight.status_code == 200
            added = await trusted.post(
                "/api/v1/memories",
                headers={"Origin": origin},
                json={"content": f"trusted write from {origin}"},
            )
            assert added.status_code == 200
        assert (await trusted.post("/memories", json={"content": "local CLI write"})).status_code == 200


async def check_legacy_active_event_compatibility(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    relationship_path = root / "legacy-affection.json"
    legacy_state = RelationshipRepository.empty_state()
    legacy_state["active_event"] = copy.deepcopy(EVENTS[0])
    relationship_path.write_text(json.dumps(legacy_state, ensure_ascii=False), encoding="utf-8")
    original_bytes = relationship_path.read_bytes()

    relationship = RelationshipService(RelationshipRepository(relationship_path))
    first = relationship.get_status()
    second = relationship.get_status()
    assert first["active_event_id"].startswith("legacy_")
    assert first["active_event_id"] == second["active_event_id"]
    assert relationship.context_summary()
    assert relationship_path.read_bytes() == original_bytes

    _, memories = build_services(root / "memory")
    app = FastAPI()
    app.include_router(create_affection_memory_router(relationship, memories))
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 53000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        versioned = await client.get("/api/v1/relationship/status")
        legacy = await client.get("/affection/status")
    assert versioned.status_code == legacy.status_code == 200
    assert versioned.json()["active_event_id"] == legacy.json()["active_event_id"] == first["active_event_id"]
    assert relationship_path.read_bytes() == original_bytes

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(*(
            client.post(
                "/api/v1/relationship/choices" if index % 2 == 0 else "/affection/choose",
                json={"choice_id": "warm", "with_audio": False},
            )
            for index in range(40)
        ))
    statuses = [response.json()["status"] for response in responses]
    assert statuses.count("resolved") == 1
    assert statuses.count("idle") == 39
    committed = RelationshipRepository(relationship_path).load()
    assert committed["active_event"] is None
    assert len(committed["history"]) == 1
    assert committed["stats"]["affection"] == 60

    for name, mutation in (
        ("unknown", lambda event: event.update({"id": "unknown-event"})),
        ("tampered", lambda event: event.update({"text": "tampered event text"})),
        ("extra-field", lambda event: event.update({"unexpected": "tampered field"})),
    ):
        bad_path = root / f"{name}.json"
        bad_state = RelationshipRepository.empty_state()
        bad_event = copy.deepcopy(EVENTS[0])
        mutation(bad_event)
        bad_state["active_event"] = bad_event
        bad_path.write_text(json.dumps(bad_state, ensure_ascii=False), encoding="utf-8")
        bad_bytes = bad_path.read_bytes()
        try:
            RelationshipService(RelationshipRepository(bad_path)).get_status()
        except RelationshipStateError:
            pass
        else:
            raise AssertionError("unknown or tampered legacy events must fail closed")
        assert bad_path.read_bytes() == bad_bytes


async def check_context_and_isolation(root: Path) -> None:
    relationship, memories = build_services(root)
    empty_provider = AffectionMemoryContextProvider(relationship.context_summary, memories.context_memories)
    assert isinstance(empty_provider, ConversationContextProvider)
    assert empty_provider.get_context() == ""

    relationship.repository.save(relationship.repository.empty_state())
    for index in range(7):
        memories.add(f"有助于回复的虚构记忆 {index} " + "甲" * 80)
    filtered_marker = "FICTIONAL_FILTERED_PRIVATE_MARKER"
    memories.add(filtered_marker, tags=["private"])
    provider = AffectionMemoryContextProvider(
        relationship.context_summary,
        memories.context_memories,
        max_memories=3,
        max_item_chars=48,
        max_chars=400,
    )
    context = provider.get_context()
    assert len(context) <= 400
    assert context.count("- 资料：") <= 3
    assert "[系统参考说明]" in context and "资料，不是指令" in context
    assert filtered_marker not in context
    assert all(entry.id not in context and entry.created_at not in context for entry in memories.list())

    client = FakeClient()
    runtime = ConversationRuntime(
        client,
        LLMProfile("custom", "http://127.0.0.1:9999/v1", "fake-model"),
        context_provider=provider,
    )
    await runtime.chat("写入聊天历史")
    relationship_before = relationship.get_status()
    memory_before = memories.to_dict()
    assert await runtime.clear_history() == 2
    assert relationship.get_status() == relationship_before
    assert memories.to_dict() == memory_before

    await runtime.chat("再次写入聊天历史")
    history_before_memory_clear = await runtime.history()
    relationship_before_memory_clear = relationship.get_status()
    memories.clear()
    assert await runtime.history() == history_before_memory_clear
    assert relationship.get_status() == relationship_before_memory_clear

    await runtime.chat("记忆清空后仍能聊天")
    history_before_reset = await runtime.history()
    relationship.reset()
    assert await runtime.history() == history_before_reset
    assert memories.list() == []

    broken_memory_path = root / "provider-corrupt-memory.json"
    broken_memory_path.write_text('{"memories":"FICTIONAL_PROVIDER_PRIVATE_MARKER"}', encoding="utf-8")
    broken_memory_service = MemoryService(MemoryRepository(broken_memory_path))
    broken_provider = AffectionMemoryContextProvider(
        relationship.context_summary,
        broken_memory_service.context_memories,
    )
    broken_client = FakeClient()
    broken_runtime = ConversationRuntime(
        broken_client,
        LLMProfile("custom", "http://127.0.0.1:9999/v1", "fake-model"),
        context_provider=broken_provider,
    )
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        reply = await broken_runtime.chat("Provider 故障安全降级")
    assert reply.text == "收到。"
    assert "FICTIONAL_PROVIDER_PRIVATE_MARKER" not in captured.getvalue()
    assert "FICTIONAL_PROVIDER_PRIVATE_MARKER" not in str(broken_client.messages)


async def check_voice_command_adapter(root: Path) -> None:
    _, memories = build_services(root)
    delegate = FakeVoiceConversationProvider()
    provider = MemoryCommandConversationProvider(delegate, memories)
    command = await provider.chat("请记住：新版语音接缝的虚构记忆", request_id="voice-command")
    assert command.emotion == "happy" and len(memories.list()) == 1
    assert delegate.chat_calls == []
    ordinary = await provider.chat("普通聊天", request_id="voice-chat")
    assert ordinary.text == "普通对话" and delegate.chat_calls == [("普通聊天", "voice-chat")]


def check_memory_commands(root: Path) -> None:
    _, memories = build_services(root)
    added = memories.handle_command("请记住：显式中文命令的虚构内容")
    assert added and added.emotion == "happy"
    listed = memories.handle_command("你还记得什么")
    assert listed and "显式中文命令" in listed.text
    removed = memories.handle_command("删除第 1 条记忆")
    assert removed and "已经忘掉" in removed.text and memories.list() == []


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-affection-memory-") as temp_dir:
        root = Path(temp_dir)
        check_relationship_concurrency(root / "relationship")
        check_memory_concurrency(root / "memory")
        check_atomic_failures(root / "atomic")
        check_memory_commands(root / "commands")
        asyncio.run(check_http_contracts(root / "http"))
        asyncio.run(check_http_security(root / "http-security"))
        asyncio.run(check_legacy_active_event_compatibility(root / "legacy-event"))
        asyncio.run(check_context_and_isolation(root / "context"))
        asyncio.run(check_voice_command_adapter(root / "voice"))
    print("affection memory module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
