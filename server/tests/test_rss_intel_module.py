"""Isolated installable-package checks for PK-134 RSS intelligence."""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.intel_contracts import (
    CollectRequest,
    CollectorRegistry,
    CollectorResult,
    CoverageStatus,
)
from core.modules import InProcessModuleLoader, ModuleManager
from features.rss_intel.module import (
    COLLECTOR_PROVIDER_STATE,
    OWNED_PROVIDER_STATE,
    SOURCE_CONFIG_PROVIDER_STATE,
    register,
    unregister,
)
from features.rss_intel import http_client as rss_http_client
from features.rss_intel.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_rss_intel_package,
    file_sha256,
)
from features.rss_intel.provider import RSSIntelCollectorProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = PROJECT_ROOT / "server" / "features" / "rss_intel"
RELEASE_FRAGMENT = FEATURE_ROOT / "release" / "official-release-fragment.json"
FIXED_TIME = datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc)
FEED_URL = "https://feed.example.test/money.xml"
FEED_XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Fixture Feed</title>
<item><guid>fixture-1</guid><title>Bootstrap revenue note</title>
<description>Deterministic fixture summary</description>
<link>https://article.example.test/fixture-1</link>
<pubDate>Thu, 30 Jul 2026 03:30:00 GMT</pubDate></item>
</channel></rss>"""
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


def _request() -> CollectRequest:
    return CollectRequest(
        local_date=date(2026, 7, 30),
        timezone="Asia/Shanghai",
        source_ids=("money",),
        lookback=24,
        source_config_snapshot={},
    )


def _manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def _write_intel_sources_fixture(root: Path) -> Path:
    package = root / "intel_sources-package"
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "intel_sources",
        "name": "Fixture intelligence sources",
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": [],
        "legacy_endpoints": [],
        "data_namespace": "intel_sources",
        "permissions": [],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (package / "backend" / "__init__.py").write_text(
        "def register(app):\n"
        "    app.state.intel_sources_fixture_registered = True\n",
        encoding="utf-8",
    )
    return package


def _install_dependencies(manager: ModuleManager, root: Path) -> None:
    dependency = _write_intel_sources_fixture(root)
    digest = manager.calculate_package_sha256(dependency)
    manager.install(dependency, digest, expected_module_id="intel_sources")
    manager.enable("intel_sources")


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
            assert info.create_version == 20
            assert info.extract_version == 20
            assert info.internal_attr == 0
            assert info.external_attr == 0o100644 << 16
            assert info.extra == b""
            assert info.comment == b""
            assert not info.filename.startswith(("/", "\\"))
            assert "\\" not in info.filename
            assert ".." not in Path(info.filename).parts
            combined.append(archive.read(info).decode("utf-8"))
    package_text = "\n".join(combined)
    assert "\r\n" not in package_text
    assert not re.search(r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b", package_text)
    assert not any(
        token in name.casefold()
        for name in names
        for token in (
            ".env",
            "cache",
            "credential",
            "fixture",
            "registry",
            "script",
            "test",
            "vendor",
        )
    )


def check_deterministic_package_and_release_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-rss-package-") as temp_dir:
        root = Path(temp_dir)
        first = build_rss_intel_package(root / "rss-first.zip")
        second = build_rss_intel_package(root / "rss-second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)

        with zipfile.ZipFile(first) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            dashboard = archive.read("dashboard/index.js").decode("utf-8")
        assert manifest["id"] == "rss_intel"
        assert manifest["version"] == OFFICIAL_RELEASE_VERSION
        assert manifest["dependencies"] == ["intel_sources"]
        assert manifest["api_namespaces"] == []
        assert manifest["legacy_endpoints"] == []
        assert manifest["permissions"] == []
        assert "context.request" not in dashboard
        assert "fetch(" not in dashboard
        assert "http://" not in dashboard and "https://" not in dashboard

    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "rss_intel"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["dependencies"] == ["intel_sources"]
    assert fragment["data_policy"] == "preserve_on_uninstall"
    assert fragment["requires_restart"] is True


async def check_missing_provider_is_zero_network() -> None:
    app = FastAPI()
    before_routes = tuple(route.path for route in app.routes)
    register(app)
    register(app)
    assert tuple(route.path for route in app.routes) == before_routes
    collector = app.state.intel_collector_registry.get("money")
    assert collector is app.state.rss_intel_collector
    result = await collector.collect(_request())
    assert result.coverage.status is CoverageStatus.NOT_CONFIGURED
    assert result.items == ()
    unregister(app)
    assert app.state.intel_collector_registry.get("money") is None
    assert not hasattr(app.state, COLLECTOR_PROVIDER_STATE)
    assert not hasattr(app.state, OWNED_PROVIDER_STATE)


def check_app_state_source_config_seam_and_errors() -> None:
    app = FastAPI()
    calls = []

    def source_config():
        calls.append("read")
        return {
            "rss_feeds": [FEED_URL],
            "keywords": ["bootstrap"],
            "allowed_redirect_hosts": ["redirect.example.test"],
        }

    setattr(app.state, SOURCE_CONFIG_PROVIDER_STATE, source_config)
    before_routes = tuple(route.path for route in app.routes)
    original_resolver = rss_http_client.socket.getaddrinfo
    rss_http_client.socket.getaddrinfo = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(AssertionError("registration attempted DNS"))
    )
    try:
        register(app)
    finally:
        rss_http_client.socket.getaddrinfo = original_resolver

    collector = app.state.intel_collector_registry.get("money")
    assert collector is not None
    assert collector._policy.feed_urls == (FEED_URL,)
    assert collector._keywords == ("bootstrap",)
    assert calls == ["read"]
    assert tuple(route.path for route in app.routes) == before_routes
    assert getattr(app.state, OWNED_PROVIDER_STATE) is True

    unregister(app)
    assert app.state.intel_collector_registry.get("money") is None
    assert getattr(app.state, SOURCE_CONFIG_PROVIDER_STATE) is source_config
    assert not hasattr(app.state, COLLECTOR_PROVIDER_STATE)
    assert not hasattr(app.state, OWNED_PROVIDER_STATE)
    assert tuple(route.path for route in app.routes) == before_routes

    invalid_callable = FastAPI()
    setattr(invalid_callable.state, SOURCE_CONFIG_PROVIDER_STATE, {"feed_urls": []})
    try:
        register(invalid_callable)
    except TypeError as exc:
        assert "must be callable" in str(exc)
    else:
        raise AssertionError("non-callable RSS source config provider was accepted")
    assert invalid_callable.state.intel_collector_registry.get("money") is None
    assert not hasattr(invalid_callable.state, COLLECTOR_PROVIDER_STATE)

    invalid_result = FastAPI()
    setattr(invalid_result.state, SOURCE_CONFIG_PROVIDER_STATE, lambda: [])
    try:
        register(invalid_result)
    except ValueError as exc:
        assert "must return a mapping" in str(exc)
    else:
        raise AssertionError("invalid RSS source config mapping was accepted")
    assert invalid_result.state.intel_collector_registry.get("money") is None
    assert not hasattr(invalid_result.state, COLLECTOR_PROVIDER_STATE)
    assert not hasattr(invalid_result.state, OWNED_PROVIDER_STATE)

    unknown_field = FastAPI()
    setattr(
        unknown_field.state,
        SOURCE_CONFIG_PROVIDER_STATE,
        lambda: {"rss_feeds": [], "user_url": "https://blocked.example.test/feed"},
    )
    try:
        register(unknown_field)
    except ValueError as exc:
        assert "unknown RSS app-state config field" in str(exc)
    else:
        raise AssertionError("unknown RSS app-state config field was accepted")
    assert unknown_field.state.intel_collector_registry.get("money") is None
    assert not hasattr(unknown_field.state, COLLECTOR_PROVIDER_STATE)


async def check_private_dns_and_redirect_escape() -> None:
    direct_seen = []

    def direct_handler(request: httpx.Request) -> httpx.Response:
        direct_seen.append(str(request.url))
        return httpx.Response(200, content=FEED_XML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(direct_handler)) as client:
        provider = RSSIntelCollectorProvider(
            lambda: {"feed_urls": [FEED_URL]},
            client=client,
            resolver=lambda _host: ("10.0.0.8",),
            clock=lambda: FIXED_TIME,
        )
        result = await provider.create_collector().collect(_request())
    assert result.coverage.status is CoverageStatus.FAILED
    assert direct_seen == []
    assert any("dns_rejected" in warning for warning in result.warnings)

    redirect_seen = []

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        redirect_seen.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://redirect.example.test/final.xml"},
        )

    def fake_dns(host: str):
        return ("127.0.0.1",) if host == "redirect.example.test" else ("93.184.216.34",)

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler)) as client:
        provider = RSSIntelCollectorProvider(
            lambda: {
                "feed_urls": [FEED_URL],
                "allowed_redirect_hosts": ["redirect.example.test"],
            },
            client=client,
            resolver=fake_dns,
            clock=lambda: FIXED_TIME,
        )
        result = await provider.create_collector().collect(_request())
    assert result.coverage.status is CoverageStatus.FAILED
    assert redirect_seen == [FEED_URL]
    assert any("dns_rejected" in warning for warning in result.warnings)


class _OtherCollector:
    source_id = "github"

    async def collect(self, request: CollectRequest) -> CollectorResult:
        raise AssertionError("unrelated Collector must not be called")


class _ExistingMoneyCollector:
    source_id = "money"

    async def collect(self, request: CollectRequest) -> CollectorResult:
        raise AssertionError("existing Collector must not be replaced")


async def check_lifecycle_failure_isolation_and_reinstall() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-rss-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = _manager(root)
        _install_dependencies(manager, root)
        package = build_rss_intel_package(root / OFFICIAL_ASSET_NAME)
        digest = file_sha256(package)
        installed = manager.install(package, digest, expected_module_id="rss_intel")
        assert installed["install_status"] == "installed_disabled"
        enabled = manager.enable("rss_intel")
        assert enabled["enabled"] is True
        assert enabled["restart_required"] is True

        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, content=FEED_XML)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            app = FastAPI()
            registry = CollectorRegistry()
            other = _OtherCollector()
            registry.register(other)
            app.state.intel_collector_registry = registry
            app.state.rss_intel_collector_provider = RSSIntelCollectorProvider(
                lambda: {
                    "feed_urls": [FEED_URL],
                    "keywords": ["bootstrap"],
                },
                client=client,
                resolver=lambda _host: ("93.184.216.34",),
                clock=lambda: FIXED_TIME,
            )
            before_routes = tuple(route.path for route in app.routes)
            results = InProcessModuleLoader().load(
                app,
                manager.enabled_in_process_descriptors(),
            )
            manager.record_load_results(results)
            assert {item["module_id"]: item["status"] for item in results} == {
                "intel_sources": "loaded",
                "rss_intel": "loaded",
            }, results
            assert tuple(route.path for route in app.routes) == before_routes
            assert registry.get("github") is other
            collected = await registry.get("money").collect(_request())
            assert collected.coverage.status is CoverageStatus.COMPLETE
            assert len(collected.items) == 1
            first_stable_id = collected.items[0].stable_id
            assert seen == [FEED_URL]

        module_data = root / "data" / "modules" / "rss_intel"
        module_data.mkdir(parents=True, exist_ok=True)
        sentinel = module_data / "preserved.txt"
        sentinel.write_text("temporary isolated state", encoding="utf-8")

        disabled = manager.disable("rss_intel")
        assert disabled["install_status"] == "installed_disabled"
        disabled_app = FastAPI()
        disabled_app.state.intel_collector_registry = CollectorRegistry()
        disabled_results = InProcessModuleLoader().load(
            disabled_app,
            manager.enabled_in_process_descriptors(),
        )
        assert [item["module_id"] for item in disabled_results] == ["intel_sources"]
        assert disabled_app.state.intel_collector_registry.get("money") is None

        uninstalled = manager.uninstall("rss_intel")
        assert uninstalled["data_preserved"] is True
        assert sentinel.read_text(encoding="utf-8") == "temporary isolated state"

        reinstalled = manager.install(package, digest, expected_module_id="rss_intel")
        assert reinstalled["install_status"] == "installed_disabled"
        manager.enable("rss_intel")
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=FEED_XML))
        ) as client:
            reinstalled_app = FastAPI()
            reinstalled_app.state.intel_collector_registry = CollectorRegistry()
            reinstalled_app.state.rss_intel_collector_provider = RSSIntelCollectorProvider(
                lambda: {"feed_urls": [FEED_URL], "keywords": ["bootstrap"]},
                client=client,
                resolver=lambda _host: ("93.184.216.34",),
                clock=lambda: FIXED_TIME,
            )
            reloaded = InProcessModuleLoader().load(
                reinstalled_app,
                manager.enabled_in_process_descriptors(),
            )
            assert {item["module_id"]: item["status"] for item in reloaded} == {
                "intel_sources": "loaded",
                "rss_intel": "loaded",
            }, reloaded
            restored = await reinstalled_app.state.intel_collector_registry.get(
                "money"
            ).collect(_request())
        assert restored.items[0].stable_id == first_stable_id
        assert sentinel.is_file()

        duplicate_app = FastAPI()
        duplicate_registry = CollectorRegistry()
        existing = _ExistingMoneyCollector()
        duplicate_registry.register(existing)
        duplicate_app.state.intel_collector_registry = duplicate_registry
        duplicate_app.state.rss_intel_collector_provider = RSSIntelCollectorProvider()
        duplicate_routes = tuple(route.path for route in duplicate_app.routes)
        duplicate_results = InProcessModuleLoader().load(
            duplicate_app,
            manager.enabled_in_process_descriptors(),
        )
        by_module = {item["module_id"]: item for item in duplicate_results}
        assert by_module["rss_intel"]["status"] == "failed"
        assert duplicate_registry.get("money") is existing
        assert tuple(route.path for route in duplicate_app.routes) == duplicate_routes


async def main() -> int:
    check_deterministic_package_and_release_metadata()
    await check_missing_provider_is_zero_network()
    check_app_state_source_config_seam_and_errors()
    await check_private_dns_and_redirect_escape()
    await check_lifecycle_failure_isolation_and_reinstall()
    print("PK-134 RSS installable module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
