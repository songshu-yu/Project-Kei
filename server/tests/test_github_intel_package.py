"""PK-132 installable package checks using only temporary paths and fake HTTP."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import json
import subprocess
import sys
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
    CoverageStatus,
)
from core.modules import InProcessModuleLoader, ModuleManager, validate_manifest
from core.modules.exceptions import ModuleConflictError
from core.modules.official_catalog import (
    OfficialCatalogHTTPClient,
    OfficialCatalogStore,
    validate_official_catalog,
)
from features.github_intel import GitHubCollectorSettings, register
from features.github_intel.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_github_intel_package,
    file_sha256,
)
from features.module_manager.official_service import OfficialModuleService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = PROJECT_ROOT / "server" / "features" / "github_intel"
RELEASE_ROOT = FEATURE_ROOT / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
ENTRYPOINT = FEATURE_ROOT / "package_source" / "dashboard" / "index.js"
NOW = datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc)
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    "backend/__init__.py",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def write_intel_sources_fixture(root: Path) -> Path:
    package = root / "intel-sources-fixture"
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "intel_sources",
        "name": "Isolated Intel Sources",
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
        "config_schema": None,
        "permissions": ["local_state"],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (package / "backend" / "__init__.py").write_text(
        "def register(app):\n"
        "    app.state.intel_sources_fixture_loaded = True\n",
        encoding="utf-8",
    )
    return package


def install_dependency(manager: ModuleManager, root: Path) -> None:
    package = write_intel_sources_fixture(root)
    digest = manager.calculate_package_sha256(package)
    manager.install(package, digest, expected_module_id="intel_sources")
    manager.enable("intel_sources")


def restarted_app(
    manager: ModuleManager,
    *,
    with_registry: bool = True,
) -> tuple[FastAPI, list[dict[str, str]]]:
    app = FastAPI()
    if with_registry:
        app.state.intel_collector_registry = CollectorRegistry()
    results = InProcessModuleLoader().load(
        app,
        manager.enabled_in_process_descriptors(),
    )
    return app, results


def assert_package_contents(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        assert names == EXPECTED_PACKAGE_NAMES
        assert len(names) == len(archive.infolist())
        for info in archive.infolist():
            assert info.date_time == FIXED_ZIP_DATETIME
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.extra == b"" and info.comment == b""
        manifest_raw = archive.read("manifest.json")
        manifest = validate_manifest(json.loads(manifest_raw.decode("utf-8")))
        assert manifest.id == "github_intel"
        assert manifest.dependencies == ("intel_sources",)
        assert manifest.api_namespaces == ()
        assert manifest.permissions == ()
        assert manifest.dashboard_entrypoint == "dashboard/index.js"
        assert manifest.config_schema is None
        package_text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in sorted(names)
        )
    assert "features.daily_briefing" not in package_text
    assert "features.intel_sources" not in package_text
    assert "source_composition" not in package_text
    assert "server/data" not in package_text.replace("\\", "/")
    assert "print(" not in package_text
    assert not any(
        marker in name.casefold()
        for name in names
        for marker in (
            ".env",
            "cache",
            "cookie",
            "credential",
            "fixture",
            "model",
            "registry",
            "script",
            "test",
            "vendor",
        )
    )


def check_deterministic_package_and_release_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-github-package-") as temp_dir:
        root = Path(temp_dir)
        first = build_github_intel_package(root / "first.zip")
        second = build_github_intel_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        assert_package_contents(first)
        assert_package_contents(second)

        materialized = build_github_intel_package(root / "materialized")
        for path in materialized.rglob("*"):
            if path.is_file():
                assert b"\r\n" not in path.read_bytes()

        fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
        entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
        with zipfile.ZipFile(first) as archive:
            manifest_raw = archive.read("manifest.json")
        assert fragment == {
            "schema_version": 1,
            "module_id": "github_intel",
            "name": "GitHub 情报来源",
            "version": OFFICIAL_RELEASE_VERSION,
            "core_compatibility": ">=1.0.0 <2.0.0",
            "release_tag": OFFICIAL_RELEASE_TAG,
            "asset_name": OFFICIAL_ASSET_NAME,
            "dependencies": ["intel_sources"],
            "optional_dependencies": [],
            "conflicts": [],
            "permissions": [],
            "data_policy": "preserve_on_uninstall",
            "requires_restart": True,
        }
        assert entry["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
        assert entry["package_sha256"] == file_sha256(first)
        assert entry["package_size"] == first.stat().st_size
        catalog = validate_official_catalog({
            "schema_version": 1,
            "publisher": "Project Kei",
            "owner": "songshu-yu",
            "repository": "Project-Kei-Modules",
            "generated_at": "2026-07-30T00:00:00Z",
            "modules": [entry],
        })
        assert catalog.modules[0].package_url == (
            "https://github.com/songshu-yu/Project-Kei-Modules/releases/download/"
            f"{OFFICIAL_RELEASE_TAG}/{OFFICIAL_ASSET_NAME}"
        )


async def collect_from_installed_package(app: FastAPI) -> dict:
    registry = app.state.intel_collector_registry
    collector = registry.get("github")
    assert collector is app.state.github_intel_collector
    collector._settings = GitHubCollectorSettings(  # noqa: SLF001
        per_page=2,
        max_pages=2,
        timeout_seconds=2,
        trust_env=False,
        use_environment_auth=False,
    )

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.host == "api.github.com"
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        if request.url.path.startswith("/users/"):
            return httpx.Response(
                200,
                json=[{
                    "id": "installed-event",
                    "type": "WatchEvent",
                    "actor": {"login": "fixture-user"},
                    "repo": {"name": "fixture-org/fixture-repo"},
                    "created_at": "2026-07-30T07:30:00Z",
                    "payload": {},
                }],
            )
        return httpx.Response(404, text="private upstream detail")

    collector._transport = httpx.MockTransport(handler)  # noqa: SLF001
    collector._clock = lambda: NOW  # noqa: SLF001
    result = await collector.collect(CollectRequest(
        local_date=date(2026, 7, 30),
        timezone="Asia/Shanghai",
        source_ids=("github",),
        refresh=True,
        source_config_snapshot={
            "github_users": ["fixture-user"],
            "github_repos": ["fixture-org/missing-repo"],
        },
    ))
    assert calls == [
        "/users/fixture-user/events/public",
        "/repos/fixture-org/missing-repo/releases",
    ]
    assert result.coverage.status is CoverageStatus.PARTIAL
    assert len(result.items) == 1
    payload = result.to_dict()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "private upstream detail" not in serialized
    return payload


def check_lifecycle_provider_and_failure_isolation() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-github-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package = build_github_intel_package(root / OFFICIAL_ASSET_NAME)
        digest = file_sha256(package)

        installed = manager.install(
            package,
            digest,
            expected_module_id="github_intel",
        )
        assert installed["install_status"] == "installed_disabled"
        assert installed["enabled"] is False
        try:
            manager.enable("github_intel")
        except ModuleConflictError as exc:
            assert str(exc) == "missing required modules: intel_sources"
        else:
            raise AssertionError("GitHub module enabled without intel_sources")
        install_dependency(manager, root)
        enabled = manager.enable("github_intel")
        assert enabled["enabled"] is True and enabled["restart_required"] is True

        app, results = restarted_app(manager)
        assert {
            result["module_id"]: result["status"]
            for result in results
        } == {
            "github_intel": "loaded",
            "intel_sources": "loaded",
        }
        manager.record_load_results(results)
        assert app.state.intel_sources_fixture_loaded is True
        route_keys_before = [
            (tuple(sorted(route.methods or ())), route.path)
            for route in app.routes
        ]
        registered = register(app)
        assert registered is app.state.github_intel_collector
        route_keys_after = [
            (tuple(sorted(route.methods or ())), route.path)
            for route in app.routes
        ]
        assert route_keys_after == route_keys_before
        assert len(route_keys_after) == len(set(route_keys_after))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            payload = asyncio.run(collect_from_installed_package(app))
        assert stdout.getvalue() == ""
        assert payload["source_id"] == "github"

        provider_app, provider_results = restarted_app(
            manager,
            with_registry=False,
        )
        assert {
            result["module_id"]: result["status"]
            for result in provider_results
        } == {
            "github_intel": "loaded",
            "intel_sources": "loaded",
        }
        assert isinstance(
            provider_app.state.intel_collector_registry,
            CollectorRegistry,
        )
        assert provider_app.state.intel_collector_registry.get("github") is not None

        conflict_app = FastAPI()
        conflict_app.state.intel_collector_registry = CollectorRegistry()

        class OtherGitHubCollector:
            source_id = "github"

            async def collect(self, request):
                raise AssertionError("conflicting collector must not run")

        other = OtherGitHubCollector()
        conflict_app.state.intel_collector_registry.register(other)
        conflict_results = InProcessModuleLoader().load(
            conflict_app,
            manager.enabled_in_process_descriptors(),
        )
        conflict_by_id = {
            result["module_id"]: result
            for result in conflict_results
        }
        assert conflict_by_id["intel_sources"] == {
            "module_id": "intel_sources",
            "status": "loaded",
        }
        assert conflict_by_id["github_intel"]["status"] == "failed"
        assert "ValueError" in conflict_by_id["github_intel"]["error"]
        assert conflict_app.state.intel_sources_fixture_loaded is True
        assert conflict_app.state.intel_collector_registry.get("github") is other

        module_data = root / "data" / "modules" / "github_intel"
        source_data = root / "data" / "modules" / "intel_sources"
        module_data.mkdir(parents=True)
        source_data.mkdir(parents=True)
        (module_data / "isolated-cache-sentinel.json").write_text(
            '{"fixture": true}\n',
            encoding="utf-8",
        )
        (source_data / "isolated-config-sentinel.json").write_text(
            '{"fixture": true}\n',
            encoding="utf-8",
        )

        disabled = manager.disable("github_intel")
        assert disabled["enabled"] is False and disabled["restart_required"] is True
        assert app.state.intel_collector_registry.get("github") is not None
        disabled_app, disabled_results = restarted_app(manager)
        assert disabled_results == [{"module_id": "intel_sources", "status": "loaded"}]
        assert disabled_app.state.intel_collector_registry.get("github") is None

        removed = manager.uninstall("github_intel")
        assert removed["data_preserved"] is True
        assert module_data.is_dir() and source_data.is_dir()

        reinstalled = manager.install(
            package,
            digest,
            expected_module_id="github_intel",
        )
        assert reinstalled["install_status"] == "installed_disabled"
        manager.enable("github_intel")
        reinstalled_app, reinstalled_results = restarted_app(manager)
        assert next(
            result
            for result in reinstalled_results
            if result["module_id"] == "github_intel"
        ) == {
            "module_id": "github_intel",
            "status": "loaded",
        }
        assert reinstalled_app.state.intel_collector_registry.get("github") is not None
        assert module_data.is_dir() and source_data.is_dir()


def check_anonymous_fixed_official_acquisition() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-github-official-") as temp_dir:
        root = Path(temp_dir)
        package = build_github_intel_package(root / OFFICIAL_ASSET_NAME)
        entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
        catalog_payload = {
            "schema_version": 1,
            "publisher": "Project Kei",
            "owner": "songshu-yu",
            "repository": "Project-Kei-Modules",
            "generated_at": "2026-07-30T00:00:00Z",
            "modules": [entry],
        }
        bundled = root / "bundled-catalog.json"
        bundled.write_text(
            json.dumps(catalog_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        store = OfficialCatalogStore(
            bundled,
            root / "data" / "official-module-catalog.json",
        )
        store.save(validate_official_catalog(catalog_payload))
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            assert str(request.url) == entry["package_url"]
            assert "authorization" not in request.headers
            assert "cookie" not in request.headers
            return httpx.Response(
                200,
                content=package.read_bytes(),
                headers={"Content-Length": str(package.stat().st_size)},
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
            trust_env=False,
        )
        manager = make_manager(root)
        service = OfficialModuleService(
            manager,
            store,
            OfficialCatalogHTTPClient(client=client),
        )
        before = service.list_catalog()
        assert requests == [] and before["network_accessed"] is False
        assert before["source"] == {
            "publisher": "Project Kei",
            "owner": "songshu-yu",
            "repository": "Project-Kei-Modules",
            "catalog_url": (
                "https://raw.githubusercontent.com/songshu-yu/"
                "Project-Kei-Modules/main/catalog/official-catalog.json"
            ),
            "catalog_mirrors": {
                "github": (
                    "https://raw.githubusercontent.com/songshu-yu/"
                    "Project-Kei-Modules/main/catalog/official-catalog.json"
                ),
                "gitee": (
                    "https://gitee.com/songshuyu957/Project-Kei-Modules/"
                    "raw/main/catalog/official-catalog.json"
                ),
            },
            "download_sources": ["auto", "github", "gitee"],
            "anonymous_only": True,
        }
        installed = service.install(
            "github_intel",
            OFFICIAL_RELEASE_VERSION,
            f"github_intel@{OFFICIAL_RELEASE_VERSION}",
        )
        assert len(requests) == 1
        assert installed["package_source"] == "official_github_release"
        serialized = json.dumps(installed, ensure_ascii=False).casefold()
        assert "authorization" not in serialized
        assert "cookie" not in serialized
        client.close()


def check_dashboard_entrypoint() -> None:
    source = ENTRYPOINT.read_text(encoding="utf-8")
    assert "export async function mount(context)" in source
    assert "export async function unmount()" in source
    assert "context.request" not in source
    assert "fetch(" not in source
    assert "localStorage" not in source and "sessionStorage" not in source
    completed = subprocess.run(
        ["node", "--check", str(ENTRYPOINT)],
        cwd=PROJECT_ROOT / "server",
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)


def main() -> int:
    check_deterministic_package_and_release_metadata()
    check_lifecycle_provider_and_failure_isolation()
    check_anonymous_fixed_official_acquisition()
    check_dashboard_entrypoint()
    print("github intelligence installable package tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
