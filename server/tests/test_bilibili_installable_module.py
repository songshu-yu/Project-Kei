"""Isolated installable-package regression for PK-130."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.intel_contracts import CollectorRegistry
from core.modules import InProcessModuleLoader, ModuleManager
from features.bilibili.package_builder import (
    BACKEND_SOURCES,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_bilibili_package,
    file_sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = PROJECT_ROOT / "server" / "features" / "bilibili"
RELEASE_FRAGMENT = FEATURE_ROOT / "release" / "official-release-fragment.json"
EXPECTED_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_SOURCES),
}
FIXED_NOW = datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc)


class FakeSourceRegistry:
    def read(self) -> dict:
        return {"bilibili_uids": [10001]}


class FakeBilibiliClient:
    calls: list[str] = []

    async def fetch_profile(self, uid: object) -> dict:
        self.calls.append(f"profile:{uid}")
        return {
            "uid": int(uid),
            "name": "测试用户",
            "avatar_url": "https://i.example/avatar.png",
        }

    async def fetch_space_dynamics(self, uid: object) -> list[dict]:
        self.calls.append(f"dynamics:{uid}")
        return [{
            "id_str": "dynamic-1",
            "type": "DYNAMIC_TYPE_WORD",
            "modules": {
                "module_author": {
                    "name": "测试用户",
                    "pub_ts": int(FIXED_NOW.timestamp()),
                },
                "module_dynamic": {"desc": {"text": "固定测试动态"}},
            },
        }]

    async def aclose(self) -> None:
        return None


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


def manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "state" / "module_registry.json",
        data_root=root / "state" / "modules",
    )


def dependency_package(root: Path) -> Path:
    package = root / "intel-sources"
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "intel_sources",
        "name": "intel_sources fixture",
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
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "backend" / "__init__.py").write_text(
        "def register(app):\n    app.state.intel_sources_fixture = True\n",
        encoding="utf-8",
    )
    return package


def restarted_app(
    module_manager: ModuleManager,
    data_root: Path,
    collector_registry: CollectorRegistry | None = None,
) -> tuple[FastAPI, list[dict], CollectorRegistry]:
    app = FastAPI()
    sources = FakeSourceRegistry()
    collectors = collector_registry or CollectorRegistry()
    app.state.intel_source_registry_provider = lambda: sources
    app.state.intel_collector_registry_provider = lambda: collectors
    app.state.bilibili_data_root_provider = lambda: data_root
    app.state.bilibili_local_request_guard = lambda _request: True
    app.state.bilibili_client_factory_provider = lambda _credentials: FakeBilibiliClient()
    app.state.bilibili_now_provider = lambda: FIXED_NOW
    loader = InProcessModuleLoader()
    results = loader.load(app, module_manager.enabled_in_process_descriptors())
    module_manager.record_load_results(results)
    return app, results, collectors


def seed_historical_data(data_root: Path) -> dict[str, str]:
    data_root.mkdir(parents=True, exist_ok=True)
    secrets = {
        "sessdata": "historical-session-A1",
        "bili_jct": "historical-csrf-B2",
        "buvid3": "historical-device-C3",
    }
    credential_entry = {
        "values": secrets,
        "state": "configured",
        "updated_at": "2026-07-29T08:00:00+00:00",
        "validated_at": "2026-07-29T08:01:00+00:00",
        "last_error_code": None,
        "retry_after": None,
    }
    (data_root / "bilibili_credentials.local.json").write_text(
        json.dumps({
            "schema_version": 1,
            "active": credential_entry,
            "candidate": None,
            "environment_status": None,
        }),
        encoding="utf-8",
    )
    (data_root / "bilibili_profiles.json").write_text(
        json.dumps({
            "schema_version": 1,
            "profiles": {
                "10001": {
                    "uid": 10001,
                    "name": "历史缓存用户",
                    "avatar_url": "",
                    "status": "ok",
                    "updated_at": "2026-07-29T08:00:00+00:00",
                },
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return secrets


def check_deterministic_package_and_release() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-bilibili-build-") as temp_dir:
        root = Path(temp_dir)
        first = build_bilibili_package(root / "first.zip")
        second = build_bilibili_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        with zipfile.ZipFile(first) as archive:
            assert set(archive.namelist()) == EXPECTED_NAMES
            package_text = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.endswith((".py", ".js", ".json"))
            )
        lowered_names = {name.casefold() for name in EXPECTED_NAMES}
        assert not any(
            token in Path(name).parts
            for name in lowered_names
            for token in (".env", "vendor", "node_modules", "scripts", "state", "data")
        )
        assert not any(name.endswith((".local.json", ".db", ".sqlite")) for name in lowered_names)
        assert "server/data/intel_sources.json" not in package_text
        assert "features.daily_briefing" not in package_text
        assert "features.intel_sources" not in package_text
        assert "intel.collectors" not in package_text
        assert "services.bilibili_profile_cache" not in package_text
        assert "session-secret-A1" not in package_text
        dashboard = zipfile.ZipFile(first).read("dashboard/index.js").decode("utf-8")
        assert "input.type = 'password'" in dashboard
        assert "console." not in dashboard
        assert "localStorage" not in dashboard and "sessionStorage" not in dashboard
        assert "fetch(" not in dashboard
        assert "avatar.src" not in dashboard
        assert "createElement('img')" not in dashboard
        assert "/api/v1/bilibili/profiles/resolve" not in dashboard
        collect_listener = dashboard.index("el(root, 'collect').addEventListener('click'")
        explicit_collect = dashboard.index(
            "/api/v1/bilibili/credentials/validate-and-collect"
        )
        assert explicit_collect > collect_listener

    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "bilibili"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["data_policy"] == "preserve_on_uninstall"


def check_provider_failure_is_atomic() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-bilibili-provider-") as temp_dir:
        root = Path(temp_dir)
        module_manager = manager(root)
        dependency = dependency_package(root)
        module_manager.install(
            dependency,
            module_manager.calculate_package_sha256(dependency),
            expected_module_id="intel_sources",
        )
        module_manager.enable("intel_sources")
        package = build_bilibili_package(root / "bilibili.zip")
        module_manager.install(package, file_sha256(package), expected_module_id="bilibili")
        module_manager.enable("bilibili")
        app = FastAPI()
        initial_paths = [route.path for route in app.routes]
        results = InProcessModuleLoader().load(
            app, module_manager.enabled_in_process_descriptors()
        )
        bilibili_result = next(item for item in results if item["module_id"] == "bilibili")
        assert bilibili_result["status"] == "failed"
        assert [route.path for route in app.routes] == initial_paths
        assert not (root / "state" / "modules" / "bilibili").exists()


def check_route_registration_failure_rolls_back() -> None:
    class FailingApp(FastAPI):
        def include_router(self, router, **kwargs):  # type: ignore[no-untyped-def]
            if any(route.path.startswith("/api/v1/bilibili") for route in router.routes):
                self.router.routes.append(router.routes[0])
                raise RuntimeError("injected route registration failure")
            return super().include_router(router, **kwargs)

    with tempfile.TemporaryDirectory(prefix="kei-bilibili-route-rollback-") as temp_dir:
        root = Path(temp_dir)
        module_manager = manager(root)
        dependency = dependency_package(root)
        module_manager.install(
            dependency,
            module_manager.calculate_package_sha256(dependency),
            expected_module_id="intel_sources",
        )
        module_manager.enable("intel_sources")
        package = build_bilibili_package(root / "bilibili.zip")
        module_manager.install(package, file_sha256(package), expected_module_id="bilibili")
        module_manager.enable("bilibili")

        app = FailingApp()
        sources = FakeSourceRegistry()
        collectors = CollectorRegistry()
        data_root = root / "state" / "modules" / "bilibili"
        app.state.intel_source_registry_provider = lambda: sources
        app.state.intel_collector_registry_provider = lambda: collectors
        app.state.bilibili_data_root_provider = lambda: data_root
        app.state.bilibili_local_request_guard = lambda _request: True
        app.state.bilibili_client_factory_provider = lambda _credentials: FakeBilibiliClient()
        app.state.bilibili_now_provider = lambda: FIXED_NOW
        initial_paths = [route.path for route in app.routes]
        results = InProcessModuleLoader().load(
            app, module_manager.enabled_in_process_descriptors()
        )
        failed = next(item for item in results if item["module_id"] == "bilibili")
        assert failed["status"] == "failed"
        assert [route.path for route in app.routes] == initial_paths
        assert collectors.get("bilibili") is None
        assert not data_root.exists()


def check_duplicate_route_is_rejected_atomically() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-bilibili-duplicate-route-") as temp_dir:
        root = Path(temp_dir)
        module_manager = manager(root)
        dependency = dependency_package(root)
        module_manager.install(
            dependency,
            module_manager.calculate_package_sha256(dependency),
            expected_module_id="intel_sources",
        )
        module_manager.enable("intel_sources")
        package = build_bilibili_package(root / "bilibili.zip")
        module_manager.install(package, file_sha256(package), expected_module_id="bilibili")
        module_manager.enable("bilibili")

        app = FastAPI()

        @app.get("/api/v1/bilibili/profiles")
        async def occupied_route() -> dict:
            return {"occupied": True}

        sources = FakeSourceRegistry()
        collectors = CollectorRegistry()
        data_root = root / "state" / "modules" / "bilibili"
        app.state.intel_source_registry_provider = lambda: sources
        app.state.intel_collector_registry_provider = lambda: collectors
        app.state.bilibili_data_root_provider = lambda: data_root
        app.state.bilibili_local_request_guard = lambda _request: True
        app.state.bilibili_client_factory_provider = lambda _credentials: FakeBilibiliClient()
        app.state.bilibili_now_provider = lambda: FIXED_NOW
        initial_paths = [route.path for route in app.routes]

        results = InProcessModuleLoader().load(
            app, module_manager.enabled_in_process_descriptors()
        )
        failed = next(item for item in results if item["module_id"] == "bilibili")
        assert failed["status"] == "failed"
        assert [route.path for route in app.routes] == initial_paths
        assert collectors.get("bilibili") is None
        assert not data_root.exists()


def check_data_path_guards() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-bilibili-path-guard-") as temp_dir:
        root = Path(temp_dir)
        module_manager = manager(root)
        dependency = dependency_package(root)
        module_manager.install(
            dependency,
            module_manager.calculate_package_sha256(dependency),
            expected_module_id="intel_sources",
        )
        module_manager.enable("intel_sources")
        package = build_bilibili_package(root / "bilibili.zip")
        module_manager.install(package, file_sha256(package), expected_module_id="bilibili")
        module_manager.enable("bilibili")

        valid_root = root / "state" / "modules" / "bilibili"
        loaded_app, results, _ = restarted_app(module_manager, valid_root)
        assert next(item for item in results if item["module_id"] == "bilibili")["status"] == "loaded"

        import sys
        loaded_backend = sys.modules[
            "_project_kei_module_bilibili_"
            + OFFICIAL_RELEASE_VERSION.replace(".", "_")
        ]

        def guarded_app(data_root: Path) -> tuple[FastAPI, CollectorRegistry]:
            app = FastAPI()
            collectors = CollectorRegistry()
            app.state.intel_source_registry_provider = lambda: FakeSourceRegistry()
            app.state.intel_collector_registry_provider = lambda: collectors
            app.state.bilibili_data_root_provider = lambda: data_root
            app.state.bilibili_local_request_guard = lambda _request: True
            app.state.bilibili_client_factory_provider = (
                lambda _credentials: FakeBilibiliClient()
            )
            app.state.bilibili_now_provider = lambda: FIXED_NOW
            return app, collectors

        relative_app, relative_collectors = guarded_app(Path("relative-bilibili-data"))
        relative_paths = [route.path for route in relative_app.routes]
        try:
            loaded_backend.register(relative_app)
        except RuntimeError as exc:
            assert "absolute path" in str(exc)
        else:
            raise AssertionError("relative Bilibili data root should be rejected")
        assert [route.path for route in relative_app.routes] == relative_paths
        assert relative_collectors.get("bilibili") is None

        traversal_root = root / "state" / ".." / "bilibili-data"
        traversal_app, traversal_collectors = guarded_app(traversal_root)
        traversal_paths = [route.path for route in traversal_app.routes]
        try:
            loaded_backend.register(traversal_app)
        except RuntimeError as exc:
            assert "normalized" in str(exc)
        else:
            raise AssertionError("parent traversal in Bilibili data root should be rejected")
        assert [route.path for route in traversal_app.routes] == traversal_paths
        assert traversal_collectors.get("bilibili") is None

        simulated_reparse = root / "simulated-reparse"
        simulated_reparse.mkdir()
        reparse_app, reparse_collectors = guarded_app(simulated_reparse)
        reparse_paths = [route.path for route in reparse_app.routes]
        original_link_check = loaded_backend._is_link_or_reparse
        loaded_backend._is_link_or_reparse = (
            lambda path: Path(path) == simulated_reparse
        )
        try:
            try:
                loaded_backend.register(reparse_app)
            except RuntimeError as exc:
                assert "link or reparse point" in str(exc)
            else:
                raise AssertionError("reparse Bilibili data root should be rejected")
        finally:
            loaded_backend._is_link_or_reparse = original_link_check
        assert [route.path for route in reparse_app.routes] == reparse_paths
        assert reparse_collectors.get("bilibili") is None
        assert not (simulated_reparse / "bilibili_profiles.json").exists()
        assert not (simulated_reparse / "bilibili_credentials.local.json").exists()
        assert loaded_app.state.bilibili_module_registered is True


def check_lifecycle_zero_network_and_reinstall() -> None:
    FakeBilibiliClient.calls.clear()
    with tempfile.TemporaryDirectory(prefix="kei-bilibili-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        module_manager = manager(root)
        dependency = dependency_package(root)
        module_manager.install(
            dependency,
            module_manager.calculate_package_sha256(dependency),
            expected_module_id="intel_sources",
        )
        module_manager.enable("intel_sources")
        package = build_bilibili_package(root / OFFICIAL_ASSET_NAME)
        installed = module_manager.install(
            package,
            file_sha256(package),
            expected_module_id="bilibili",
        )
        assert installed["install_status"] == "installed_disabled"
        module_manager.enable("bilibili")

        data_root = root / "state" / "modules" / "bilibili"
        historical_secrets = seed_historical_data(data_root)
        app, results, collectors = restarted_app(module_manager, data_root)
        assert next(item for item in results if item["module_id"] == "bilibili")["status"] == "loaded"
        assert collectors.get("bilibili") is not None
        expected_paths = {
            "/api/v1/bilibili/profiles",
            "/api/v1/bilibili/profiles/resolve",
            "/api/v1/bilibili/credentials/status",
            "/api/v1/bilibili/credentials",
            "/api/v1/bilibili/credentials/validate-and-collect",
            "/dashboard/intel-sources/bilibili-profiles/resolve",
            "/dashboard/intel-sources/bilibili-credentials/status",
            "/dashboard/intel-sources/bilibili-credentials",
            "/dashboard/intel-sources/bilibili-credentials/validate-and-collect",
        }
        assert expected_paths <= {route.path for route in app.routes}

        historical_status = asyncio.run(
            call(app, "GET", "/api/v1/bilibili/credentials/status")
        )
        assert historical_status.status_code == 200
        assert historical_status.json()["active_available"] is True
        assert all(value not in historical_status.text for value in historical_secrets.values())
        historical_profiles = asyncio.run(
            call(app, "GET", "/api/v1/bilibili/profiles")
        )
        assert historical_profiles.status_code == 200
        assert (
            historical_profiles.json()["profiles"]["10001"]["name"]
            == "历史缓存用户"
        )
        assert FakeBilibiliClient.calls == []
        assert not (data_root / "profiles.json").exists()
        assert not (data_root / "credentials.local.json").exists()

        secrets = {
            "sessdata": "session-secret-A1",
            "bili_jct": "csrf-secret-B2",
            "buvid3": "device-secret-C3",
        }
        saved = asyncio.run(call(
            app,
            "PUT",
            "/api/v1/bilibili/credentials",
            json=secrets,
        ))
        assert saved.status_code == 200
        assert FakeBilibiliClient.calls == []
        serialized = json.dumps(saved.json(), ensure_ascii=False)
        assert all(secret not in serialized for secret in secrets.values())

        collected = asyncio.run(call(
            app,
            "POST",
            "/api/v1/bilibili/credentials/validate-and-collect",
        ))
        assert collected.status_code == 200, collected.text
        assert FakeBilibiliClient.calls == ["profile:10001", "dynamics:10001"]
        response_text = collected.text
        assert all(secret not in response_text for secret in secrets.values())
        assert (data_root / "bilibili_credentials.local.json").is_file()
        assert (data_root / "bilibili_profiles.json").is_file()
        assert not (data_root / "credentials.local.json").exists()
        assert not (data_root / "profiles.json").exists()

        before = len(app.routes)
        import sys
        loaded_backend = sys.modules[
            "_project_kei_module_bilibili_"
            + OFFICIAL_RELEASE_VERSION.replace(".", "_")
        ]
        loaded_backend.register(app)
        assert len(app.routes) == before

        module_manager.disable("bilibili")
        uninstalled = module_manager.uninstall("bilibili")
        assert uninstalled["data_preserved"] is True
        assert (data_root / "bilibili_credentials.local.json").is_file()
        assert (data_root / "bilibili_profiles.json").is_file()
        assert not (data_root / "credentials.local.json").exists()
        assert not (data_root / "profiles.json").exists()
        module_manager.install(package, file_sha256(package), expected_module_id="bilibili")
        module_manager.enable("bilibili")
        restored, restored_results, _ = restarted_app(module_manager, data_root)
        restored_bilibili = next(
            item for item in restored_results if item["module_id"] == "bilibili"
        )
        assert restored_bilibili["status"] == "loaded", restored_results
        status = asyncio.run(
            call(restored, "GET", "/api/v1/bilibili/credentials/status")
        )
        assert status.status_code == 200
        assert status.json()["active_available"] is True
        assert all(secret not in status.text for secret in secrets.values())


def main() -> int:
    started = time.monotonic()
    check_deterministic_package_and_release()
    check_provider_failure_is_atomic()
    check_route_registration_failure_rolls_back()
    check_duplicate_route_is_rejected_atomically()
    check_data_path_guards()
    check_lifecycle_zero_network_and_reinstall()
    print("bilibili installable module tests passed in %.2fs" % (time.monotonic() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
