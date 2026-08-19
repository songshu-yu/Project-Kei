"""End-to-end, isolated checks for the installable focus module."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import (
    ManifestValidationError,
    ModuleConflictError,
    PackageValidationError,
)
from features.catalog.service import get_module_catalog
from features.focus.package_builder import (
    BACKEND_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_focus_package,
    file_sha256,
)
from features.focus.repository import FocusRepository
from features.focus.router import create_focus_router
from features.focus.service import FocusService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FOCUS_ROOT = PROJECT_ROOT / "server" / "features" / "focus"
RELEASE_ROOT = FOCUS_ROOT / "release"
RELEASE_FRAGMENT = RELEASE_ROOT / "official-release-fragment.json"
CATALOG_ENTRY = RELEASE_ROOT / "official-catalog-entry.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
CATALOG_GENERATED_AT = "2026-07-30T00:00:00Z"
EXPECTED_PACKAGE_NAMES = {
    "manifest.json",
    "dashboard/index.js",
    *(f"backend/{name}" for name in BACKEND_FILES),
}


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def restarted_app(manager: ModuleManager, state_path: Path) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    app.state.focus_state_path = state_path
    results = InProcessModuleLoader().load(app, manager.enabled_in_process_descriptors())
    manager.record_load_results(results)
    return app, results


def check_api_equivalence() -> None:
    async def scenario(prefix: str) -> list[dict]:
        with tempfile.TemporaryDirectory(prefix="kei-focus-api-") as temp_dir:
            current = datetime(2026, 7, 21, 11, 0, 0)
            service = FocusService(
                FocusRepository(Path(temp_dir) / "focus_timer.json"),
                clock=lambda: current,
                id_factory=lambda: "api-session",
            )

            async def synthesize(_text: str) -> bytes:
                return b"isolated-audio"

            app = FastAPI()
            app.include_router(create_focus_router(service, synthesize))
            responses = []
            responses.append((await call(app, "GET", f"{prefix}/status")).json())
            responses.append((await call(app, "POST", f"{prefix}/start", json={
                "mode": "pomodoro",
                "minutes": 5,
                "task": "api fixture",
                "force": False,
                "with_audio": True,
            })).json())
            responses.append((await call(app, "POST", f"{prefix}/start", json={
                "mode": "focus",
                "minutes": 10,
                "task": "duplicate fixture",
                "force": False,
                "with_audio": False,
            })).json())
            responses.append((await call(app, "POST", f"{prefix}/stop")).json())
            responses.append((await call(app, "POST", f"{prefix}/reset")).json())
            return responses

    versioned = asyncio.run(scenario("/api/v1/focus"))
    legacy = asyncio.run(scenario("/focus"))
    assert versioned == legacy
    assert versioned[1]["audio_base64"]
    assert versioned[2]["already_active"] is True


def check_controlled_encouragement_api() -> None:
    class FakeGenerator:
        system_prompt = "fictional Kei system"

        def __init__(self) -> None:
            self.calls = []

        async def generate_text(self, system: str, user: str, **kwargs):
            self.calls.append((system, user, kwargs))
            return SimpleNamespace(
                text="[emotion:happy] 继续守住这段专注，老师。",
                generated=True,
                error_code=None,
            )

    with tempfile.TemporaryDirectory(prefix="kei-focus-encouragement-") as temp_dir:
        root = Path(temp_dir)
        state_path = root / "focus_timer.json"
        current = datetime(2030, 1, 2, 8, 0, 0)
        service = FocusService(
            FocusRepository(state_path),
            clock=lambda: current,
            id_factory=lambda: "fictional-session",
        )
        generator = FakeGenerator()
        app = FastAPI()
        app.include_router(create_focus_router(
            service,
            text_generator_provider=lambda: generator,
            local_request_guard=lambda _request: True,
        ))
        started = asyncio.run(call(app, "POST", "/api/v1/focus/start", json={
            "mode": "pomodoro",
            "minutes": 25,
            "task": "must-not-reach-generator",
            "force": False,
            "with_audio": False,
        })).json()
        assert started["session_id"] == "fictional-session"
        generated = asyncio.run(call(app, "POST", "/api/v1/focus/encouragement", json={
            "session_id": started["session_id"],
            "start_at": started["start_at"],
        }))
        assert generated.status_code == 200
        assert generated.json() == {
            "eligible": True,
            "generated": True,
            "text": "继续守住这段专注，老师。",
            "error_code": None,
        }
        assert len(generator.calls) == 1
        serialized_call = repr(generator.calls)
        assert "must-not-reach-generator" not in serialized_call
        assert "openid" not in serialized_call.lower()
        assert generator.calls[0][2] == {
            "max_tokens": 90,
            "temperature": 0.8,
            "fallback": "",
        }

        mismatch = asyncio.run(call(app, "POST", "/api/v1/focus/encouragement", json={
            "session_id": "replacement-session",
            "start_at": started["start_at"],
        }))
        assert mismatch.status_code == 409
        assert len(generator.calls) == 1

        asyncio.run(call(app, "POST", "/api/v1/focus/stop"))
        stopped = asyncio.run(call(app, "POST", "/api/v1/focus/encouragement", json={
            "session_id": started["session_id"],
            "start_at": started["start_at"],
        }))
        assert stopped.status_code == 409
        assert len(generator.calls) == 1

        old_bytes = b'{"active_id":"broken","sessions":'
        state_path.write_bytes(old_bytes)
        corrupt = asyncio.run(call(app, "GET", "/api/v1/focus/status"))
        assert corrupt.status_code == 500
        assert state_path.read_bytes() == old_bytes
        assert len(generator.calls) == 1

        blocked = FastAPI()
        blocked.include_router(create_focus_router(
            FocusService(FocusRepository(root / "blocked.json")),
            text_generator_provider=lambda: generator,
            local_request_guard=lambda _request: False,
        ))
        rejected = asyncio.run(call(blocked, "POST", "/api/v1/focus/encouragement", json={
            "session_id": "fictional-session",
            "start_at": "2030-01-02T08:00:00",
        }))
        assert rejected.status_code == 403
        assert len(generator.calls) == 1


def _assert_package_contents(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = sorted(info.filename for info in infos)
        assert names == sorted(EXPECTED_PACKAGE_NAMES)
        assert len(names) == len(set(name.casefold() for name in names))
        combined = []
        for info in infos:
            assert not info.filename.startswith(("/", "\\"))
            assert "\\" not in info.filename
            assert ".." not in Path(info.filename).parts
            assert ":" not in info.filename.split("/", 1)[0]
            assert info.date_time == FIXED_ZIP_DATETIME
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.create_system == 3
            assert info.create_version == 20
            assert info.extract_version == 20
            assert info.internal_attr == 0
            assert info.external_attr == 0o100644 << 16
            assert info.extra == b""
            assert info.comment == b""
            combined.append(archive.read(info).decode("utf-8"))
    package_text = "\n".join(combined)
    assert "\r\n" not in package_text
    assert not re.search(r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b", package_text)
    assert "focus_timer.json" not in names
    assert not any(
        token in name.casefold()
        for name in names
        for token in (
            ".env", "registry", "runtime", "cache", "test", "fixture",
            "vendor", "script",
        )
    )


def check_deterministic_package_build() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-deterministic-") as temp_dir:
        root = Path(temp_dir)
        first = build_focus_package(root / "focus-first.zip")
        second = build_focus_package(root / "focus-second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        _assert_package_contents(first)
        _assert_package_contents(second)

        materialized = build_focus_package(root / "materialized")
        for path in materialized.rglob("*"):
            if path.is_file():
                assert b"\r\n" not in path.read_bytes()


def check_official_release_metadata() -> None:
    fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
    expected_entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
    assert fragment["module_id"] == "focus"
    assert fragment["version"] == OFFICIAL_RELEASE_VERSION
    assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
    assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
    assert fragment["permissions"] == ["local_state"]
    assert fragment["data_policy"] == "preserve_on_uninstall"
    assert fragment["requires_restart"] is True

    with tempfile.TemporaryDirectory(prefix="kei-focus-official-release-") as temp_dir:
        root = Path(temp_dir)
        asset_root = root / "assets"
        asset_root.mkdir()
        package = build_focus_package(asset_root / OFFICIAL_ASSET_NAME)
        output = root / "official-catalog.json"
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
                CATALOG_GENERATED_AT,
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr or completed.stdout)
        catalog = json.loads(output.read_text(encoding="utf-8"))
        assert catalog["owner"] == "songshu-yu"
        assert catalog["repository"] == "Project-Kei-Modules"
        assert catalog["modules"] == [expected_entry]

        with zipfile.ZipFile(package) as archive:
            manifest_raw = archive.read("manifest.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
        assert manifest["id"] == fragment["module_id"]
        assert manifest["name"] == fragment["name"]
        assert manifest["version"] == fragment["version"]
        assert manifest["core_compatibility"] == fragment["core_compatibility"]
        assert expected_entry["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
        assert expected_entry["package_size"] == package.stat().st_size
        assert expected_entry["package_sha256"] == file_sha256(package)
        assert expected_entry["package_url"] == (
            "https://github.com/songshu-yu/Project-Kei-Modules/releases/download/"
            f"{OFFICIAL_RELEASE_TAG}/{OFFICIAL_ASSET_NAME}"
        )
        _assert_package_contents(package)


def write_fixture_package(root: Path, module_id: str, namespace: str) -> Path:
    package = root / module_id
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": module_id,
        "name": module_id,
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": [namespace],
        "legacy_endpoints": [],
        "data_namespace": module_id,
        "permissions": [],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "backend" / "__init__.py").write_text(
        "def register(app):\n    return None\n", encoding="utf-8"
    )
    return package


def check_lifecycle_and_restart_loading() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-lifecycle-") as temp_dir:
        root = Path(temp_dir)
        manager = make_manager(root)
        package_v1 = build_focus_package(root / "focus-1.1.1.zip")
        package_v2 = build_focus_package(root / "focus-1.2.0.zip", version="1.2.0")
        _assert_package_contents(package_v1)
        digest_v1 = file_sha256(package_v1)
        assert manager.calculate_package_sha256(package_v1) == digest_v1

        installed = manager.install(package_v1, digest_v1, expected_module_id="focus")
        assert installed["install_status"] == "installed_disabled"
        assert installed["enabled"] is False and installed["requires_restart"] is True
        enabled = manager.enable("focus")
        assert enabled["enabled"] is True and enabled["restart_required"] is True

        completed_state_path = root / "isolated-completed-state" / "focus_timer.json"
        FocusService(FocusRepository(completed_state_path)).start(
            mode="pomodoro",
            minutes=0.1,
            task="completed restart fixture",
            now=datetime(2020, 1, 1, 0, 0, 0),
        )
        completed_app, completed_results = restarted_app(manager, completed_state_path)
        assert completed_results == [{"module_id": "focus", "status": "loaded"}]
        completed = asyncio.run(call(completed_app, "GET", "/api/v1/focus/status"))
        assert completed.status_code == 200
        assert completed.json()["completed"] is True
        assert completed.json()["remaining_seconds"] == 0

        state_path = root / "isolated-user-state" / "focus_timer.json"
        app, results = restarted_app(manager, state_path)
        assert results == [{"module_id": "focus", "status": "loaded"}]
        route_paths = {route.path for route in app.routes}
        expected_routes = {
            "/api/v1/focus/status", "/api/v1/focus/start", "/api/v1/focus/stop",
            "/api/v1/focus/reset", "/api/v1/focus/encouragement",
            "/focus/status", "/focus/start", "/focus/stop", "/focus/reset",
        }
        assert expected_routes <= route_paths
        started = asyncio.run(call(app, "POST", "/api/v1/focus/start", json={
            "mode": "focus", "minutes": 5, "task": "lifecycle fixture",
            "force": False, "with_audio": False,
        }))
        assert started.status_code == 200 and started.json()["started"] is True

        restored_app, restored_results = restarted_app(manager, state_path)
        assert restored_results == [{"module_id": "focus", "status": "loaded"}]
        restored = asyncio.run(call(restored_app, "GET", "/focus/status"))
        assert restored.status_code == 200 and restored.json()["active"] is True
        assert restored.json()["remaining_seconds"] > 0

        asset = manager.asset_path("focus", "dashboard/index.js")
        assert asset.is_file() and asset.name == "index.js"
        catalog = get_module_catalog(lifecycle_snapshot=manager.snapshot())
        focus_item = next(item for item in catalog["modules"] if item["key"] == "focus")
        assert focus_item["migration_status"] == "installable"
        assert focus_item["dashboard_entrypoint"].endswith("/dashboard/index.js")
        assert focus_item["enabled"] is True

        upgraded = manager.update("focus", package_v2, file_sha256(package_v2))
        assert upgraded["installed_version"] == "1.2.0"
        assert upgraded["enabled"] is True and upgraded["restart_required"] is True
        upgraded_app, upgraded_results = restarted_app(manager, state_path)
        assert upgraded_results == [{"module_id": "focus", "status": "loaded"}]
        assert asyncio.run(call(upgraded_app, "GET", "/api/v1/focus/status")).json()["active"]

        disabled = manager.disable("focus")
        assert disabled["install_status"] == "installed_disabled"
        assert disabled["restart_required"] is True
        # First-version semantics are explicit: the old app keeps registered routes.
        assert asyncio.run(call(upgraded_app, "GET", "/api/v1/focus/status")).status_code == 200
        disabled_app, disabled_results = restarted_app(manager, state_path)
        assert disabled_results == []
        assert asyncio.run(call(disabled_app, "GET", "/api/v1/focus/status")).status_code == 404
        try:
            manager.asset_path("focus", "dashboard/index.js")
        except ModuleConflictError:
            pass
        else:
            raise AssertionError("disabled focus dashboard asset remained available")

        uninstall_result = manager.uninstall("focus")
        assert uninstall_result["data_preserved"] is True
        assert state_path.is_file()
        uninstalled_app, uninstalled_results = restarted_app(manager, state_path)
        assert uninstalled_results == []
        assert asyncio.run(call(uninstalled_app, "GET", "/focus/status")).status_code == 404

        reinstalled = manager.install(package_v1, digest_v1, expected_module_id="focus")
        assert reinstalled["install_status"] == "installed_disabled"
        manager.enable("focus")
        reinstalled_app, reinstalled_results = restarted_app(manager, state_path)
        assert reinstalled_results == [{"module_id": "focus", "status": "loaded"}]
        relinked = asyncio.run(call(reinstalled_app, "GET", "/api/v1/focus/status"))
        assert relinked.status_code == 200 and relinked.json()["active"] is True

        module_data = root / "data" / "modules" / "focus"
        module_data.mkdir(parents=True, exist_ok=True)
        (module_data / "isolated-sentinel.txt").write_text("temporary", encoding="utf-8")
        try:
            manager.purge_data("focus", "FOCUS")
        except ModuleConflictError:
            pass
        else:
            raise AssertionError("inexact focus purge confirmation was accepted")
        assert module_data.is_dir() and state_path.is_file()
        purged = manager.purge_data("focus", "focus")
        assert purged["purged"] is True and not module_data.exists()
        assert state_path.is_file()


def check_failed_install_is_atomic() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-focus-failures-") as temp_dir:
        root = Path(temp_dir)
        package = build_focus_package(root / "focus.zip")

        wrong_hash_manager = make_manager(root / "wrong-hash")
        try:
            wrong_hash_manager.install(package, "0" * 64, expected_module_id="focus")
        except PackageValidationError:
            pass
        else:
            raise AssertionError("focus package with a wrong digest was accepted")
        assert "focus" not in wrong_hash_manager.snapshot()
        assert not (wrong_hash_manager.runtime_root / "focus").exists()

        malformed_root = root / "malformed-package"
        build_focus_package(malformed_root)
        malformed_manifest_path = malformed_root / "manifest.json"
        malformed_manifest = json.loads(malformed_manifest_path.read_text(encoding="utf-8"))
        malformed_manifest["install_script"] = "forbidden.ps1"
        malformed_manifest_path.write_text(json.dumps(malformed_manifest), encoding="utf-8")
        malformed_manager = make_manager(root / "malformed-manager")
        malformed_hash = malformed_manager.calculate_package_sha256(malformed_root)
        try:
            malformed_manager.install(
                malformed_root, malformed_hash, expected_module_id="focus"
            )
        except ManifestValidationError:
            pass
        else:
            raise AssertionError("focus package with an illegal manifest field was accepted")
        assert "focus" not in malformed_manager.snapshot()
        assert not (malformed_manager.runtime_root / "focus").exists()
        assert not (malformed_manager.data_root / "focus").exists()

        illegal_root = root / "illegal-package"
        build_focus_package(illegal_root)
        manifest_path = illegal_root / "manifest.json"
        illegal_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        illegal_manifest["api_namespaces"] = ["/api/v1/modules"]
        manifest_path.write_text(json.dumps(illegal_manifest), encoding="utf-8")
        illegal_manager = make_manager(root / "illegal-manager")
        illegal_hash = illegal_manager.calculate_package_sha256(illegal_root)
        try:
            illegal_manager.install(illegal_root, illegal_hash, expected_module_id="focus")
        except ModuleConflictError:
            pass
        else:
            raise AssertionError("focus package using a Core namespace was accepted")
        assert "focus" not in illegal_manager.snapshot()
        assert not (illegal_manager.runtime_root / "focus").exists()

        conflict_manager = make_manager(root / "conflict-manager")
        blocker = write_fixture_package(root, "focus_blocker", "/api/v1/focus")
        blocker_hash = conflict_manager.calculate_package_sha256(blocker)
        conflict_manager.install(blocker, blocker_hash, expected_module_id="focus_blocker")
        try:
            conflict_manager.install(package, file_sha256(package), expected_module_id="focus")
        except ModuleConflictError:
            pass
        else:
            raise AssertionError("focus namespace conflict was accepted")
        assert "focus" not in conflict_manager.snapshot()
        assert not (conflict_manager.runtime_root / "focus").exists()
        assert not (conflict_manager.data_root / "focus").exists()

        update_manager = make_manager(root / "failed-update-manager")
        valid_v1 = build_focus_package(root / "focus-update-v1.zip")
        update_manager.install(valid_v1, file_sha256(valid_v1), expected_module_id="focus")
        update_manager.enable("focus")
        invalid_v2 = root / "focus-update-v2"
        build_focus_package(invalid_v2, version="1.2.0")
        invalid_v2_manifest_path = invalid_v2 / "manifest.json"
        invalid_v2_manifest = json.loads(invalid_v2_manifest_path.read_text(encoding="utf-8"))
        invalid_v2_manifest["dashboard_entrypoint"] = "dashboard/missing.js"
        invalid_v2_manifest_path.write_text(json.dumps(invalid_v2_manifest), encoding="utf-8")
        invalid_v2_hash = update_manager.calculate_package_sha256(invalid_v2)
        try:
            update_manager.update("focus", invalid_v2, invalid_v2_hash)
        except PackageValidationError:
            pass
        else:
            raise AssertionError("focus update with a missing declared entrypoint was accepted")
        current = update_manager.get("focus")
        assert current["installed_version"] == "1.1.1" and current["enabled"] is True
        assert not (update_manager.runtime_root / "focus" / "1.2.0").exists()
        update_state = root / "failed-update-state" / "focus_timer.json"
        old_app, load_results = restarted_app(update_manager, update_state)
        assert load_results == [{"module_id": "focus", "status": "loaded"}]
        assert asyncio.run(call(old_app, "GET", "/api/v1/focus/status")).status_code == 200


def check_uninstalled_catalog_state() -> None:
    focus = next(
        item for item in get_module_catalog(lifecycle_snapshot={})["modules"]
        if item["key"] == "focus"
    )
    assert focus["install_status"] == "available"
    assert focus["enabled"] is False
    assert focus["managed"] is True
    assert focus["migration_status"] == "installable"
    assert focus["requires_restart"] is True


def main() -> int:
    check_api_equivalence()
    check_controlled_encouragement_api()
    check_deterministic_package_build()
    check_official_release_metadata()
    check_lifecycle_and_restart_loading()
    check_failed_install_is_atomic()
    check_uninstalled_catalog_state()
    print("focus module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
