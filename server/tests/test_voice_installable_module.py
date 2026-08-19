"""Isolated lifecycle and package checks for the installable PK-210 module."""

from __future__ import annotations

import asyncio
import hashlib
import io
import inspect
import json
import re
import subprocess
import tempfile
import threading
import wave
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.calendar_contracts import (
    CalendarSummaryProviderRegistry,
    calendar_summary_registry,
    get_calendar_summary,
)
from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ModuleConflictError
from features.voice.models import (
    AudioResult,
    EncodedUtterance,
    ProviderCapabilities,
    ProviderHealth,
    Transcript,
    VoicePackRef,
    VoiceRequest,
)
from features.voice.media import OUTPUT_PROFILE
from features.voice.module import register as register_source_voice
from features.voice.module import unregister as unregister_source_voice
from features.voice.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_voice_package,
    file_sha256,
)
from features.voice_pack_registry.package_builder import (
    build_voice_pack_registry_package,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VOICE_ROOT = PROJECT_ROOT / "server" / "features" / "voice"
RELEASE_ROOT = VOICE_ROOT / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    "backend/__init__.py",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


class FakeASR:
    def __init__(self, text: str = "老师你好") -> None:
        self.text = text
        self.calls = []
        self.cancelled = []
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available")

    def capabilities(self):
        return ProviderCapabilities("fake-asr", ("transcribe",), ("wav",))

    async def transcribe(self, request):
        self.calls.append(request)
        return Transcript(text=self.text, language="zh", language_probability=1.0)

    async def cancel(self, request_id):
        self.cancelled.append(request_id)

    async def close(self):
        self.closed = True


class AwaitingCloseASR(FakeASR):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0
        self.close_started = asyncio.Event()
        self.close_release = asyncio.Event()

    async def close(self):
        self.close_calls += 1
        self.close_started.set()
        await self.close_release.wait()
        self.closed = True


class FakeConversation:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available")

    def capabilities(self):
        return ProviderCapabilities("fake-conversation", ("chat",))

    async def chat(self, message: str, *, request_id: str):
        self.calls.append((request_id, message))
        return SimpleNamespace(
            text=f"回复：{message}",
            emotion="calm",
            timestamp="2026-07-30T12:00:00",
        )

    async def cancel(self, _request_id):
        return None

    async def close(self):
        self.closed = True


class FakeTTS:
    def __init__(self, *, wait: asyncio.Event | None = None) -> None:
        self.wait = wait
        self.calls = []
        self.cancelled = []
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available")

    def capabilities(self):
        return ProviderCapabilities("fake-tts", ("synthesize",), ("wav",))

    async def synthesize(self, request, voice_pack):
        self.calls.append((request, voice_pack))
        try:
            if self.wait is not None:
                await self.wait.wait()
            stream = io.BytesIO()
            with wave.open(stream, "wb") as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(24_000)
                target.writeframes((b"\x00\x00" * 8) + (b"\x00\x10" * 240))
            return AudioResult(audio=stream.getvalue())
        except asyncio.CancelledError:
            self.cancelled.append(request.request_id)
            raise

    async def cancel(self, request_id):
        self.cancelled.append(request_id)

    async def close(self):
        self.closed = True


class FakeSilkEncoder:
    def __init__(self) -> None:
        self.calls = []
        self.cancelled = []
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available")

    def capabilities(self):
        return ProviderCapabilities("fake-silk", ("encode",), (OUTPUT_PROFILE,))

    async def encode(self, request):
        self.calls.append(request)
        return EncodedUtterance(b"SILK" + request.pcm_s16le[:8], "audio/silk", OUTPUT_PROFILE)

    async def cancel(self, request_id):
        self.cancelled.append(request_id)

    async def close(self):
        self.closed = True


class FailingCloseTTS(FakeTTS):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        raise RuntimeError("C:/FAKE/private/tts-close")


class FakeVoicePackResolver:
    async def health(self):
        return ProviderHealth(True, "available")

    def capabilities(self):
        return ProviderCapabilities("fake-pack", ("resolve",))

    async def resolve_active_pack(self):
        return VoicePackRef("fake-kei", "1.0.0", "fake-tts")

    async def resolve_pack(self, _pack_id):
        return await self.resolve_active_pack()

    async def cancel(self, _request_id):
        return None

    async def close(self):
        return None


class BlockingVoicePackResolver(FakeVoicePackResolver):
    def __init__(self, pack_id: str) -> None:
        self.pack_id = pack_id
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def resolve_active_pack(self):
        self.started.set()
        await self.release.wait()
        return VoicePackRef(self.pack_id, "1.0.0", "fake-tts")


class FakeRuntimeControl:
    def __init__(self, *, fail_status: bool = False, fail_start: bool = False):
        self.fail_status = fail_status
        self.fail_start = fail_start
        self.status_calls = 0
        self.start_calls = []
        self.selection_status_calls = 0
        self.selection_calls = 0

    def status(self):
        self.status_calls += 1
        if self.fail_status:
            raise RuntimeError("C:/FAKE/private/runtime-control-status")
        return {
            "asr": {
                "running": False,
                "ready": True,
                "state": "ready",
                "message": "C:/FAKE/private/asr-message",
                "launcher_exists": True,
                "configuration_ready": True,
                "private_path": "C:/FAKE/start_asr.bat",
            },
            "gpt-sovits": {
                "running": False,
                "ready": True,
                "state": "ready",
                "message": "GPT-SoVITS 已就绪。",
                "launcher_exists": True,
                "configuration_ready": True,
            },
        }

    def start(self, target):
        self.start_calls.append(target)
        if self.fail_start:
            raise RuntimeError("C:/FAKE/private/start-error")
        return {
            **self.status()[target],
            "running": True,
            "ready": False,
            "state": "starting",
            "message": f"{target} 正在启动。",
            "started": True,
            "command": "C:/FAKE/private/start.bat",
        }

    def asr_model_selection_status(self):
        self.selection_status_calls += 1
        return {
            "available": True,
            "configured": False,
            "state": "unconfigured",
            "directory_name": None,
            "private_path": "C:/FAKE/private/model",
        }

    async def select_asr_model_directory(self):
        self.selection_calls += 1
        return {
            "available": True,
            "configured": True,
            "state": "configured",
            "directory_name": "fake-model",
            "private_path": "C:/FAKE/private/model",
        }


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def write_conversation_fixture(root: Path) -> Path:
    package = root / "conversation"
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "conversation",
        "name": "fake conversation dependency",
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": ["/api/v1/conversation"],
        "legacy_endpoints": [],
        "data_namespace": "conversation",
        "permissions": [],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (package / "backend" / "__init__.py").write_text(
        "def register(app):\n"
        "    app.state.fake_conversation_module_registered = True\n",
        encoding="utf-8",
    )
    return package


def restarted_app(
    manager: ModuleManager,
    data_root: Path,
    *,
    tts=True,
) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    app.state.voice_data_root = data_root
    app.state.voice_asr_provider = FakeASR()
    app.state.voice_conversation_provider = FakeConversation()
    app.state.voice_tts_provider = FakeTTS() if tts else None
    app.state.voice_pack_resolver = FakeVoicePackResolver() if tts else None
    app.state.voice_utterance_encoder = FakeSilkEncoder() if tts else None
    results = InProcessModuleLoader().load(
        app,
        manager.enabled_in_process_descriptors(),
    )
    manager.record_load_results(results)
    return app, results


def _assert_package_contents(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = sorted(info.filename for info in infos)
        assert names == sorted(EXPECTED_PACKAGE_NAMES)
        assert len(names) == len(set(name.casefold() for name in names))
        combined = []
        for info in infos:
            assert info.date_time == FIXED_ZIP_DATETIME
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.create_system == 3
            assert info.external_attr == 0o100644 << 16
            assert not info.filename.startswith(("/", "\\"))
            assert "\\" not in info.filename
            assert ".." not in Path(info.filename).parts
            combined.append(archive.read(info).decode("utf-8"))
    package_text = "\n".join(combined)
    assert "\r\n" not in package_text
    assert not re.search(
        r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b",
        package_text,
    )
    assert "features.calendar" not in package_text
    assert "features.conversation" not in package_text
    assert "gpt_sovits" not in package_text.lower()
    assert not any(
        token in name.casefold()
        for name in names
        for token in (
            ".env",
            "weight",
            "reference_audio",
            "vendor",
            "script",
            "output",
            "fixture",
            "test",
        )
    )


def check_deterministic_package_and_release_metadata() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    expected_entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "voice"
    assert fragment["dependencies"] == ["conversation"]
    assert fragment["optional_dependencies"] == ["calendar"]
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    with tempfile.TemporaryDirectory(prefix="kei-voice-package-test-") as temp_dir:
        root = Path(temp_dir)
        first = build_voice_package(root / "first.zip")
        second = build_voice_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)
        with zipfile.ZipFile(first) as archive:
            manifest_raw = archive.read("manifest.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
            dashboard = archive.read("dashboard/index.js").decode("utf-8")
        assert manifest["version"] == OFFICIAL_RELEASE_VERSION
        assert manifest["api_namespaces"] == [
            "/api/v1/voice",
            "/api/v1/voice-control",
        ]
        assert "/api/v1/voice-control/status" in manifest["legacy_endpoints"]
        assert "/api/v1/voice-control/asr/start" in manifest["legacy_endpoints"]
        assert "/api/v1/voice-control/asr/start-background" in manifest["legacy_endpoints"]
        assert "/api/v1/voice-control/asr/stop" in manifest["legacy_endpoints"]
        assert (
            "/api/v1/voice-control/asr/model-directory/status"
            in manifest["legacy_endpoints"]
        )
        assert (
            "/api/v1/voice-control/asr/model-directory/select"
            in manifest["legacy_endpoints"]
        )
        assert (
            "/api/v1/voice-control/gpt-sovits/start"
            in manifest["legacy_endpoints"]
        )
        assert (
            "/api/v1/voice-control/gpt-sovits/start-background"
            in manifest["legacy_endpoints"]
        )
        assert (
            "/api/v1/voice-control/gpt-sovits/stop"
            in manifest["legacy_endpoints"]
        )
        assert "export async function mount(context)" in dashboard
        assert "export async function unmount()" in dashboard
        assert "context.request('/api/v1/voice/health')" in dashboard
        assert "context.request('/api/v1/voice-control/status')" in dashboard
        assert "/api/v1/voice-control/asr/start" in dashboard
        assert "调试启动 ASR（打开窗口）" in dashboard
        assert "/api/v1/voice-control/asr/stop" in dashboard
        assert "/api/v1/voice-control/asr/model-directory/status" in dashboard
        assert "/api/v1/voice-control/asr/model-directory/select" in dashboard
        assert "webkitdirectory" not in dashboard
        assert "/api/v1/voice-control/gpt-sovits/start" in dashboard
        assert "调试启动 GPT-SoVITS（打开窗口）" in dashboard
        assert "/api/v1/voice-control/gpt-sovits/stop" in dashboard
        assert "globalThis.confirm" in dashboard
        assert "fetch(" not in dashboard
        assert "localStorage" not in dashboard
        assert expected_entry["manifest_sha256"] == hashlib.sha256(
            manifest_raw
        ).hexdigest()
        assert expected_entry["package_sha256"] == file_sha256(first)
        assert expected_entry["package_size"] == first.stat().st_size


def check_lifecycle_api_degradation_and_isolation() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-voice-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        conversation = write_conversation_fixture(root / "fixtures")
        voice = build_voice_package(root / "voice.zip")
        missing_dependency_manager = make_manager(root / "missing-dependency")
        missing_dependency_manager.install(
            voice,
            file_sha256(voice),
            expected_module_id="voice",
        )
        try:
            missing_dependency_manager.enable("voice")
        except ModuleConflictError as exc:
            assert "conversation" in str(exc)
        else:
            raise AssertionError("voice enabled without its conversation dependency")

        conversation_hash = manager.calculate_package_sha256(conversation)
        manager.install(
            conversation,
            conversation_hash,
            expected_module_id="conversation",
        )
        manager.enable("conversation")
        manager.install(voice, file_sha256(voice), expected_module_id="voice")
        manager.enable("voice")

        voice_data = root / "external-voice-data"
        external_model_registration = root / "external-provider" / "registry.json"
        user_audio = root / "user-audio" / "kept.wav"
        external_model_registration.parent.mkdir(parents=True)
        external_model_registration.write_text("fake registration", encoding="utf-8")
        user_audio.parent.mkdir(parents=True)
        user_audio.write_bytes(b"user-owned")

        app, results = restarted_app(manager, voice_data)
        assert {item["module_id"] for item in results} == {
            "conversation",
            "voice",
        }
        route_paths = [route.path for route in app.routes]
        for path in (
            "/api/v1/voice/health",
            "/api/v1/voice/chat",
            "/api/v1/voice/synthesize",
            "/api/v1/voice/chat/stream",
            "/api/v1/voice/audio/{filename}",
            "/voice/health",
            "/voice/chat",
            "/voice/chat/stream",
            "/voice/audio/{filename}",
            "/api/v1/voice-control/status",
            "/api/v1/voice-control/asr/start",
            "/api/v1/voice-control/gpt-sovits/start",
        ):
            assert route_paths.count(path) == 1
        assert manager.asset_path("voice", "dashboard/index.js").is_file()

        files = {"file": ("sample.wav", b"fake-audio", "audio/wav")}
        versioned = asyncio.run(
            call(app, "POST", "/api/v1/voice/chat", files=files)
        )
        legacy = asyncio.run(call(app, "POST", "/voice/chat", files=files))
        assert versioned.status_code == legacy.status_code == 200
        assert versioned.json()["mode"] == legacy.json()["mode"] == "audio"
        assert versioned.json()["assistant_text"] == legacy.json()["assistant_text"]
        assert versioned.json()["audio_path"].startswith("/api/v1/voice/audio/")
        assert legacy.json()["audio_path"].startswith("/voice/audio/")
        assert not any((voice_data / "tmp").iterdir())

        conversation_calls = len(app.state.voice_conversation_provider.calls)
        asr_calls = len(app.state.voice_asr_provider.calls)
        synthesis = asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice/synthesize",
            headers={"Idempotency-Key": "qqmsg_installable_1234"},
            json={"purpose": "qq_reply", "text": "安装包只合成一次。"},
        ))
        assert synthesis.status_code == 200, synthesis.text
        assert synthesis.headers["content-type"] == "audio/silk"
        assert synthesis.headers["x-kei-audio-final"] == "true"
        assert synthesis.headers["x-kei-audio-duration-ms"].isdigit()
        assert 1 <= int(synthesis.headers["x-kei-audio-duration-ms"]) <= 60000
        assert synthesis.headers["x-kei-audio-profile"] == "qq_c2c_voice_v1"
        assert synthesis.content.startswith(b"SILK")
        assert len(app.state.voice_conversation_provider.calls) == conversation_calls
        assert len(app.state.voice_asr_provider.calls) == asr_calls
        assert len(app.state.voice_utterance_encoder.calls) == 1

        async def concurrent_requests():
            return await asyncio.gather(
                app.state.voice_service.chat(VoiceRequest(audio=b"one")),
                app.state.voice_service.chat(VoiceRequest(audio=b"two")),
            )

        replies = asyncio.run(concurrent_requests())
        filenames = [reply.audio[0].filename for reply in replies]
        assert len(set(filenames)) == 2
        assert all((voice_data / "output" / name).is_file() for name in filenames)
        assert not any((voice_data / "tmp").iterdir())

        degraded_app, degraded_results = restarted_app(
            manager,
            root / "degraded-data",
            tts=False,
        )
        assert next(
            item for item in degraded_results if item["module_id"] == "voice"
        )["status"] == "loaded"
        degraded = asyncio.run(
            call(
                degraded_app,
                "POST",
                "/api/v1/voice/chat",
                files={"file": ("sample.wav", b"fake-audio", "audio/wav")},
            )
        )
        assert degraded.status_code == 200
        assert degraded.json()["mode"] == "text_only"
        assert degraded.json()["audio_available"] is False
        assert degraded.json()["errors"][0]["code"] == "tts_unavailable"

        disabled = manager.disable("voice")
        assert disabled["restart_required"] is True
        disabled_app, disabled_results = restarted_app(
            manager,
            root / "disabled-data",
        )
        assert all(item["module_id"] != "voice" for item in disabled_results)
        try:
            manager.asset_path("voice", "dashboard/index.js")
        except ModuleConflictError:
            pass
        else:
            raise AssertionError("disabled voice dashboard remained available")
        assert (
            asyncio.run(call(disabled_app, "GET", "/api/v1/voice/health")).status_code
            == 404
        )
        uninstalled = manager.uninstall("voice")
        assert uninstalled["data_preserved"] is True
        assert external_model_registration.is_file()
        assert user_audio.read_bytes() == b"user-owned"

        manager.install(voice, file_sha256(voice), expected_module_id="voice")
        manager.enable("voice")
        reinstalled_app, reinstalled_results = restarted_app(
            manager,
            root / "reinstalled-data",
        )
        assert next(
            item for item in reinstalled_results if item["module_id"] == "voice"
        )["status"] == "loaded"
        assert (
            asyncio.run(call(reinstalled_app, "GET", "/voice/health")).status_code
            == 200
        )


def check_runtime_control_provider_and_guards() -> None:
    trusted = {"Origin": "http://127.0.0.1:8000"}
    with tempfile.TemporaryDirectory(prefix="kei-voice-control-missing-") as temp:
        app = FastAPI()
        app.state.voice_data_root = Path(temp)
        app.state.voice_conversation_provider = FakeConversation()
        register_source_voice(app)

        missing = asyncio.run(
            call(app, "GET", "/api/v1/voice-control/status")
        )
        assert missing.status_code == 200
        assert missing.json()["asr"]["state"] == "unavailable"
        assert missing.json()["gpt-sovits"]["state"] == "unavailable"
        missing_selection = asyncio.run(call(
            app,
            "GET",
            "/api/v1/voice-control/asr/model-directory/status",
        ))
        assert missing_selection.status_code == 200
        assert missing_selection.json()["state"] == "unavailable"
        assert asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice-control/asr/start",
        )).status_code == 403
        unavailable = asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice-control/asr/start",
            headers=trusted,
        ))
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == (
            "voice_runtime_control_unavailable"
        )

        async def remote_status():
            transport = httpx.ASGITransport(
                app=app,
                client=("203.0.113.19", 51000),
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                return await client.get("/api/v1/voice-control/status")

        assert asyncio.run(remote_status()).status_code == 403
        asyncio.run(unregister_source_voice(app))

    with tempfile.TemporaryDirectory(prefix="kei-voice-control-provider-") as temp:
        provider = FakeRuntimeControl()
        app = FastAPI()
        app.state.voice_data_root = Path(temp)
        app.state.voice_conversation_provider = FakeConversation()
        app.state.voice_runtime_control_provider = provider
        register_source_voice(app)
        assert provider.status_calls == 0
        status = asyncio.run(call(
            app,
            "GET",
            "/api/v1/voice-control/status",
        ))
        assert status.status_code == 200
        assert provider.status_calls == 1
        assert "private_path" not in status.text
        assert "C:/FAKE" not in status.text
        selection_status = asyncio.run(call(
            app,
            "GET",
            "/api/v1/voice-control/asr/model-directory/status",
        ))
        assert selection_status.status_code == 200
        assert selection_status.json()["state"] == "unconfigured"
        assert "C:/FAKE" not in selection_status.text
        selected = asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice-control/asr/model-directory/select",
            headers=trusted,
        ))
        assert selected.status_code == 200
        assert selected.json()["directory_name"] == "fake-model"
        assert provider.selection_calls == 1
        assert "C:/FAKE" not in selected.text
        malicious = asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice-control/asr/model-directory/select",
            headers=trusted,
            json={"path": "C:/FAKE/evil"},
        ))
        assert malicious.status_code == 422
        assert provider.selection_calls == 1
        first = asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice-control/asr/start",
            headers=trusted,
        ))
        assert first.status_code == 200
        assert first.json()["started"] is True
        assert provider.start_calls == ["asr"]
        assert "command" not in first.text
        assert "C:/FAKE" not in first.text
        rejected_body = asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice-control/gpt-sovits/start",
            headers=trusted,
            json={"command": "C:/FAKE/evil.bat"},
        ))
        assert rejected_body.status_code == 422
        assert provider.start_calls == ["asr"]

    with tempfile.TemporaryDirectory(prefix="kei-voice-control-errors-") as temp:
        provider = FakeRuntimeControl(fail_status=True, fail_start=True)
        app = FastAPI()
        app.state.voice_data_root = Path(temp)
        app.state.voice_conversation_provider = FakeConversation()
        app.state.voice_runtime_control_provider = provider
        register_source_voice(app)
        status = asyncio.run(call(
            app,
            "GET",
            "/api/v1/voice-control/status",
        ))
        assert status.status_code == 200
        assert status.json()["asr"]["state"] == "unavailable"
        failed = asyncio.run(call(
            app,
            "POST",
            "/api/v1/voice-control/asr/start",
            headers=trusted,
        ))
        assert failed.status_code == 500
        assert failed.json() == {"detail": "asr_start_failed"}
        assert "C:/FAKE" not in failed.text


def check_async_unregister_ownership_and_cleanup() -> None:
    assert inspect.iscoroutinefunction(unregister_source_voice)

    async def direct_shutdown(root: Path) -> None:
        asr = AwaitingCloseASR()
        asr.close_release.set()
        tts = FakeTTS()
        conversation = FakeConversation()
        resolver = FakeVoicePackResolver()
        user_audio = root / "user-audio" / "kept.wav"
        user_audio.parent.mkdir(parents=True)
        user_audio.write_bytes(b"user-owned-audio")

        app = FastAPI()
        app.state.voice_data_root = root / "voice-data"
        app.state.voice_asr_provider = asr
        app.state.voice_conversation_provider = conversation
        app.state.voice_tts_provider = tts
        app.state.voice_pack_resolver = resolver
        register_source_voice(app)
        owner = app.state.voice_module_service_owner

        await unregister_source_voice(app)
        await unregister_source_voice(app)

        assert asr.close_calls == 1 and asr.closed
        assert tts.closed
        assert owner.asr is None
        assert owner.conversation is None
        assert owner.tts is None
        assert owner.voice_packs is None
        assert not hasattr(app.state, "voice_module_service_owner")
        assert not hasattr(app.state, "voice_service")
        assert app.state.voice_asr_provider is asr
        assert app.state.voice_conversation_provider is conversation
        assert app.state.voice_tts_provider is tts
        assert app.state.voice_pack_resolver is resolver
        assert user_audio.read_bytes() == b"user-owned-audio"

    async def loader_shutdown(root: Path) -> None:
        manager = make_manager(root)
        conversation_package = write_conversation_fixture(root / "packages")
        voice_package = build_voice_package(root / "voice.zip")
        for package, module_id in (
            (conversation_package, "conversation"),
            (voice_package, "voice"),
        ):
            manager.install(
                package,
                manager.calculate_package_sha256(package),
                expected_module_id=module_id,
            )
            manager.enable(module_id)

        asr = AwaitingCloseASR()
        tts = FailingCloseTTS()
        conversation = FakeConversation()
        resolver = FakeVoicePackResolver()
        user_audio = root / "user-audio" / "kept.wav"
        user_audio.parent.mkdir(parents=True)
        user_audio.write_bytes(b"keep-this-audio")
        app = FastAPI()
        app.state.voice_data_root = root / "voice-data"
        app.state.voice_asr_provider = asr
        app.state.voice_conversation_provider = conversation
        app.state.voice_tts_provider = tts
        app.state.voice_pack_resolver = resolver
        loader = InProcessModuleLoader()
        results = loader.load(app, manager.enabled_in_process_descriptors())
        assert results == [
            {"module_id": "conversation", "status": "loaded"},
            {"module_id": "voice", "status": "loaded"},
        ]
        owner = app.state.voice_module_service_owner
        replacement = object()
        app.state.voice_service = replacement

        closing = asyncio.create_task(loader.unload_one_async(app, "voice"))
        await asyncio.wait_for(asr.close_started.wait(), timeout=1)
        assert not closing.done()
        assert app.state.voice_module_service_owner is owner
        assert owner.asr is None
        assert owner.conversation is None
        assert owner.tts is None
        assert owner.voice_packs is None
        asr.close_release.set()
        result = await closing

        assert result == {"module_id": "voice", "status": "unloaded"}
        assert asr.close_calls == 1 and asr.closed
        assert tts.close_calls == 1
        assert app.state.voice_service is replacement
        assert not hasattr(app.state, "voice_module_service_owner")
        assert not hasattr(app.state, "voice_pack_resolver_binding")
        assert app.state.voice_asr_provider is asr
        assert app.state.voice_conversation_provider is conversation
        assert app.state.voice_tts_provider is tts
        assert app.state.voice_pack_resolver is resolver
        assert user_audio.read_bytes() == b"keep-this-audio"
        assert await loader.unload_one_async(app, "voice") == {
            "module_id": "voice",
            "status": "not_loaded",
        }
        assert asr.close_calls == 1
        assert tts.close_calls == 1

    with tempfile.TemporaryDirectory(prefix="kei-voice-unregister-direct-") as temp:
        asyncio.run(direct_shutdown(Path(temp)))
    with tempfile.TemporaryDirectory(prefix="kei-voice-unregister-loader-") as temp:
        asyncio.run(loader_shutdown(Path(temp)))


def check_dashboard_explicit_runtime_controls() -> None:
    source = (
        VOICE_ROOT / "package_source" / "dashboard" / "index.js"
    ).read_text(encoding="utf-8")
    assert "globalThis.fetch" not in source
    with tempfile.TemporaryDirectory(prefix="kei-voice-dashboard-") as temp:
        module_path = Path(temp) / "index.mjs"
        module_path.write_text(source, encoding="utf-8")
        probe = f"""
class FakeElement {{
  constructor(tag, ownerDocument) {{
    this.tagName = tag;
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.dataset = {{}};
    this.listeners = {{}};
    this.disabled = false;
    this.textContent = '';
    this.className = '';
  }}
  append(...items) {{ this.children.push(...items); }}
  replaceChildren(...items) {{ this.children = [...items]; }}
  addEventListener(name, handler) {{ this.listeners[name] = handler; }}
  querySelector(selector) {{
    const match = selector.match(/^\\[data-voice-role="([^"]+)"\\]$/);
    if (!match) return null;
    const role = match[1];
    const visit = (node) => {{
      if (!node || typeof node !== 'object') return null;
      if (node.dataset?.voiceRole === role) return node;
      for (const child of node.children || []) {{
        const found = visit(child);
        if (found) return found;
      }}
      return null;
    }};
    return visit(this);
  }}
}}
const ownerDocument = {{createElement: (tag) => new FakeElement(tag, ownerDocument)}};
const root = new FakeElement('root', ownerDocument);
const calls = [];
const notices = [];
globalThis.fetch = () => {{ throw new Error('global fetch must not be used'); }};
const runtimeStatus = {{
  asr: {{state:'ready', ready:true, running:false, message:'ASR ready'}},
  'gpt-sovits': {{state:'ready', ready:true, running:false, message:'TTS ready'}},
}};
const mod = await import({module_path.as_uri()!r});
await mod.mount({{
  root,
  request: async (path, options = {{}}) => {{
    calls.push([path, options.method || 'GET']);
    if (path === '/api/v1/voice/health') return {{providers:{{}}}};
    if (path === '/api/v1/voice-control/status') return runtimeStatus;
    if (path === '/api/v1/voice-control/asr/model-directory/status') {{
      return {{available:true, configured:false, state:'unconfigured', message:'not configured'}};
    }}
    if (path === '/api/v1/voice-control/asr/model-directory/select') {{
      return {{available:true, configured:true, state:'configured', directory_name:'fake-model', message:'configured'}};
    }}
    if (path === '/api/v1/voice-control/asr/start') {{
      return {{...runtimeStatus.asr, state:'starting', running:true, ready:false, started:true}};
    }}
    if (path === '/api/v1/voice-control/gpt-sovits/start') {{
      throw new Error('fake unavailable');
    }}
    throw new Error(`unexpected endpoint: ${{path}}`);
  }},
  notify: (message, level) => notices.push([message, level]),
}});
if (calls.filter(([, method]) => method === 'POST').length !== 0) {{
  throw new Error('mount triggered a runtime action');
}}
if (root.querySelector('[data-voice-role="start-asr"]').disabled) {{
  throw new Error('ready ASR button was not enabled');
}}
await root.querySelector('[data-voice-role="start-asr"]').listeners.click();
if (calls.filter(([path, method]) =>
  path === '/api/v1/voice-control/asr/start' && method === 'POST').length !== 1) {{
  throw new Error('explicit ASR click did not issue exactly one POST');
}}
await root.querySelector('[data-voice-role="select-asr-model-directory"]').listeners.click();
if (calls.filter(([path, method]) =>
  path === '/api/v1/voice-control/asr/model-directory/select' && method === 'POST').length !== 1) {{
  throw new Error('explicit directory click did not issue exactly one POST');
}}
if (root.querySelector('[data-voice-role="asr-model-directory-detail"]').textContent.includes('C:/')) {{
  throw new Error('directory status exposed a local path');
}}
await root.querySelector('[data-voice-role="start-gpt-sovits"]').listeners.click();
if (calls.filter(([path, method]) =>
  path === '/api/v1/voice-control/gpt-sovits/start' && method === 'POST').length !== 1) {{
  throw new Error('explicit GPT-SoVITS click did not issue exactly one POST');
}}
if (!notices.some(([, level]) => level === 'error')) {{
  throw new Error('runtime start error was not surfaced');
}}
const postsBeforeRefresh = calls.filter(([, method]) => method === 'POST').length;
await root.querySelector('[data-voice-role="refresh"]').listeners.click();
if (calls.filter(([, method]) => method === 'POST').length !== postsBeforeRefresh) {{
  throw new Error('refresh triggered a runtime start');
}}
await mod.unmount();
if (root.children.length !== 0) throw new Error('voice panel did not unmount');
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", probe],
            cwd=PROJECT_ROOT / "server",
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)


def check_stream_cancellation_and_duplicate_route_guard() -> None:
    async def cancellation_scenario():
        with tempfile.TemporaryDirectory(prefix="kei-voice-cancel-") as temp_dir:
            app = FastAPI()
            wait = asyncio.Event()
            tts = FakeTTS(wait=wait)
            app.state.voice_data_root = Path(temp_dir)
            app.state.voice_asr_provider = FakeASR()
            app.state.voice_conversation_provider = FakeConversation()
            app.state.voice_tts_provider = tts
            app.state.voice_pack_resolver = FakeVoicePackResolver()
            register_source_voice(app)
            stream = app.state.voice_service.stream(VoiceRequest(audio=b"x"))
            assert (await stream.__anext__())["event"] == "reply"
            pending = asyncio.create_task(stream.__anext__())
            for _ in range(100):
                if tts.calls:
                    break
                await asyncio.sleep(0)
            assert tts.calls
            pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass
            assert tts.cancelled
            assert not list((Path(temp_dir) / "output").glob("*.wav"))
            assert not any((Path(temp_dir) / "tmp").iterdir())
            await stream.aclose()
            await unregister_source_voice(app)

    asyncio.run(cancellation_scenario())

    with tempfile.TemporaryDirectory(prefix="kei-voice-duplicate-") as temp_dir:
        app = FastAPI()
        app.state.voice_data_root = Path(temp_dir)
        app.state.voice_conversation_provider = FakeConversation()
        register_source_voice(app)
        register_source_voice(app)
        paths = [route.path for route in app.routes]
        assert paths.count("/api/v1/voice/chat") == 1
        asyncio.run(unregister_source_voice(app))

        second = FastAPI()
        second.state.voice_data_root = Path(temp_dir) / "second"
        second.state.voice_conversation_provider = FakeConversation()
        from features.voice.router import create_voice_router

        second.include_router(create_voice_router(lambda: None))
        try:
            register_source_voice(second)
        except RuntimeError as exc:
            assert "already registered" in str(exc)
        else:
            raise AssertionError("duplicate voice routes were accepted")

        missing_asr = FastAPI()
        missing_asr.state.voice_data_root = Path(temp_dir) / "missing-asr"
        missing_asr.state.voice_conversation_provider = FakeConversation()
        register_source_voice(missing_asr)
        response = asyncio.run(
            call(
                missing_asr,
                "POST",
                "/api/v1/voice/chat",
                files={"file": ("sample.wav", b"audio", "audio/wav")},
            )
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "asr_unavailable"


def check_dynamic_voice_pack_resolver_binding() -> None:
    async def scenario(root: Path) -> None:
        chained = []

        def previous_consumer(candidate) -> None:
            chained.append(candidate)

        app = FastAPI()
        app.state.voice_data_root = root
        app.state.voice_asr_provider = FakeASR()
        app.state.voice_conversation_provider = FakeConversation()
        app.state.voice_tts_provider = FakeTTS()
        app.state.voice_pack_resolver_consumer = previous_consumer
        register_source_voice(app)

        binding = app.state.voice_pack_resolver_binding
        consumer = app.state.voice_pack_resolver_consumer
        assert binding.current() is None
        missing = await app.state.voice_service.chat(VoiceRequest(audio=b"x"))
        assert missing.mode == "text_only"
        assert missing.errors[0]["code"] == "voice_pack_unavailable"

        invalid = object()
        consumer(invalid)
        assert chained[-1] is invalid
        assert binding.current() is None

        first = BlockingVoicePackResolver("first")
        second = FakeVoicePackResolver()
        consumer(first)
        request = asyncio.create_task(
            app.state.voice_service.chat(VoiceRequest(audio=b"first"))
        )
        await first.started.wait()
        consumer(second)
        first.release.set()
        result = await request
        assert result.mode == "audio"
        assert app.state.voice_tts_provider.calls[-1][1].pack_id == "first"

        next_result = await app.state.voice_service.chat(
            VoiceRequest(audio=b"second")
        )
        assert next_result.mode == "audio"
        assert app.state.voice_tts_provider.calls[-1][1].pack_id == "fake-kei"

        consumer(None)
        assert binding.current() is None
        unbound = await app.state.voice_service.chat(VoiceRequest(audio=b"x"))
        assert unbound.mode == "text_only"
        assert unbound.errors[0]["code"] == "voice_pack_unavailable"

        voice_consumer = app.state.voice_pack_resolver_consumer
        downstream_calls = []

        def downstream_consumer(candidate) -> None:
            voice_consumer(candidate)
            downstream_calls.append(candidate)

        app.state.voice_pack_resolver_consumer = downstream_consumer
        await unregister_source_voice(app)
        assert app.state.voice_pack_resolver_consumer is downstream_consumer
        downstream_consumer(second)
        assert downstream_calls == [second]
        assert chained[-1] is second
        assert binding.current() is None

    with tempfile.TemporaryDirectory(prefix="kei-voice-resolver-binding-") as temp:
        asyncio.run(scenario(Path(temp)))

    with tempfile.TemporaryDirectory(prefix="kei-voice-registry-order-") as temp:
        root = Path(temp)
        manager = make_manager(root)
        conversation = write_conversation_fixture(root / "packages")
        voice = build_voice_package(root / "voice.zip")
        registry = build_voice_pack_registry_package(
            root / "voice_pack_registry.zip"
        )
        for package, module_id in (
            (conversation, "conversation"),
            (voice, "voice"),
            (registry, "voice_pack_registry"),
        ):
            manager.install(
                package,
                manager.calculate_package_sha256(package),
                expected_module_id=module_id,
            )
            manager.enable(module_id)

        app = FastAPI()
        app.state.voice_data_root = root / "voice-data"
        app.state.voice_asr_provider = FakeASR()
        app.state.voice_conversation_provider = FakeConversation()
        app.state.voice_tts_provider = FakeTTS()
        app.state.voice_pack_registry_path = root / "registry.json"
        app.state.voice_pack_runtime_root = root / "runtime-packs"
        results = InProcessModuleLoader().load(
            app,
            manager.enabled_in_process_descriptors(),
        )
        assert results == [
            {"module_id": "conversation", "status": "loaded"},
            {"module_id": "voice", "status": "loaded"},
            {"module_id": "voice_pack_registry", "status": "loaded"},
        ]
        assert (
            app.state.voice_service.voice_packs.current()
            is app.state.voice_pack_registry_service
        )
        app.state.voice_pack_resolver_consumer(None)
        assert app.state.voice_service.voice_packs.current() is None


def check_calendar_registry_contract_and_reverse_dependency() -> None:
    registry = CalendarSummaryProviderRegistry()
    assert registry.summary() == {
        "available": False,
        "error_code": "calendar_unavailable",
        "message": "",
        "skills": [],
    }

    class Provider:
        def __call__(self, day=None):
            return {
                "message": f"公开摘要 {day or 'today'}",
                "skills": [],
            }

    provider = Provider()
    registry.register_calendar_summary_provider(provider)
    assert registry.summary("2030-01-02")["message"] == "公开摘要 2030-01-02"
    registry.unregister_calendar_summary_provider(object())
    assert registry.summary()["available"] is True
    registry.unregister_calendar_summary_provider(provider)
    assert registry.summary()["error_code"] == "calendar_unavailable"

    failures = CalendarSummaryProviderRegistry()
    failures.register_calendar_summary_provider(
        lambda _day=None: (_ for _ in ()).throw(RuntimeError("private path"))
    )
    assert failures.summary()["error_code"] == "calendar_unavailable"

    concurrent = CalendarSummaryProviderRegistry()
    values = []
    errors = []
    lock = threading.Lock()

    def reader():
        try:
            for _ in range(300):
                value = concurrent.summary()
                with lock:
                    values.append(value["available"])
        except Exception as exc:
            errors.append(exc)

    def writer():
        for _ in range(100):
            concurrent.register_calendar_summary_provider(provider)
            concurrent.unregister_calendar_summary_provider(provider)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    threads.append(threading.Thread(target=writer))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors and values
    assert set(values) <= {True, False}

    calendar_summary_registry.unregister_calendar_summary_provider()
    assert get_calendar_summary()["error_code"] == "calendar_unavailable"
    legacy_source = (VOICE_ROOT / "legacy_pipeline.py").read_text(encoding="utf-8")
    assert "features.calendar" not in legacy_source
    assert "calendar.service" not in legacy_source
    package_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(VOICE_ROOT.rglob("*.py"))
        if "voice_packs" not in path.parts and "gpt_sovits" not in path.parts
    )
    assert "from features.calendar" not in package_sources
    assert "import features.calendar" not in package_sources


def main() -> int:
    check_deterministic_package_and_release_metadata()
    check_lifecycle_api_degradation_and_isolation()
    check_runtime_control_provider_and_guards()
    check_async_unregister_ownership_and_cleanup()
    check_dashboard_explicit_runtime_controls()
    check_stream_cancellation_and_duplicate_route_guard()
    check_dynamic_voice_pack_resolver_binding()
    check_calendar_registry_contract_and_reverse_dependency()
    print("installable voice module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
