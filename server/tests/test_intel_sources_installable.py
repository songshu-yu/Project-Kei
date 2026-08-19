"""PK-115 installable package, lifecycle, Provider, and isolation checks."""

from __future__ import annotations

import asyncio
import ast
import hashlib
import json
import os
import socket
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import PackageValidationError
from features.intel_sources.module import register
from features.intel_sources.package_builder import (
    BACKEND_FILES,
    OFFICIAL_ASSET_NAME,
    build_intel_sources_package,
    file_sha256,
)
from features.intel_sources.repository import DEFAULT_PATH


FEATURE_ROOT = Path(__file__).resolve().parents[1] / "features" / "intel_sources"
DEFAULTS = {
    "twitter_users": ["OpenAI"],
    "money_twitter_users": [],
    "github_users": [],
    "github_repos": [],
    "bilibili_uids": [],
    "youtube_channel_ids": [],
    "paper_priority_authors": [],
    "paper_secondary_authors": [],
    "paper_ai_authors": [],
}
FULL_PAYLOAD = {
    "twitter_users": ["OpenAI", "KeiBot"],
    "money_twitter_users": ["IndieHackers"],
    "github_users": ["openai"],
    "github_repos": ["openai/openai-python"],
    "bilibili_uids": [123],
    "youtube_channel_ids": ["UC1234567890123456789012"],
    "paper_priority_authors": ["Ada Lovelace"],
    "paper_secondary_authors": ["Grace Hopper"],
    "paper_ai_authors": [],
}


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def make_app(config_path: Path) -> FastAPI:
    app = FastAPI()
    app.state.intel_source_config_path = config_path
    app.state.intel_source_defaults_provider = lambda: {
        key: list(value) for key, value in DEFAULTS.items()
    }
    app.state.intel_source_local_control_guard = lambda _request: True
    return app


def restarted_app(
    manager: ModuleManager,
    config_path: Path,
) -> tuple[FastAPI, list[dict[str, str]]]:
    app = make_app(config_path)
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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, **kwargs)


def route_keys(app: FastAPI) -> list[tuple[str, str]]:
    return [
        (method, route.path)
        for route in app.routes
        for method in sorted(getattr(route, "methods", ()) or ())
        if route.path.startswith(("/api/v1/intel-sources", "/dashboard/intel-sources"))
    ]


def check_package_is_deterministic_allowlisted_and_secret_free() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-intel-sources-package-test-") as temp_dir:
        root = Path(temp_dir)
        protected = os.path.abspath(os.fspath(DEFAULT_PATH)).casefold()
        original_open = Path.open

        def guarded_open(path: Path, *args, **kwargs):
            if os.path.abspath(os.fspath(path)).casefold() == protected:
                raise AssertionError("package build attempted to read real intel_sources.json")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guarded_open):
            first = build_intel_sources_package(root / "first.zip")
            second = build_intel_sources_package(root / "second.zip")
            assert first.read_bytes() == second.read_bytes()
            assert file_sha256(first) == file_sha256(second)

        expected = {
            "manifest.json",
            "dashboard/index.js",
            *(f"backend/{name}" for name in BACKEND_FILES),
        }
        with zipfile.ZipFile(first) as archive:
            assert set(archive.namelist()) == expected
            assert all(
                info.date_time == (2026, 1, 1, 0, 0, 0)
                for info in archive.infolist()
            )
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["id"] == "intel_sources"
            assert manifest["entrypoint"] == "backend.register"
            assert manifest["api_namespaces"] == ["/api/v1/intel-sources"]
            assert manifest["legacy_endpoints"] == ["/dashboard/intel-sources"]
            assert manifest["data_namespace"] == "intel_sources"
            assert manifest["permissions"] == ["local_state"]
            for name in archive.namelist():
                lowered = name.casefold()
                assert ".env" not in lowered
                assert "intel_sources.json" not in lowered
                assert "__pycache__" not in lowered
                assert "vendor/" not in lowered
                assert "scripts/" not in lowered

            imported: set[str] = set()
            for name in expected:
                if not name.endswith(".py"):
                    continue
                tree = ast.parse(archive.read(name).decode("utf-8"), filename=name)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported.add(node.module)
            assert not any(name.startswith("features.daily_briefing") for name in imported)
            assert not any(name.startswith("intel.collectors") for name in imported)
            assert not {"httpx", "requests", "urllib", "socket"} & imported
            manifest_digest = hashlib.sha256(archive.read("manifest.json")).hexdigest()

        release_entry = json.loads(
            (FEATURE_ROOT / "release" / "official-catalog-entry.json").read_text(
                encoding="utf-8"
            )
        )
        assert release_entry["asset_name"] == OFFICIAL_ASSET_NAME
        assert release_entry["manifest_sha256"] == manifest_digest
        assert release_entry["package_sha256"] == file_sha256(first)
        assert release_entry["package_size"] == first.stat().st_size


def check_registration_uses_one_registry_provider_and_zero_network() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-intel-sources-api-test-") as temp_dir:
        root = Path(temp_dir)
        app = make_app(root / "intel_sources.json")
        before = len(app.routes)
        register(app)
        register(app)
        assert len(app.routes) > before
        keys = route_keys(app)
        assert len(keys) == len(set(keys))
        assert callable(app.state.intel_source_config_reader)
        assert callable(app.state.intel_source_snapshot_provider)
        assert app.state.intel_sources_module_registered is True

        async def scenario() -> None:
            initial = await call(app, "GET", "/api/v1/intel-sources")
            assert initial.status_code == 200
            assert initial.json()["twitter_users"] == ["OpenAI"]
            assert not (root / "intel_sources.json").exists()

            added = await call(
                app,
                "POST",
                "/api/v1/intel-sources/twitter_users",
                json={"value": "@KeiBot"},
            )
            assert added.status_code == 200
            legacy = await call(app, "GET", "/dashboard/intel-sources")
            assert legacy.json()["twitter_users"] == ["OpenAI", "KeiBot"]

            replaced = await call(
                app,
                "PUT",
                "/dashboard/intel-sources",
                json={"github_repos": ["openai/openai-python"]},
            )
            assert replaced.status_code == 200
            versioned = await call(app, "GET", "/api/v1/intel-sources")
            assert versioned.json()["twitter_users"] == ["OpenAI", "KeiBot"]
            assert versioned.json()["github_repos"] == ["openai/openai-python"]

        with patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network forbidden"),
        ):
            with patch.object(
                socket,
                "getaddrinfo",
                side_effect=AssertionError("network forbidden"),
            ):
                asyncio.run(scenario())

        snapshot = app.state.intel_source_snapshot_provider(["github"])
        assert snapshot == {
            "github_users": (),
            "github_repos": ("openai/openai-python",),
        }
        try:
            snapshot["github_repos"] = ()  # type: ignore[index]
        except TypeError:
            pass
        else:
            raise AssertionError("Collector snapshot Provider returned a mutable mapping")


def check_route_conflict_is_rejected_before_partial_registration() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-intel-sources-route-test-") as temp_dir:
        app = make_app(Path(temp_dir) / "intel_sources.json")

        @app.get("/api/v1/intel-sources")
        async def conflicting_route():
            return {}

        before = route_keys(app)
        try:
            register(app)
        except RuntimeError as exc:
            assert "duplicate route registration blocked" in str(exc)
        else:
            raise AssertionError("duplicate source route was accepted")
        assert route_keys(app) == before
        assert not getattr(app.state, "intel_sources_module_registered", False)
        assert not hasattr(app.state, "intel_source_snapshot_provider")


def check_install_disable_uninstall_reinstall_preserves_config() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-intel-sources-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        package = build_intel_sources_package(root / OFFICIAL_ASSET_NAME)
        digest = file_sha256(package)

        failed_manager = make_manager(root / "failed")
        try:
            failed_manager.install(package, "0" * 64, expected_module_id="intel_sources")
        except PackageValidationError:
            pass
        else:
            raise AssertionError("package with incorrect digest was installed")
        assert "intel_sources" not in failed_manager.snapshot()
        assert not (failed_manager.runtime_root / "intel_sources").exists()
        assert not (failed_manager.data_root / "intel_sources").exists()

        manager = make_manager(root / "lifecycle")
        installed = manager.install(
            package,
            digest,
            expected_module_id="intel_sources",
        )
        assert installed["install_status"] == "installed_disabled"
        assert installed["enabled"] is False
        manager.enable("intel_sources")

        config_path = root / "preserved" / "intel_sources.json"
        app, results = restarted_app(manager, config_path)
        assert results == [{"module_id": "intel_sources", "status": "loaded"}]
        saved = asyncio.run(
            call(app, "PUT", "/api/v1/intel-sources", json=FULL_PAYLOAD)
        )
        assert saved.status_code == 200
        original_bytes = config_path.read_bytes()
        assert asyncio.run(call(app, "GET", "/dashboard/intel-sources")).json()[
            "github_repos"
        ] == ["openai/openai-python"]

        manager.disable("intel_sources")
        disabled_app, disabled_results = restarted_app(manager, config_path)
        assert disabled_results == []
        assert asyncio.run(
            call(disabled_app, "GET", "/api/v1/intel-sources")
        ).status_code == 404

        uninstalled = manager.uninstall("intel_sources")
        assert uninstalled["data_preserved"] is True
        assert config_path.read_bytes() == original_bytes

        manager.install(package, digest, expected_module_id="intel_sources")
        manager.enable("intel_sources")
        restored_app, restored_results = restarted_app(manager, config_path)
        assert restored_results == [{"module_id": "intel_sources", "status": "loaded"}]
        restored = asyncio.run(
            call(restored_app, "GET", "/api/v1/intel-sources")
        )
        assert restored.status_code == 200
        assert restored.json()["github_repos"] == ["openai/openai-python"]
        assert restored.json()["using_local_override"] is True


def main() -> int:
    check_package_is_deterministic_allowlisted_and_secret_free()
    check_registration_uses_one_registry_provider_and_zero_network()
    check_route_conflict_is_rejected_before_partial_registration()
    check_install_disable_uninstall_reinstall_preserves_config()
    print("PK-115 installable intel_sources tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
