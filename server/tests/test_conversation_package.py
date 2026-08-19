"""Isolated end-to-end checks for the installable conversation package."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient


TEST_API_KEY = "pk200-fake-key-never-real"
os.environ["LLM_API_KEY"] = TEST_API_KEY
os.environ["PROJECT_KEI_ENV_FILE"] = str(
    Path(tempfile.gettempdir()) / "project-kei-pk200-package-missing.env"
)

import _path_setup  # noqa: E402,F401

from core.modules import InProcessModuleLoader, ModuleManager  # noqa: E402
from core.modules.exceptions import (  # noqa: E402
    ModuleConflictError,
    PackageValidationError,
)
from features.conversation import module as conversation_module  # noqa: E402
from features.conversation.context import (  # noqa: E402
    AppStateConversationContextProvider,
    ConversationContextProvider,
)
from features.conversation.models import LLMProfile  # noqa: E402
from features.conversation.package_builder import (  # noqa: E402
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    PACKAGE_SOURCE_FILES,
    build_conversation_package,
    file_sha256,
)
from features.conversation.repository import LLMProfileRepository  # noqa: E402
from features.conversation.runtime import ConversationRuntime  # noqa: E402
from features.conversation.service import ConversationService  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = PROJECT_ROOT / "server" / "features" / "conversation"
RELEASE_FRAGMENT = FEATURE_ROOT / "release" / "official-release-fragment.json"
CATALOG_ENTRY = FEATURE_ROOT / "release" / "official-catalog-entry.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
CATALOG_GENERATED_AT = "2026-07-30T00:00:00Z"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "backend/kei_system.txt",
    *(f"backend/{name}" for name in BACKEND_FILES),
    *PACKAGE_SOURCE_FILES,
}


class FakeClient:
    system_prompt = "你是安装包测试用 Kei。"

    def __init__(self, model: str):
        self.model = model
        self.closed = 0
        self.messages: list[list[dict[str, str]]] = []

    async def chat_completion(self, messages, **_kwargs) -> str:
        assert self.closed == 0
        self.messages.append([dict(item) for item in messages])
        return f"[emotion:calm] chat:{self.model}"

    async def complete(self, _system: str, _user: str, **_kwargs) -> str:
        assert self.closed == 0
        return f"generated:{self.model}"

    async def test(self) -> None:
        assert self.closed == 0

    async def close(self) -> None:
        self.closed += 1


class StaticContext(ConversationContextProvider):
    def __init__(self, value: str = "只读安装包上下文"):
        self.value = value

    def get_context(self) -> str:
        return self.value


class BrokenContext:
    def get_context(self) -> str:
        raise RuntimeError("pk200-private-context-must-not-leak")


class NonStringContext:
    def get_context(self):
        return {"private": "not prompt text"}


class BlockingFakeClient(FakeClient):
    def __init__(
        self,
        model: str,
        entered: asyncio.Event,
        release: asyncio.Event,
        block_call: int = 3,
    ):
        super().__init__(model)
        self.entered = entered
        self.release = release
        self.block_call = block_call

    async def chat_completion(self, messages, **_kwargs) -> str:
        assert self.closed == 0
        self.messages.append([dict(item) for item in messages])
        if len(self.messages) == self.block_call:
            self.entered.set()
            await self.release.wait()
        return f"[emotion:calm] chat:{self.model}"


class FailingCloseService:
    def __init__(self):
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        raise RuntimeError(
            "pk200-fake-key-never-real private-profile-path"
        )


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def make_service(
    profile_path: Path,
    created_clients: list[FakeClient],
    *,
    context: ConversationContextProvider | None = None,
) -> ConversationService:
    repository = LLMProfileRepository(profile_path)
    default = LLMProfile(
        "custom",
        "http://127.0.0.1:9911/v1",
        "package-default",
        "disabled",
    )
    active = repository.load(default)

    def client_factory(profile: LLMProfile) -> FakeClient:
        client = FakeClient(profile.model)
        created_clients.append(client)
        return client

    runtime = ConversationRuntime(
        client_factory(active),
        active,
        context_provider=context,
    )
    return ConversationService(runtime, repository, client_factory)


def restarted_app(
    manager: ModuleManager,
    profile_path: Path,
    created_clients: list[FakeClient],
) -> tuple[FastAPI, list[dict[str, str]]]:
    app = FastAPI()
    app.state.conversation_service_factory = lambda: make_service(
        profile_path,
        created_clients,
        context=StaticContext(),
    )
    app.state.conversation_local_control_guard = lambda _request: True
    app.state.conversation_audio_synthesizer = (
        lambda _text, _emotion: b"fake-audio"
    )
    results = InProcessModuleLoader().load(
        app,
        manager.enabled_in_process_descriptors(),
    )
    manager.record_load_results(results)
    return app, results


async def call(
    app: FastAPI,
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54000))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
    ) as client:
        return await client.request(method, path, **kwargs)


def _assert_package_contents(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert names == EXPECTED_PACKAGE_NAMES
        for info in archive.infolist():
            assert info.date_time == FIXED_ZIP_DATETIME
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.extra == b"" and info.comment == b""
        package_text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in sorted(names)
        )
    assert TEST_API_KEY not in package_text
    assert not re.search(r"(?i)authorization\s*[:=]\s*['\"]?bearer\s+\S+", package_text)
    assert not re.search(r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b", package_text)
    assert not any(
        token in name.casefold()
        for name in names
        for token in (
            ".env",
            "llm_profile",
            "memories",
            "affection",
            "cache",
            "vendor",
            "node_modules",
            "install.ps1",
            "install.bat",
        )
    )


def check_deterministic_package_and_release() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    expected_entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "conversation"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["permissions"] == ["local_state"]
    assert fragment["data_policy"] == "preserve_on_uninstall"
    assert fragment["requires_restart"] is True

    with tempfile.TemporaryDirectory(
        prefix="kei-conversation-deterministic-"
    ) as temp_dir:
        root = Path(temp_dir)
        first = build_conversation_package(root / "first.zip")
        second = build_conversation_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)
        _assert_package_contents(second)
        with zipfile.ZipFile(first) as archive:
            manifest_raw = archive.read("manifest.json")
        assert expected_entry["manifest_sha256"] == hashlib.sha256(
            manifest_raw
        ).hexdigest()
        assert expected_entry["package_size"] == first.stat().st_size
        assert expected_entry["package_sha256"] == file_sha256(first)
        assert expected_entry["package_url"] == (
            "https://github.com/songshu-yu/Project-Kei-Modules/releases/download/"
            f"{OFFICIAL_RELEASE_TAG}/{OFFICIAL_ASSET_NAME}"
        )

        asset_root = root / "assets"
        asset_root.mkdir()
        build_conversation_package(asset_root / OFFICIAL_ASSET_NAME)
        catalog_output = root / "official-catalog.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(CATALOG_BUILDER),
                "--fragment",
                str(RELEASE_FRAGMENT),
                "--asset-root",
                str(asset_root),
                "--output",
                str(catalog_output),
                "--generated-at",
                CATALOG_GENERATED_AT,
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)
        catalog = json.loads(catalog_output.read_text(encoding="utf-8"))
        assert catalog["owner"] == "songshu-yu"
        assert catalog["repository"] == "Project-Kei-Modules"
        assert catalog["modules"] == [expected_entry]

        materialized = build_conversation_package(root / "materialized")
        assert {
            path.relative_to(materialized).as_posix()
            for path in materialized.rglob("*")
            if path.is_file()
        } == EXPECTED_PACKAGE_NAMES
        for path in materialized.rglob("*"):
            if path.is_file():
                assert b"\r\n" not in path.read_bytes()

    dashboard = (
        FEATURE_ROOT / "package_source" / "dashboard" / "index.js"
    ).read_text(encoding="utf-8")
    for element_id in (
        "llm-preset",
        "llm-base-url",
        "llm-model",
        "llm-thinking",
        "apply-llm",
        "llm-status",
    ):
        assert element_id in dashboard
    assert "/api/v1/llm-profile" in dashboard
    assert "localStorage" not in dashboard
    assert "sessionStorage" not in dashboard
    assert "indexedDB" not in dashboard
    assert "api_key" not in dashboard.casefold()


def check_missing_environment_configuration() -> None:
    previous = os.environ.pop("LLM_API_KEY", None)
    try:
        with tempfile.TemporaryDirectory(
            prefix="kei-conversation-configuration-"
        ) as temp_dir:
            root = Path(temp_dir)
            manager = make_manager(root)
            package = build_conversation_package(root / "conversation.zip")
            installed = manager.install(
                package,
                file_sha256(package),
                expected_module_id="conversation",
            )
            assert installed["configuration_ready"] is False
            assert installed["install_status"] == "needs_configuration"
            checked = manager.check_configuration("conversation")
            assert checked["missing_configuration_fields"] == ["llm_api_key"]
            try:
                manager.enable("conversation")
            except ModuleConflictError:
                pass
            else:
                raise AssertionError("conversation enabled without its environment key")
    finally:
        if previous is not None:
            os.environ["LLM_API_KEY"] = previous


async def check_lifecycle_routes_profile_and_fallback() -> None:
    with tempfile.TemporaryDirectory(
        prefix="kei-conversation-lifecycle-"
    ) as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_conversation_package(root / OFFICIAL_ASSET_NAME)
        digest = file_sha256(package)
        installed = manager.install(
            package,
            digest,
            expected_module_id="conversation",
        )
        assert installed["install_status"] == "installed_disabled"
        assert installed["configuration_ready"] is True
        enabled = manager.enable("conversation")
        assert enabled["enabled"] is True
        assert enabled["restart_required"] is True

        profile_path = root / "state" / "llm_profile.json"
        clients: list[FakeClient] = []
        app, results = restarted_app(manager, profile_path, clients)
        assert results == [{"module_id": "conversation", "status": "loaded"}], results
        route_keys = [
            (route.path, method)
            for route in app.routes
            for method in (getattr(route, "methods", None) or {"WEBSOCKET"})
            if method not in {"HEAD", "OPTIONS"}
        ]
        assert len(route_keys) == len(set(route_keys))
        repeated_results = InProcessModuleLoader().load(
            app,
            manager.enabled_in_process_descriptors(),
        )
        assert repeated_results == [
            {"module_id": "conversation", "status": "loaded"}
        ]
        repeated_route_keys = [
            (route.path, method)
            for route in app.routes
            for method in (getattr(route, "methods", None) or {"WEBSOCKET"})
            if method not in {"HEAD", "OPTIONS"}
        ]
        assert repeated_route_keys == route_keys
        for path in (
            "/api/v1/conversation",
            "/api/v1/conversation/history",
            "/api/v1/llm-profile",
            "/chat",
            "/chat/text-only",
            "/history",
            "/history/clear",
            "/ws/chat",
            "/dashboard/llm/profile",
        ):
            assert any(route_path == path for route_path, _method in route_keys)

        versioned = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "versioned"},
        )
        legacy = await call(
            app,
            "POST",
            "/chat/text-only",
            json={"message": "legacy", "with_audio": False},
        )
        with_audio = await call(
            app,
            "POST",
            "/chat",
            json={"message": "audio", "with_audio": True},
        )
        assert versioned.status_code == legacy.status_code == with_audio.status_code == 200
        assert versioned.json()["text"] == legacy.json()["text"] == "chat:package-default"
        assert versioned.json()["emotion"] == legacy.json()["emotion"] == "calm"
        assert with_audio.json()["audio_base64"] == base64.b64encode(
            b"fake-audio"
        ).decode("ascii")
        assert "只读安装包上下文" in clients[0].messages[0][0]["content"]

        before_switch = await call(app, "GET", "/history")
        assert before_switch.json()["count"] == 6
        switched = await call(
            app,
            "PUT",
            "/api/v1/llm-profile",
            json={
                "provider": "custom",
                "base_url": "http://127.0.0.1:9922/v1",
                "model": "package-switched",
                "thinking_mode": "enabled",
            },
        )
        assert switched.status_code == 200
        assert switched.json()["thinking_mode"] == "disabled"
        legacy_profile = await call(app, "GET", "/dashboard/llm/profile")
        assert legacy_profile.json() == switched.json()
        assert set(switched.json()) == {
            "provider",
            "base_url",
            "model",
            "thinking_mode",
            "updated_at",
        }
        saved = json.loads(profile_path.read_text(encoding="utf-8"))
        assert set(saved) == set(switched.json())
        assert saved["model"] == "package-switched"
        assert TEST_API_KEY not in profile_path.read_text(encoding="utf-8")
        after_switch = await call(app, "GET", "/api/v1/conversation/history")
        assert after_switch.json()["count"] == before_switch.json()["count"]
        await app.state.conversation_service_close()

        restarted_clients: list[FakeClient] = []
        restarted, restarted_results = restarted_app(
            manager,
            profile_path,
            restarted_clients,
        )
        assert restarted_results == [{"module_id": "conversation", "status": "loaded"}]
        restored_profile = await call(restarted, "GET", "/api/v1/llm-profile")
        assert restored_profile.json()["model"] == "package-switched"
        assert getattr(restarted.state, "conversation_text_generator_provider")() is (
            restarted.state.conversation_service
        )
        generated = await restarted.state.conversation_service.generate_text(
            "受控测试指令",
            "受控输入",
            fallback="local-fallback",
        )
        assert generated.generated is True
        assert generated.text == "generated:package-switched"
        await restarted.state.conversation_service_close()

        disabled = manager.disable("conversation")
        assert disabled["restart_required"] is True
        no_module_app = FastAPI()
        no_module_results = InProcessModuleLoader().load(
            no_module_app,
            manager.enabled_in_process_descriptors(),
        )
        assert no_module_results == []
        provider = getattr(
            no_module_app.state,
            "conversation_text_generator_provider",
            lambda: None,
        )
        assert provider() is None
        consumer_text = "consumer-local-fallback" if provider() is None else "unexpected"
        assert consumer_text == "consumer-local-fallback"
        assert not any(
            route.path.startswith("/api/v1/conversation")
            for route in no_module_app.routes
        )

        removed = manager.uninstall("conversation")
        assert removed["data_preserved"] is True
        assert profile_path.is_file()
        uninstalled = FastAPI()
        assert InProcessModuleLoader().load(
            uninstalled,
            manager.enabled_in_process_descriptors(),
        ) == []
        assert not any(route.path == "/chat/text-only" for route in uninstalled.routes)

        manager.install(package, digest, expected_module_id="conversation")
        manager.enable("conversation")
        reinstalled_clients: list[FakeClient] = []
        reinstalled, reinstalled_results = restarted_app(
            manager,
            profile_path,
            reinstalled_clients,
        )
        assert reinstalled_results == [{"module_id": "conversation", "status": "loaded"}]
        relinked = await call(reinstalled, "GET", "/api/v1/llm-profile")
        assert relinked.json()["model"] == "package-switched"
        module_data = manager.data_root / "conversation"
        module_data.mkdir(parents=True)
        (module_data / "temporary-sentinel.txt").write_text(
            "temporary",
            encoding="utf-8",
        )
        purged = manager.purge_data("conversation", "conversation")
        assert purged["purged"] is True
        assert not module_data.exists()
        assert profile_path.is_file()
        await reinstalled.state.conversation_service_close()


def check_atomic_failures_and_duplicate_routes() -> None:
    with tempfile.TemporaryDirectory(
        prefix="kei-conversation-failures-"
    ) as temp_dir:
        root = Path(temp_dir)
        package = build_conversation_package(root / "conversation.zip")

        wrong_hash_manager = make_manager(root / "wrong-hash")
        try:
            wrong_hash_manager.install(
                package,
                "0" * 64,
                expected_module_id="conversation",
            )
        except PackageValidationError:
            pass
        else:
            raise AssertionError("conversation package accepted a wrong digest")
        assert "conversation" not in wrong_hash_manager.snapshot()
        assert not (wrong_hash_manager.runtime_root / "conversation").exists()

        missing_asset = build_conversation_package(root / "missing-dashboard")
        (missing_asset / "dashboard" / "index.js").unlink()
        invalid_manager = make_manager(root / "missing-manager")
        invalid_digest = invalid_manager.calculate_package_sha256(missing_asset)
        try:
            invalid_manager.install(
                missing_asset,
                invalid_digest,
                expected_module_id="conversation",
            )
        except PackageValidationError:
            pass
        else:
            raise AssertionError("package with missing dashboard entrypoint was accepted")
        assert "conversation" not in invalid_manager.snapshot()
        assert not (invalid_manager.runtime_root / "conversation").exists()

        duplicate_manager = make_manager(root / "duplicate-manager")
        digest = file_sha256(package)
        duplicate_manager.install(
            package,
            digest,
            expected_module_id="conversation",
        )
        duplicate_manager.enable("conversation")
        app = FastAPI()

        @app.post("/api/v1/conversation")
        async def existing_route():
            return {"text": "existing"}

        factory_calls = 0

        def forbidden_factory():
            nonlocal factory_calls
            factory_calls += 1
            raise AssertionError("service was created before duplicate route rejection")

        app.state.conversation_service_factory = forbidden_factory
        results = InProcessModuleLoader().load(
            app,
            duplicate_manager.enabled_in_process_descriptors(),
        )
        assert len(results) == 1
        assert results[0]["module_id"] == "conversation"
        assert results[0]["status"] == "failed"
        assert "already registered" in results[0]["error"]
        assert factory_calls == 0
        assert [route.path for route in app.routes].count(
            "/api/v1/conversation"
        ) == 1
        assert not getattr(app.state, "conversation_module_registered", False)


def check_websocket_contract() -> None:
    with tempfile.TemporaryDirectory(
        prefix="kei-conversation-websocket-"
    ) as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_conversation_package(root / "conversation.zip")
        manager.install(
            package,
            file_sha256(package),
            expected_module_id="conversation",
        )
        manager.enable("conversation")
        clients: list[FakeClient] = []
        app, results = restarted_app(
            manager,
            root / "profile.json",
            clients,
        )
        assert results == [{"module_id": "conversation", "status": "loaded"}], results
        with TestClient(app) as client:
            with client.websocket_connect("/ws/chat") as websocket:
                websocket.send_json({"message": "websocket"})
                payload = websocket.receive_json()
        assert payload["text"] == "chat:package-default"
        assert payload["emotion"] == "calm"
        assert payload["audio_base64"] == base64.b64encode(
            b"fake-audio"
        ).decode("ascii")
        assert set(payload) == {
            "text",
            "emotion",
            "audio_base64",
            "timestamp",
        }
        asyncio.run(app.state.conversation_service_close())


async def check_late_context_provider_assembly() -> None:
    """Conversation must observe a context module registered after itself."""

    with tempfile.TemporaryDirectory(
        prefix="kei-conversation-late-context-"
    ) as temp_dir:
        root = Path(temp_dir)

        captured: dict[str, object] = {}

        def capture_create_service(**kwargs):
            captured.update(kwargs)
            return object()

        wiring_app = FastAPI()
        wiring_app.state.conversation_context_provider = StaticContext(
            "explicit-static-provider"
        )
        with patch.object(
            conversation_module,
            "create_conversation_service",
            side_effect=capture_create_service,
        ):
            conversation_module._create_service(wiring_app)
        wired_provider = captured["context_provider"]
        assert isinstance(wired_provider, AppStateConversationContextProvider)
        assert wired_provider.get_context() == "explicit-static-provider"

        app = FastAPI()
        provider = AppStateConversationContextProvider(app)
        entered = asyncio.Event()
        release = asyncio.Event()
        client = BlockingFakeClient("late-context", entered, release)
        profile = LLMProfile(
            "custom",
            "http://127.0.0.1:9911/v1",
            "late-context",
            "disabled",
        )
        repository = LLMProfileRepository(root / "profile.json")
        service = ConversationService(
            ConversationRuntime(client, profile, context_provider=provider),
            repository,
            lambda _profile: FakeClient("unused"),
        )
        app.state.conversation_service_factory = lambda: service
        app.state.conversation_local_control_guard = lambda _request: True
        conversation_module.register(app)

        first_response = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "before-affection"},
        )
        assert first_response.status_code == 200
        first_system = client.messages[0][0]["content"]
        assert "late-provider-a" not in first_system
        assert "late-provider-b" not in first_system

        app.state.conversation_context_provider = StaticContext(
            "late-provider-after-registration"
        )
        late_response = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "after-affection-registration"},
        )
        assert late_response.status_code == 200
        assert "late-provider-after-registration" in (
            client.messages[1][0]["content"]
        )

        app.state.conversation_context_provider = StaticContext(
            "late-provider-a"
        )
        concurrent_a = asyncio.create_task(
            call(
                app,
                "POST",
                "/api/v1/conversation",
                json={"message": "after-affection-a"},
            )
        )
        await entered.wait()
        await asyncio.sleep(0)
        app.state.conversation_context_provider = StaticContext(
            "late-provider-b"
        )
        concurrent_b = asyncio.create_task(
            call(
                app,
                "POST",
                "/api/v1/conversation",
                json={"message": "after-affection-b"},
            )
        )
        release.set()
        response_a, response_b = await asyncio.gather(
            concurrent_a,
            concurrent_b,
        )
        assert response_a.status_code == response_b.status_code == 200
        system_a = client.messages[2][0]["content"]
        system_b = client.messages[3][0]["content"]
        assert "late-provider-a" in system_a
        assert "late-provider-b" not in system_a
        assert "late-provider-b" in system_b
        assert "late-provider-a" not in system_b

        del app.state.conversation_context_provider
        removed = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "provider-removed"},
        )
        assert removed.status_code == 200
        assert "late-provider-a" not in client.messages[4][0]["content"]
        assert "late-provider-b" not in client.messages[4][0]["content"]

        app.state.conversation_context_provider = BrokenContext()
        broken = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "broken-provider"},
        )
        assert broken.status_code == 200
        assert "pk200-private-context-must-not-leak" not in broken.text

        app.state.conversation_context_provider = object()
        non_structural = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "non-structural-provider"},
        )
        assert non_structural.status_code == 200

        app.state.conversation_context_provider = NonStringContext()
        non_string = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "non-string-provider"},
        )
        assert non_string.status_code == 200
        assert "not prompt text" not in client.messages[7][0]["content"]

        app.state.conversation_context_provider = provider
        self_reference = await call(
            app,
            "POST",
            "/api/v1/conversation",
            json={"message": "self-provider"},
        )
        assert self_reference.status_code == 200
        assert client.messages[8][0]["content"] == FakeClient.system_prompt
        await app.state.conversation_service_close()


async def check_async_unregister_lifecycle() -> None:
    with tempfile.TemporaryDirectory(
        prefix="kei-conversation-unregister-"
    ) as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_conversation_package(root / OFFICIAL_ASSET_NAME)
        manager.install(
            package,
            file_sha256(package),
            expected_module_id="conversation",
        )
        manager.enable("conversation")

        app = FastAPI()
        affection_provider = StaticContext("late-affection-provider")
        app.state.conversation_context_provider = affection_provider
        clients: list[FakeClient] = []
        app.state.conversation_service_factory = lambda: make_service(
            root / "profile.json",
            clients,
        )
        app.state.conversation_local_control_guard = lambda _request: True
        loader = InProcessModuleLoader()
        loaded = loader.load(
            app,
            manager.enabled_in_process_descriptors(),
        )
        assert loaded == [{"module_id": "conversation", "status": "loaded"}]
        import_name = loader._registrations["conversation"]["import_name"]
        installed_module = sys.modules[import_name]
        installed_register = installed_module.register
        installed_unregister = installed_module.unregister
        assert callable(installed_unregister)
        assert app.state.conversation_context_provider is affection_provider

        unloaded = await loader.unload_one_async(app, "conversation")
        assert unloaded == {
            "module_id": "conversation",
            "status": "unloaded",
        }
        assert clients[0].closed == 1
        assert app.state.conversation_context_provider is affection_provider
        for name in (
            "conversation_service",
            "conversation_text_generator_provider",
            "conversation_service_close",
            "conversation_module_registered",
            "_conversation_module_ownership",
        ):
            assert not hasattr(app.state, name)
        assert not any(
            route.path in conversation_module.DECLARED_ROUTE_PATHS
            for route in app.routes
        )
        assert await loader.unload_one_async(app, "conversation") == {
            "module_id": "conversation",
            "status": "not_loaded",
        }
        await installed_unregister(app)
        await installed_unregister(app)
        assert clients[0].closed == 1

        protected = FastAPI()
        protected_provider = StaticContext("protected-affection-provider")
        protected.state.conversation_context_provider = protected_provider
        protected_clients: list[FakeClient] = []
        protected.state.conversation_service_factory = lambda: make_service(
            root / "protected-profile.json",
            protected_clients,
        )
        protected.state.conversation_local_control_guard = lambda _request: True
        installed_register(protected)
        foreign_service = object()

        async def foreign_close() -> None:
            return None

        protected.state.conversation_service = foreign_service
        protected.state.conversation_service_close = foreign_close
        await installed_unregister(protected)
        assert protected_clients[0].closed == 1
        assert protected.state.conversation_service is foreign_service
        assert protected.state.conversation_service_close is foreign_close
        assert protected.state.conversation_context_provider is protected_provider
        assert not hasattr(
            protected.state,
            "conversation_text_generator_provider",
        )
        assert not hasattr(protected.state, "conversation_module_registered")
        assert not hasattr(protected.state, "_conversation_module_ownership")
        await installed_unregister(protected)
        assert protected_clients[0].closed == 1

        failing = FastAPI()
        failing_provider = StaticContext("failure-affection-provider")
        failing.state.conversation_context_provider = failing_provider
        failing_service = FailingCloseService()
        failing.state.conversation_service_factory = lambda: failing_service
        failing.state.conversation_local_control_guard = lambda _request: True
        installed_register(failing)
        try:
            await installed_unregister(failing)
        except RuntimeError as exc:
            assert str(exc) == "conversation service cleanup failed"
            assert TEST_API_KEY not in str(exc)
            assert "private-profile-path" not in str(exc)
        else:
            raise AssertionError("unregister swallowed a service close failure")
        assert failing_service.close_calls == 1
        assert failing.state.conversation_context_provider is failing_provider
        for name in (
            "conversation_service",
            "conversation_text_generator_provider",
            "conversation_service_close",
            "conversation_module_registered",
            "_conversation_module_ownership",
        ):
            assert not hasattr(failing.state, name)
        await installed_unregister(failing)
        assert failing_service.close_calls == 1


def main() -> int:
    check_deterministic_package_and_release()
    check_missing_environment_configuration()
    asyncio.run(check_lifecycle_routes_profile_and_fallback())
    check_atomic_failures_and_duplicate_routes()
    check_websocket_contract()
    asyncio.run(check_late_context_provider_assembly())
    asyncio.run(check_async_unregister_lifecycle())
    print("conversation package tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
