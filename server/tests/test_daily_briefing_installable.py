"""PK-011 isolated checks for the installable daily-briefing package."""
from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

import core.intel_contracts as core_contracts
import features.daily_briefing.collector_contracts as legacy_protocols
import features.daily_briefing.models as legacy_models
import features.daily_briefing.time_utils as legacy_time
from core.intel_contracts import (
    CacheStatus,
    CollectorRegistry,
    CollectorResult,
    CoverageStatus,
    IntelItem,
    SourceCoverage,
    rfc3339,
)
from core.modules import InProcessModuleLoader, ModuleManager
from features.daily_briefing.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    build_daily_briefing_package,
    file_sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
FEATURE_ROOT = SERVER_ROOT / "features" / "daily_briefing"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_FILES),
}
FIXED_NOW = datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc)


class FakeCollector:
    source_id = "github"

    def __init__(self) -> None:
        self.calls = 0

    async def collect(self, request):
        self.calls += 1
        fetched_at = rfc3339(FIXED_NOW)
        return CollectorResult(
            source_id=self.source_id,
            items=(
                IntelItem(
                    stable_id="github:fixture",
                    source_id="github",
                    category="development",
                    title="isolated package item",
                    summary="safe summary",
                    url="https://example.test/item",
                    author="fixture",
                    published_at=fetched_at,
                    fetched_at=fetched_at,
                    metadata={"fixture": True},
                ),
            ),
            warnings=(),
            coverage=SourceCoverage(CoverageStatus.COMPLETE, 1),
            fetched_at=fetched_at,
            cache_status=CacheStatus.FETCHED,
        )


class FailingCollector:
    source_id = "twitter"

    async def collect(self, _request):
        raise RuntimeError("Authorization=fictional-secret-body")


class FakeVoice:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def synthesize_briefing(self, _text: str, *, local_date: str):
        self.calls += 1
        return {
            "audio_available": True,
            "audio_path": f"/api/v1/voice/audio/{self.name}-{local_date}.wav",
            "mode": "audio",
            "degraded": False,
            "errors": [],
        }


class BlockingVoice(FakeVoice):
    def __init__(
        self,
        name: str,
        started: asyncio.Event,
        release: asyncio.Event,
    ) -> None:
        super().__init__(name)
        self.started = started
        self.release = release

    async def synthesize_briefing(self, text: str, *, local_date: str):
        self.started.set()
        await self.release.wait()
        return await super().synthesize_briefing(
            text,
            local_date=local_date,
        )


class MalformedVoice:
    async def synthesize_briefing(self, _text: str, *, local_date: str):
        del local_date
        return {
            "errors": [{
                "message": "Authorization=fictional-provider-secret",
            }],
        }


class StructuralTTS:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests = []

    async def synthesize(self, request, voice_pack):
        self.requests.append((request, voice_pack))
        if self.fail:
            raise RuntimeError("Token=fictional-tts-secret")
        assert request.text
        return SimpleNamespace(audio=b"RIFF-fake-briefing")

    async def cancel(self, _request_id: str) -> None:
        return None


class StructuralVoicePacks:
    async def resolve_active_pack(self):
        return SimpleNamespace(pack_id="fake-pack")

    async def cancel(self, _request_id: str) -> None:
        return None


class StructuralArtifactSession:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def publish(self, audio: bytes, *, index: int) -> str:
        assert audio == b"RIFF-fake-briefing"
        assert index == 1
        return "briefing_fake.wav"

    def commit(self) -> None:
        self.committed = True

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class StructuralArtifacts:
    def __init__(self) -> None:
        self.sessions = []

    def session(self, _request_id: str):
        session = StructuralArtifactSession()
        self.sessions.append(session)
        return session


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


def load_app(
    manager: ModuleManager,
    root_dir: Path,
    registry: CollectorRegistry,
) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    app.state.daily_briefing_root_dir = root_dir
    app.state.daily_briefing_clock = lambda: FIXED_NOW
    app.state.daily_briefing_local_request_guard = lambda _request: True
    app.state.daily_briefing_source_config_provider = lambda: {}
    app.state.intel_collector_registry = registry
    results = InProcessModuleLoader().load(
        app,
        manager.enabled_in_process_descriptors(),
    )
    manager.record_load_results(results)
    return app, results


def check_core_contract_identity_and_dependency_direction() -> None:
    assert legacy_models.CollectRequest is core_contracts.CollectRequest
    assert legacy_models.CollectorResult is core_contracts.CollectorResult
    assert legacy_models.IntelItem is core_contracts.IntelItem
    assert legacy_models.SourceCoverage is core_contracts.SourceCoverage
    assert legacy_protocols.Collector is core_contracts.Collector
    assert legacy_protocols.CollectorGateway is core_contracts.CollectorGateway
    assert legacy_time.get_timezone is core_contracts.get_timezone
    assert legacy_time.localize is core_contracts.localize

    forbidden = (
        "features.daily_briefing.models",
        "features.daily_briefing.collector_contracts",
        "features.daily_briefing.time_utils",
    )
    roots = (
        SERVER_ROOT / "features" / "bilibili",
        SERVER_ROOT / "features" / "github_intel",
        SERVER_ROOT / "features" / "intel_sources",
        SERVER_ROOT / "features" / "papers",
        SERVER_ROOT / "features" / "rss_intel",
        SERVER_ROOT / "features" / "x_monitor",
        SERVER_ROOT / "features" / "youtube",
        SERVER_ROOT / "intel" / "collectors",
        SERVER_ROOT / "services",
    )
    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if any(value in text for value in forbidden):
                offenders.append(path.relative_to(SERVER_ROOT).as_posix())
    assert offenders == []


def check_deterministic_package_and_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-briefing-build-") as temp_dir:
        root = Path(temp_dir)
        first = build_daily_briefing_package(root / "first.zip")
        second = build_daily_briefing_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        with zipfile.ZipFile(first) as archive:
            assert set(archive.namelist()) == EXPECTED_PACKAGE_NAMES
            for info in archive.infolist():
                assert info.date_time == FIXED_ZIP_DATETIME
                assert not info.filename.startswith("/")
                assert ".." not in Path(info.filename).parts
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["id"] == "daily_briefing"
            assert manifest["version"] == "1.0.3"
            assert manifest["dependencies"] == []
            assert {
                "x_monitor", "bilibili", "youtube", "github_intel",
                "papers", "rss_intel", "conversation", "voice",
                "life_forecast",
            } <= set(manifest["optional_dependencies"])
            combined = b"\n".join(
                archive.read(name)
                for name in archive.namelist()
            ).lower()
            for forbidden in (
                b"briefing_cache/202",
                b"intel_sources.json",
                b".env",
                b"node_modules",
                b"vendor/",
            ):
                assert forbidden not in combined
            assert b"from features.voice" not in archive.read(
                "backend/voice_adapter.py"
            )
            assert b"import features.voice" not in archive.read(
                "backend/voice_adapter.py"
            )


def check_release_metadata_matches_package() -> None:
    release_root = FEATURE_ROOT / "release"
    fragment = json.loads(
        (release_root / "official-release-fragment.json").read_text(
            encoding="utf-8"
        )
    )
    entry = json.loads(
        (release_root / "official-catalog-entry.json").read_text(
            encoding="utf-8"
        )
    )
    with tempfile.TemporaryDirectory(prefix="kei-briefing-release-") as temp_dir:
        package = build_daily_briefing_package(
            Path(temp_dir) / fragment["asset_name"]
        )
        with zipfile.ZipFile(package) as archive:
            manifest_bytes = archive.read("manifest.json")
        assert entry["package_sha256"] == file_sha256(package)
        assert entry["manifest_sha256"] == hashlib.sha256(
            manifest_bytes
        ).hexdigest()
        assert entry["package_size"] == package.stat().st_size
    for key in (
        "module_id",
        "name",
        "version",
        "core_compatibility",
        "release_tag",
        "asset_name",
        "dependencies",
        "optional_dependencies",
        "conflicts",
        "permissions",
        "data_policy",
        "requires_restart",
    ):
        assert entry[key] == fragment[key]


async def _check_lazy_voice_provider_lifecycle(app: FastAPI) -> None:
    endpoint = "/briefing/today/voice?fetch=false&rewrite=true"

    missing = await call(app, "POST", endpoint)
    assert missing.status_code == 200
    assert missing.json()["audio_available"] is False
    assert missing.json()["mode"] == "text_only"
    assert missing.json()["degraded"] is True

    structural_tts = StructuralTTS()
    structural_artifacts = StructuralArtifacts()
    app.state.voice_service = SimpleNamespace(
        tts=structural_tts,
        voice_packs=StructuralVoicePacks(),
        artifacts=structural_artifacts,
    )
    structurally_loaded = await call(app, "POST", endpoint)
    assert structurally_loaded.status_code == 200
    assert structurally_loaded.json()["audio_available"] is True
    assert structurally_loaded.json()["audio_path"].endswith(
        "/briefing_fake.wav"
    )
    assert len(structural_tts.requests) == 1
    assert structural_artifacts.sessions[0].committed is True

    delattr(app.state, "voice_service")
    structurally_unloaded = await call(app, "POST", endpoint)
    assert structurally_unloaded.status_code == 200
    assert structurally_unloaded.json()["audio_available"] is False
    assert structurally_unloaded.json()["errors"][0]["code"] == (
        "voice_unavailable"
    )

    app.state.voice_service = SimpleNamespace(
        tts=StructuralTTS(fail=True),
        voice_packs=StructuralVoicePacks(),
        artifacts=StructuralArtifacts(),
    )
    structurally_failed = await call(app, "POST", endpoint)
    structurally_failed_text = json.dumps(structurally_failed.json())
    assert structurally_failed.status_code == 200
    assert structurally_failed.json()["audio_available"] is False
    assert structurally_failed.json()["errors"][0]["code"] == "voice_failed"
    assert "fictional-tts-secret" not in structurally_failed_text
    delattr(app.state, "voice_service")

    late_voice = FakeVoice("late")
    app.state.daily_briefing_voice_provider = lambda: late_voice
    late = await call(app, "POST", endpoint)
    assert late.status_code == 200
    assert late.json()["audio_available"] is True
    assert "/late-" in late.json()["audio_path"]
    assert late_voice.calls == 1

    app.state.daily_briefing_voice_provider = None
    removed = await call(app, "POST", endpoint)
    assert removed.status_code == 200
    assert removed.json()["audio_available"] is False
    assert removed.json()["mode"] == "text_only"

    def broken_factory():
        raise RuntimeError("Cookie=fictional-factory-secret")

    app.state.daily_briefing_voice_provider = broken_factory
    broken = await call(app, "POST", endpoint)
    broken_text = json.dumps(broken.json())
    assert broken.status_code == 200
    assert broken.json()["audio_available"] is False
    assert "fictional-factory-secret" not in broken_text

    app.state.daily_briefing_voice_provider = MalformedVoice()
    malformed = await call(app, "POST", endpoint)
    malformed_text = json.dumps(malformed.json())
    assert malformed.status_code == 200
    assert malformed.json()["audio_available"] is False
    assert malformed.json()["errors"][0]["code"] == "voice_failed"
    assert "fictional-provider-secret" not in malformed_text

    first_started = asyncio.Event()
    first_release = asyncio.Event()
    second_started = asyncio.Event()
    second_release = asyncio.Event()
    first_voice = BlockingVoice("first", first_started, first_release)
    second_voice = BlockingVoice("second", second_started, second_release)
    app.state.daily_briefing_voice_provider = lambda: first_voice
    first_task = asyncio.create_task(call(app, "POST", endpoint))
    await asyncio.wait_for(first_started.wait(), timeout=2)
    app.state.daily_briefing_voice_provider = lambda: second_voice
    second_task = asyncio.create_task(call(app, "POST", endpoint))
    await asyncio.wait_for(second_started.wait(), timeout=2)
    second_release.set()
    second = await asyncio.wait_for(second_task, timeout=2)
    first_release.set()
    first = await asyncio.wait_for(first_task, timeout=2)
    assert "/first-" in first.json()["audio_path"]
    assert "/second-" in second.json()["audio_path"]
    assert first_voice.calls == 1
    assert second_voice.calls == 1

    app.state.daily_briefing_voice_provider = None


def check_lifecycle_optional_sources_and_cache() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-briefing-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_daily_briefing_package(root / "daily-briefing.zip")
        digest = file_sha256(package)

        core_only = FastAPI()
        response = asyncio.run(
            call(core_only, "GET", "/api/v1/briefing/today")
        )
        assert response.status_code == 404

        installed = manager.install(
            package,
            digest,
            expected_module_id="daily_briefing",
        )
        assert installed["install_status"] == "installed_disabled"
        manager.enable("daily_briefing")

        module_root = root / "isolated-module-root"
        cache_root = module_root / "data" / "briefing_cache"
        registry = CollectorRegistry()
        success = FakeCollector()
        registry.register(success)
        registry.register(FailingCollector())
        app, results = load_app(manager, module_root, registry)
        assert results == [
            {"module_id": "daily_briefing", "status": "loaded"}
        ], results

        read = asyncio.run(call(app, "GET", "/api/v1/briefing/today"))
        assert read.status_code == 200
        assert read.json()["ready"] is False
        assert success.calls == 0

        generated = asyncio.run(call(
            app,
            "POST",
            "/api/v1/briefing/generate",
            json={
                "source_ids": ["github", "twitter", "youtube"],
                "refresh": False,
                "rewrite": True,
                "rewrite_refresh": False,
                "patch_missing": False,
                "lookback": 24,
            },
        ))
        assert generated.status_code == 200
        payload = generated.json()
        assert payload["ready"] is True
        assert payload["coverage"]["github"]["status"] == "complete"
        assert payload["coverage"]["twitter"]["status"] == "failed"
        assert payload["coverage"]["youtube"]["status"] == "not_configured"
        assert payload["generated"] is False
        assert payload["fallback"] is True
        assert "fictional-secret-body" not in json.dumps(payload)
        assert success.calls == 1

        cached = asyncio.run(call(app, "GET", "/api/v1/briefing/today"))
        assert cached.status_code == 200 and cached.json()["ready"] is True
        assert success.calls == 1

        asyncio.run(_check_lazy_voice_provider_lifecycle(app))
        assert success.calls == 1

        cache_files = list(cache_root.glob("*.json"))
        assert cache_files
        before = {path.name: path.read_bytes() for path in cache_files}

        disabled = manager.disable("daily_briefing")
        assert disabled["restart_required"] is True
        disabled_app, disabled_results = load_app(
            manager,
            module_root,
            CollectorRegistry(),
        )
        assert disabled_results == []
        assert asyncio.run(
            call(disabled_app, "GET", "/api/v1/briefing/today")
        ).status_code == 404

        removed = manager.uninstall("daily_briefing")
        assert removed["data_preserved"] is True
        assert {
            path.name: path.read_bytes()
            for path in cache_root.glob("*.json")
        } == before

        manager.install(
            package,
            digest,
            expected_module_id="daily_briefing",
        )
        manager.enable("daily_briefing")
        restored_app, restored_results = load_app(
            manager,
            module_root,
            CollectorRegistry(),
        )
        assert restored_results == [
            {"module_id": "daily_briefing", "status": "loaded"}
        ]
        restored = asyncio.run(
            call(restored_app, "GET", "/api/v1/briefing/today")
        )
        assert restored.status_code == 200
        assert restored.json()["ready"] is True


def main() -> int:
    check_core_contract_identity_and_dependency_direction()
    check_deterministic_package_and_manifest()
    check_release_metadata_matches_package()
    check_lifecycle_optional_sources_and_cache()
    print("daily briefing installable tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
