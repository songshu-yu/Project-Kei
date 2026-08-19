"""Isolated lifecycle and package checks for installable x_monitor."""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import json
import os
import re
import tempfile
import zipfile
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.intel_contracts import CollectRequest, CollectorRegistry
from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ModuleConflictError
from features.x_monitor.package_builder import (
    BACKEND_SOURCES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_x_monitor_package,
    file_sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
RELEASE_ROOT = SERVER_ROOT / "features" / "x_monitor" / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
FIXED_NOW = datetime(2026, 7, 22, 0, 30, tzinfo=timezone.utc)
PROTECTED_PATHS = tuple(
    (SERVER_ROOT / relative).absolute()
    for relative in (
        "data/intel_sources.json",
        "data/x_profiles.json",
        "data/x_daily_posts.json",
        "data/x_daily_replies.json",
        ".env",
        "systems/data/demon_slayer.json",
        "systems/data/focus_timer.json",
        "systems/data/calendar_memo.json",
        "data/fitness_checkins.json",
    )
)


def _absolute(value: object) -> Path | None:
    if isinstance(value, int):
        return None
    try:
        return Path(value).absolute()
    except TypeError:
        return None


@contextmanager
def protected_path_tripwire(temp_root: Path):
    hits: list[str] = []
    outside_writes: list[str] = []
    system_temp_root = Path(tempfile.gettempdir()).absolute()
    original_builtin_open = builtins.open
    original_path_open = Path.open
    original_os_open = os.open
    original_replace = os.replace

    def inspect(path: object, *, writing: bool = False) -> None:
        candidate = _absolute(path)
        if candidate is None:
            return
        if candidate in PROTECTED_PATHS:
            hits.append(str(candidate))
            raise AssertionError(f"protected path accessed: {candidate}")
        allowed = (
            candidate == temp_root
            or temp_root in candidate.parents
            or candidate == system_temp_root
            or system_temp_root in candidate.parents
        )
        if writing and not allowed:
            outside_writes.append(str(candidate))
            raise AssertionError(f"write escaped temporary root: {candidate}")

    def guarded_builtin_open(file, mode="r", *args, **kwargs):
        inspect(file, writing=any(flag in str(mode) for flag in "wax+"))
        return original_builtin_open(file, mode, *args, **kwargs)

    def guarded_path_open(self, mode="r", *args, **kwargs):
        inspect(self, writing=any(flag in str(mode) for flag in "wax+"))
        return original_path_open(self, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        inspect(path, writing=writing)
        return original_os_open(path, flags, *args, **kwargs)

    def guarded_replace(source, destination, *args, **kwargs):
        inspect(source)
        inspect(destination, writing=True)
        return original_replace(source, destination, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch("builtins.open", guarded_builtin_open))
        stack.enter_context(patch.object(Path, "open", guarded_path_open))
        stack.enter_context(patch("os.open", guarded_os_open))
        stack.enter_context(patch("os.replace", guarded_replace))
        yield hits, outside_writes


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
    ) as client:
        return await client.request(method, path, **kwargs)


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def write_dependency_package(root: Path) -> Path:
    package = root / "intel_sources"
    package.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "intel_sources",
        "name": "isolated intel sources",
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
        "data_namespace": "intel_sources",
        "permissions": ["local_state"],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (package / "backend.py").write_text(
        "def register(app):\n    app.state.intel_sources_fixture_loaded = True\n",
        encoding="utf-8",
    )
    return package


def _assert_package_contents(package: Path) -> None:
    expected = {
        "manifest.json",
        "dashboard/index.js",
        *(f"backend/{name}" for name in BACKEND_SOURCES),
    }
    with zipfile.ZipFile(package) as archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        names = {item.filename for item in infos}
        assert names == expected
        assert len(names) == len({name.casefold() for name in names})
        content = []
        for item in infos:
            assert item.date_time == FIXED_ZIP_DATETIME
            assert item.compress_type == zipfile.ZIP_STORED
            assert item.external_attr == 0o100644 << 16
            assert "\\" not in item.filename and ".." not in Path(item.filename).parts
            content.append(archive.read(item).decode("utf-8"))
    text = "\n".join(content)
    assert "\r\n" not in text
    assert "features.daily_briefing" not in text
    assert "features.intel_sources" not in text
    assert "intel.intel_config" not in text
    assert "from services." not in text
    assert "from intel.collectors." not in text
    assert not re.search(r"(?i)\b[A-Z]:[\\/](?:Users|Desktop|AppData|Temp)\b", text)
    lowered_names = "\n".join(names).casefold()
    for forbidden in (
        ".env",
        "x_profiles.json",
        "x_daily_posts.json",
        "x_daily_replies.json",
        "intel_sources.json",
        "cookie",
        "token",
        "vendor",
        "fixture",
        "script",
    ):
        assert forbidden not in lowered_names


def check_deterministic_package_and_release() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "x_monitor"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["dependencies"] == ["intel_sources"]
    assert fragment["data_policy"] == "preserve_on_uninstall"
    with tempfile.TemporaryDirectory(prefix="kei-x-monitor-build-") as temp_dir:
        root = Path(temp_dir)
        first = build_x_monitor_package(root / "first.zip")
        second = build_x_monitor_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)

        output = root / "official-catalog.json"
        asset_root = root / "assets"
        asset_root.mkdir()
        asset = build_x_monitor_package(asset_root / OFFICIAL_ASSET_NAME)
        import subprocess
        import sys

        completed = subprocess.run(
            [
                sys.executable,
                str(CATALOG_BUILDER),
                "--fragment",
                str(RELEASE_FRAGMENT),
                "--asset-root",
                str(asset_root),
                "--output",
                str(output),
                "--generated-at",
                "2026-07-30T00:00:00Z",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)
        generated = json.loads(output.read_text(encoding="utf-8"))["modules"][0]
        expected = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
        assert generated == expected
        assert generated["package_sha256"] == file_sha256(asset)
        with zipfile.ZipFile(asset) as archive:
            manifest_bytes = archive.read("manifest.json")
        assert generated["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()


def _rss_fixture() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<rss><channel><title>Alice (@Alice)</title>
<item><title>Collector fixture</title>
<link>https://nitter.net/Alice/status/900</link>
<guid>https://nitter.net/Alice/status/900</guid>
<pubDate>Wed, 22 Jul 2026 00:10:00 GMT</pubDate>
<description><![CDATA[Collector fixture]]></description></item>
</channel></rss>"""


def restarted_app(manager: ModuleManager, root: Path, counters: dict[str, int]):
    async def profile_fetcher(username: str):
        counters["profile"] += 1
        return {
            "username": username,
            "name": "Alice Fixture",
            "avatar_url": "https://example.test/avatar.png",
        }

    async def query_fetcher(username: str, start_at: datetime, end_at: datetime):
        counters["query"] += 1
        return {
            "items": [{
                "id": f"{username}-1",
                "kind": "reply",
                "content": "isolated query fixture",
                "url": f"https://nitter.net/{username}/status/1",
                "published_at": start_at.replace(hour=8).isoformat(),
            }],
            "coverage": {"status": "partial", "detail": "fixture"},
            "warnings": ["fixture partial"],
        }

    def collector_transport(request: httpx.Request) -> httpx.Response:
        counters["collector"] += 1
        if request.url.path != "/Alice/rss":
            raise AssertionError(f"unexpected collector request: {request.url}")
        return httpx.Response(200, content=_rss_fixture())

    app = FastAPI()
    app.state.intel_source_snapshot_provider = lambda: {
        "twitter_users": ["Alice"],
        "money_twitter_users": [],
    }
    app.state.intel_collector_registry = CollectorRegistry()
    app.state.x_monitor_profile_path = root / "state" / "x_profiles.json"
    app.state.x_monitor_posts_path = root / "state" / "x_daily_posts.json"
    app.state.x_monitor_clock = lambda: FIXED_NOW
    app.state.x_monitor_profile_fetcher = profile_fetcher
    app.state.x_monitor_posts_query_fetcher = query_fetcher
    app.state.x_monitor_collector_client = httpx.AsyncClient(
        transport=httpx.MockTransport(collector_transport)
    )
    results = InProcessModuleLoader().load(
        app,
        manager.enabled_in_process_descriptors(),
    )
    manager.record_load_results(results)
    return app, results


def check_lifecycle_provider_and_isolation() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-x-monitor-lifecycle-") as temp_dir:
        root = Path(temp_dir).absolute()
        counters = {"profile": 0, "query": 0, "collector": 0}
        with protected_path_tripwire(root) as (hits, outside_writes):
            manager = make_manager(root)
            dependency = write_dependency_package(root / "packages")
            dependency_hash = manager.calculate_package_sha256(dependency)
            manager.install(
                dependency,
                dependency_hash,
                expected_module_id="intel_sources",
            )
            manager.enable("intel_sources")
            package = build_x_monitor_package(root / OFFICIAL_ASSET_NAME)
            digest = file_sha256(package)
            installed = manager.install(
                package,
                digest,
                expected_module_id="x_monitor",
            )
            assert installed["install_status"] == "installed_disabled"
            enabled = manager.enable("x_monitor")
            assert enabled["restart_required"] is True

            app, results = restarted_app(manager, root, counters)
            assert results == [
                {"module_id": "intel_sources", "status": "loaded"},
                {"module_id": "x_monitor", "status": "loaded"},
            ], results
            paths = {route.path for route in app.routes}
            assert {
                "/api/v1/x/profiles",
                "/api/v1/x/profiles/resolve",
                "/api/v1/x/posts",
                "/api/v1/x/posts/fetch",
                "/api/v1/x/posts/query",
                "/dashboard/intel-sources/x-profiles/resolve",
                "/dashboard/intel-sources/x-posts",
                "/dashboard/intel-sources/x-posts/fetch",
            } <= paths

            assert asyncio.run(call(app, "GET", "/api/v1/x/profiles")).status_code == 200
            assert asyncio.run(call(app, "GET", "/api/v1/x/posts")).status_code == 200
            assert counters == {"profile": 0, "query": 0, "collector": 0}

            resolved = asyncio.run(call(
                app,
                "POST",
                "/api/v1/x/profiles/resolve?username=Alice&refresh=true",
            ))
            assert resolved.status_code == 200 and counters["profile"] == 1
            query = asyncio.run(call(
                app,
                "POST",
                "/api/v1/x/posts/query",
                json={"username": "Alice", "mode": "day", "date": "2026-07-22"},
            ))
            assert query.status_code == 200
            assert query.json()["items"][0]["kind"] == "reply"
            assert counters["query"] == 1
            assert not (root / "state" / "x_daily_posts.json").exists()

            legacy = asyncio.run(call(
                app,
                "POST",
                "/dashboard/intel-sources/x-posts/fetch?username=Alice",
            ))
            assert legacy.status_code == 200 and counters["query"] == 2
            posts_path = root / "state" / "x_daily_posts.json"
            profiles_path = root / "state" / "x_profiles.json"
            preserved_posts = posts_path.read_bytes()
            preserved_profiles = profiles_path.read_bytes()

            collector = app.state.intel_collector_registry.get("twitter")
            result = asyncio.run(collector.collect(CollectRequest(
                local_date=date(2026, 7, 22),
                timezone="Asia/Shanghai",
                source_ids=("twitter",),
                lookback=24,
                source_config_snapshot={
                    "twitter_users": ["Alice"],
                    "money_twitter_users": [],
                },
            )))
            assert result.source_id == "twitter"
            assert len(result.items) == 1
            assert counters["collector"] == 1

            duplicate_app = FastAPI()
            duplicate_app.add_api_route("/api/v1/x/posts", lambda: {})
            duplicate_app.state.intel_source_snapshot_provider = (
                app.state.intel_source_snapshot_provider
            )
            duplicate_app.state.intel_collector_registry = CollectorRegistry()
            duplicate_results = InProcessModuleLoader().load(
                duplicate_app,
                [
                    descriptor
                    for descriptor in manager.enabled_in_process_descriptors()
                    if descriptor["manifest"]["id"] == "x_monitor"
                ],
            )
            assert duplicate_results[0]["status"] == "failed", duplicate_results

            manager.disable("x_monitor")
            manager.uninstall("x_monitor")
            assert profiles_path.read_bytes() == preserved_profiles
            assert posts_path.read_bytes() == preserved_posts
            manager.install(package, digest, expected_module_id="x_monitor")
            manager.enable("x_monitor")
            restored_app, restored_results = restarted_app(manager, root, counters)
            assert restored_results[-1] == {"module_id": "x_monitor", "status": "loaded"}
            restored_posts = asyncio.run(call(
                restored_app,
                "GET",
                "/api/v1/x/posts",
            ))
            assert restored_posts.status_code == 200
            assert restored_posts.json()["users"]["alice"]["count"] == 1

            fx_requests: list[str] = []

            async def failed_nitter_query(username, start_at, end_at):
                raise RuntimeError("isolated Nitter failure")

            def fx_transport(request: httpx.Request) -> httpx.Response:
                fx_requests.append(request.url.path)
                assert request.url.host == "api.fxtwitter.com"
                assert request.url.path == "/2/profile/Alice/statuses"
                return httpx.Response(200, json={
                    "code": 200,
                    "results": [{
                        "type": "status",
                        "id": "990000000000000001",
                        "url": "https://x.com/Alice/status/990000000000000001",
                        "text": "installed FxEmbed fallback fixture",
                        "created_at": "2026-07-22T08:00:00+08:00",
                        "created_timestamp": 1784678400,
                        "author": {"type": "profile", "screen_name": "Alice"},
                        "quote": None,
                        "replying_to": None,
                        "reposted_by": None,
                    }],
                })

            def unused_collector_transport(request: httpx.Request) -> httpx.Response:
                raise AssertionError(f"Collector network was not requested: {request.url}")

            fallback_app = FastAPI()
            fallback_app.state.intel_source_snapshot_provider = lambda: {
                "twitter_users": ["Alice"],
                "money_twitter_users": [],
            }
            fallback_app.state.intel_collector_registry = CollectorRegistry()
            fallback_app.state.x_monitor_profile_path = root / "fallback" / "profiles.json"
            fallback_app.state.x_monitor_posts_path = root / "fallback" / "posts.json"
            fallback_app.state.x_monitor_clock = lambda: FIXED_NOW
            fallback_app.state.x_monitor_posts_query_fetcher = failed_nitter_query
            fallback_app.state.x_monitor_fxembed_client = httpx.AsyncClient(
                transport=httpx.MockTransport(fx_transport)
            )
            fallback_app.state.x_monitor_collector_client = httpx.AsyncClient(
                transport=httpx.MockTransport(unused_collector_transport)
            )
            fallback_results = InProcessModuleLoader().load(
                fallback_app,
                manager.enabled_in_process_descriptors(),
            )
            assert fallback_results[-1] == {"module_id": "x_monitor", "status": "loaded"}
            fallback_response = asyncio.run(call(
                fallback_app,
                "POST",
                "/api/v1/x/posts/query",
                json={"username": "Alice", "mode": "day", "date": "2026-07-22"},
            ))
            assert fallback_response.status_code == 200
            assert fallback_response.json()["items"][0]["content"] == (
                "installed FxEmbed fallback fixture"
            )
            assert fx_requests == ["/2/profile/Alice/statuses"]
            asyncio.run(fallback_app.state.x_monitor_fxembed_client.aclose())
            asyncio.run(fallback_app.state.x_monitor_collector_client.aclose())
            assert hits == []
            assert outside_writes == []


def check_missing_dependency_and_duplicate_collector() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-x-monitor-conflict-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_x_monitor_package(root / "x.zip")
        manager.install(package, file_sha256(package), expected_module_id="x_monitor")
        try:
            manager.enable("x_monitor")
        except ModuleConflictError:
            pass
        else:
            raise AssertionError("x_monitor enabled without intel_sources")

        dependency = write_dependency_package(root / "dependency")
        manager.install(
            dependency,
            manager.calculate_package_sha256(dependency),
            expected_module_id="intel_sources",
        )
        manager.enable("intel_sources")
        manager.enable("x_monitor")
        app = FastAPI()
        app.state.intel_source_snapshot_provider = lambda: {
            "twitter_users": [],
            "money_twitter_users": [],
        }
        registry = CollectorRegistry()

        class ExistingCollector:
            source_id = "twitter"

            async def collect(self, request):
                raise AssertionError("must not run")

        registry.register(ExistingCollector())
        app.state.intel_collector_registry = registry
        results = InProcessModuleLoader().load(
            app,
            manager.enabled_in_process_descriptors(),
        )
        x_result = next(item for item in results if item["module_id"] == "x_monitor")
        assert x_result["status"] == "failed", results
        assert not any(route.path.startswith("/api/v1/x") for route in app.routes)


def main() -> int:
    check_lifecycle_provider_and_isolation()
    check_missing_dependency_and_duplicate_collector()
    check_deterministic_package_and_release()
    print("x_monitor installable module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
