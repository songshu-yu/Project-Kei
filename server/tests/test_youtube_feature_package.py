"""Isolated installable-package checks for the PK-131 YouTube Collector."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs

import _path_setup  # noqa: F401
import httpx
from fastapi import FastAPI

from core.intel_contracts import (
    CollectRequest,
    CollectorRegistry,
    CoverageStatus,
)
from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ModuleConflictError
from features.youtube import YouTubeCollector, register
from features.youtube.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_youtube_package,
    file_sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
YOUTUBE_ROOT = PROJECT_ROOT / "server" / "features" / "youtube"
RELEASE_ROOT = YOUTUBE_ROOT / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
CHANNEL_A = "UCaaaaaaaaaaaaaaaaaaaaaa"
CHANNEL_B = "UCbbbbbbbbbbbbbbbbbbbbbb"
VIDEO_ID = "abc123DEF45"
NOW = datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc)
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


class FakeCollector:
    source_id = "youtube"

    def __init__(self) -> None:
        self.collect_calls = 0

    async def collect(self, request: CollectRequest):
        self.collect_calls += 1
        raise AssertionError("module loading must not call the Collector")


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def write_dependency_package(root: Path) -> Path:
    package = root / "intel_sources-package"
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "intel_sources",
        "name": "Temporary intel sources dependency",
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": ["/api/v1/intel-sources"],
        "legacy_endpoints": [],
        "dashboard_entrypoint": None,
        "data_namespace": "intel_sources",
        "permissions": ["local_state"],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (package / "backend" / "__init__.py").write_text(
        "def register(app):\n    return None\n",
        encoding="utf-8",
    )
    return package


def install_dependency(manager: ModuleManager, root: Path) -> None:
    package = write_dependency_package(root)
    digest = manager.calculate_package_sha256(package)
    manager.install(package, digest, expected_module_id="intel_sources")
    manager.enable("intel_sources")


def restarted_app(
    manager: ModuleManager,
    collector: FakeCollector,
) -> tuple[FastAPI, list[dict[str, str]]]:
    app = FastAPI()
    app.state.collector_registry = CollectorRegistry()
    app.state.youtube_collector_provider = lambda: collector
    loader = InProcessModuleLoader()
    results = loader.load(app, manager.enabled_in_process_descriptors())
    manager.record_load_results(results)
    repeated = loader.load(app, manager.enabled_in_process_descriptors())
    assert all(item["status"] == "already_loaded" for item in repeated)
    return app, results


def assert_package_contents(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert names == EXPECTED_PACKAGE_NAMES
        for info in archive.infolist():
            assert info.date_time == FIXED_ZIP_DATETIME
            assert info.compress_type == zipfile.ZIP_STORED
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["id"] == "youtube"
        assert manifest["dependencies"] == ["intel_sources"]
        assert manifest["api_namespaces"] == []
        assert manifest["dashboard_entrypoint"] is None
        assert manifest["permissions"] == []
        lowered = "\n".join(names).casefold()
        for forbidden in (
            ".env",
            "channel_id",
            "cache",
            "cookie",
            "token",
            "vendor",
            "script",
            "test",
        ):
            assert forbidden not in lowered


def check_deterministic_package_and_release() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    expected_entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "youtube"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["dependencies"] == ["intel_sources"]
    assert fragment["data_policy"] == "preserve_on_uninstall"

    with tempfile.TemporaryDirectory(prefix="kei-youtube-deterministic-") as temp_dir:
        root = Path(temp_dir)
        first = build_youtube_package(root / "youtube-first.zip")
        second = build_youtube_package(root / "youtube-second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        assert_package_contents(first)

        materialized = build_youtube_package(root / "materialized")
        for path in materialized.rglob("*"):
            if path.is_file():
                assert b"\r\n" not in path.read_bytes()

        official = build_youtube_package(root / OFFICIAL_ASSET_NAME)
        with zipfile.ZipFile(official) as archive:
            manifest_raw = archive.read("manifest.json")
        assert expected_entry["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
        assert expected_entry["package_sha256"] == file_sha256(official)
        assert expected_entry["package_size"] == official.stat().st_size
        assert expected_entry["package_url"].endswith(
            f"/{OFFICIAL_RELEASE_TAG}/{OFFICIAL_ASSET_NAME}"
        )


def check_register_provider_and_duplicate_loading() -> None:
    collector = FakeCollector()
    app = SimpleNamespace(state=SimpleNamespace(
        collector_registry=CollectorRegistry(),
        youtube_collector_provider=lambda: collector,
    ))
    register(app)
    register(app)
    assert app.state.collector_registry.get("youtube") is collector
    assert app.state.youtube_collector is collector
    assert app.state.youtube_module_registered is True
    assert collector.collect_calls == 0


def check_dependency_gate() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-youtube-dependency-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_youtube_package(root / OFFICIAL_ASSET_NAME)
        manager.install(package, file_sha256(package), expected_module_id="youtube")
        try:
            manager.enable("youtube")
        except ModuleConflictError as exc:
            assert "intel_sources" in str(exc)
        else:
            raise AssertionError("youtube enabled without its intel_sources dependency")


def check_lifecycle_preserves_data() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-youtube-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        install_dependency(manager, root)
        package = build_youtube_package(root / OFFICIAL_ASSET_NAME)
        digest = file_sha256(package)

        installed = manager.install(package, digest, expected_module_id="youtube")
        assert installed["install_status"] == "installed_disabled"
        assert installed["enabled"] is False
        enabled = manager.enable("youtube")
        assert enabled["enabled"] is True and enabled["restart_required"] is True

        collector = FakeCollector()
        app, results = restarted_app(manager, collector)
        assert results == [
            {"module_id": "intel_sources", "status": "loaded"},
            {"module_id": "youtube", "status": "loaded"},
        ]
        assert app.state.collector_registry.get("youtube") is collector
        assert collector.collect_calls == 0
        route_paths = tuple(route.path for route in app.routes)
        assert not any(path.startswith("/api/v1/youtube") for path in route_paths)

        source_config = root / "data" / "intel_sources.json"
        source_config.parent.mkdir(parents=True, exist_ok=True)
        source_config.write_bytes(b'{"youtube_channel_ids":["temporary-fixture"]}')
        module_data = root / "data" / "modules" / "youtube"
        module_data.mkdir(parents=True)
        cache = module_data / "isolated-cache.json"
        cache.write_bytes(b'{"fixture":true}')
        source_before = source_config.read_bytes()
        cache_before = cache.read_bytes()

        disabled = manager.disable("youtube")
        assert disabled["enabled"] is False and disabled["restart_required"] is True
        disabled_app, disabled_results = restarted_app(manager, FakeCollector())
        assert disabled_results == [
            {"module_id": "intel_sources", "status": "loaded"},
        ]
        assert disabled_app.state.collector_registry.get("youtube") is None

        removed = manager.uninstall("youtube")
        assert removed["data_preserved"] is True
        assert source_config.read_bytes() == source_before
        assert cache.read_bytes() == cache_before

        reinstalled = manager.install(package, digest, expected_module_id="youtube")
        assert reinstalled["install_status"] == "installed_disabled"
        manager.enable("youtube")
        restored_collector = FakeCollector()
        restored_app, restored_results = restarted_app(manager, restored_collector)
        assert restored_results[-1] == {"module_id": "youtube", "status": "loaded"}
        assert restored_app.state.collector_registry.get("youtube") is restored_collector
        assert source_config.read_bytes() == source_before
        assert cache.read_bytes() == cache_before


def atom_feed(channel_id: str, video_id: str = VIDEO_ID) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015">
  <yt:channelId>{channel_id}</yt:channelId>
  <title>Temporary channel</title>
  <entry>
    <yt:videoId>{video_id}</yt:videoId>
    <yt:channelId>{channel_id}</yt:channelId>
    <title>Temporary video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v={video_id}" />
    <author><name>Temporary channel</name></author>
    <published>2026-07-30T07:30:00Z</published>
  </entry>
</feed>"""


async def check_mocktransport_missing_config_and_failure_isolation() -> None:
    calls = []

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("missing configuration must remain zero-network")

    request = CollectRequest(
        local_date=date(2026, 7, 30),
        timezone="Asia/Shanghai",
        source_ids=("youtube",),
        source_config_snapshot={},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        missing = await YouTubeCollector(
            client=client,
            clock=lambda: NOW,
            request_interval_seconds=0,
        ).collect(request)
    assert missing.coverage.status is CoverageStatus.NOT_CONFIGURED
    assert calls == []

    def mixed(request: httpx.Request) -> httpx.Response:
        channel_id = parse_qs(request.url.query.decode())["channel_id"][0]
        if channel_id == CHANNEL_B:
            raise httpx.ReadTimeout("temporary secret body", request=request)
        return httpx.Response(200, text=atom_feed(CHANNEL_A))

    configured = CollectRequest(
        local_date=date(2026, 7, 30),
        timezone="Asia/Shanghai",
        source_ids=("youtube",),
        source_config_snapshot={"youtube_channel_ids": [CHANNEL_A, CHANNEL_B]},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(mixed)) as client:
        partial = await YouTubeCollector(
            client=client,
            clock=lambda: NOW,
            request_interval_seconds=0,
        ).collect(configured)
    assert partial.coverage.status is CoverageStatus.PARTIAL
    assert len(partial.items) == 1
    assert all("temporary secret body" not in warning for warning in partial.warnings)
    assert all(CHANNEL_A not in warning and CHANNEL_B not in warning for warning in partial.warnings)


async def main() -> int:
    check_register_provider_and_duplicate_loading()
    check_deterministic_package_and_release()
    check_dependency_gate()
    check_lifecycle_preserves_data()
    await check_mocktransport_missing_config_and_failure_isolation()
    print("youtube installable package tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
