"""Offline installable-module checks for PK-212 Voice Pack Registry."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ManifestValidationError, PackageValidationError
from features.voice_pack_registry.package_builder import (
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_voice_pack_registry_package,
    file_sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = PROJECT_ROOT / "server" / "features" / "voice_pack_registry"
RELEASE_FRAGMENT = FEATURE_ROOT / "release" / "official-release-fragment.json"
CATALOG_ENTRY = FEATURE_ROOT / "release" / "official-catalog-entry.json"
CATALOG_BUILDER = PROJECT_ROOT / "scripts" / "build_official_module_catalog.py"
EXPECTED_PACKAGE_FILES = {
    "backend/__init__.py",
    "backend/contracts.py",
    "backend/errors.py",
    "backend/manifest.py",
    "backend/module.py",
    "backend/registry.py",
    "backend/router.py",
    "backend/security.py",
    "backend/service.py",
    "dashboard/index.js",
    "manifest.json",
    "schemas/voice-pack.schema.json",
}


async def call(app: FastAPI, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43120))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
    ) as client:
        return await client.request(method, path, **kwargs)


def make_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "module-runtime",
        registry_path=root / "module-registry.json",
        data_root=root / "module-data",
    )


def write_voice_dependency(root: Path) -> Path:
    package = root / "voice"
    (package / "backend").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": "voice",
        "name": "Fake voice contract",
        "version": "1.0.0",
        "type": "in_process",
        "required": False,
        "core_compatibility": ">=1.0.0 <2.0.0",
        "entrypoint": "backend.register",
        "dependencies": [],
        "optional_dependencies": [],
        "conflicts": [],
        "api_namespaces": ["/api/v1/voice"],
        "legacy_endpoints": [],
        "dashboard_entrypoint": None,
        "data_namespace": "voice",
        "permissions": [],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (package / "backend" / "__init__.py").write_text(
        "def register(app):\n"
        "    app.state.fake_voice_contract_loaded = True\n",
        encoding="utf-8",
    )
    return package


def install_and_enable(manager: ModuleManager, package: Path, module_id: str) -> None:
    digest = manager.calculate_package_sha256(package)
    manager.install(package, digest, expected_module_id=module_id)
    manager.enable(module_id)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_fake_voice_pack(root: Path, pack_id: str, marker: bytes) -> Path:
    package = root / pack_id
    (package / "models").mkdir(parents=True)
    (package / "reference").mkdir(parents=True)
    assets = {
        "models/gpt.ckpt": b"fake-gpt-" + marker,
        "models/sovits.pth": b"fake-sovits-" + marker,
        "reference/sample.wav": b"RIFF-fake-wave-" + marker,
    }
    for relative, content in assets.items():
        (package / relative).write_bytes(content)

    def asset(relative: str) -> dict:
        content = assets[relative]
        return {
            "path": relative,
            "integrity": {
                "mode": "sha256",
                "size_bytes": len(content),
                "sha256": sha256_bytes(content),
            },
        }

    manifest = {
        "schema_version": 1,
        "id": pack_id,
        "name": f"Fake {pack_id}",
        "version": "1.0.0",
        "engine": {
            "provider": "gpt-sovits",
            "protocol_version": "1.0",
        },
        "supported_languages": ["zh"],
        "gpt_checkpoint": asset("models/gpt.ckpt"),
        "sovits_checkpoint": asset("models/sovits.pth"),
        "reference_audio": asset("reference/sample.wav"),
        "reference_text": "完全虚构的测试提示文本",
        "reference_language": "zh",
        "default_text_language": "zh",
        "generation_parameters": {"temperature": 1.0},
        "metadata": {
            "source": "temporary-test-fixture",
            "author": "test",
            "license": "test-only",
            "redistribution": "restricted",
        },
    }
    (package / "voice-pack.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return package


class FakeActivator:
    def __init__(self) -> None:
        self.resolver = None
        self.active = None
        self.fail_pack_id = None
        self.calls = []

    def set_voice_pack_resolver(self, resolver) -> None:
        self.resolver = resolver

    def voice_pack_state(self) -> dict:
        return {"status": "active"}

    async def activate_voice_pack(self, voice_pack) -> None:
        self.calls.append(voice_pack)
        if voice_pack.pack_id == self.fail_pack_id:
            raise RuntimeError("synthetic activation failure")
        self.active = voice_pack


def make_loaded_app(
    manager: ModuleManager,
    registry_path: Path,
    runtime_root: Path,
    activator: FakeActivator | None,
) -> tuple[FastAPI, list[dict]]:
    app = FastAPI()
    app.state.voice_pack_registry_path = registry_path
    app.state.voice_pack_runtime_root = runtime_root
    app.state.voice_pack_activator = activator
    results = InProcessModuleLoader().load(
        app,
        manager.enabled_in_process_descriptors(),
    )
    manager.record_load_results(results)
    return app, results


def test_deterministic_asset_free_package_and_release_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpr-build-") as temp:
        root = Path(temp)
        first = build_voice_pack_registry_package(root / "first.zip")
        second = build_voice_pack_registry_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)

        with zipfile.ZipFile(first) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            names = {item.filename for item in infos}
            assert names == EXPECTED_PACKAGE_FILES
            assert len(names) == len({name.casefold() for name in names})
            rendered = []
            for item in infos:
                assert item.date_time == FIXED_ZIP_DATETIME
                assert item.compress_type == zipfile.ZIP_STORED
                assert item.create_system == 3
                assert item.external_attr == 0o100644 << 16
                assert not item.filename.startswith(("/", "\\"))
                assert "\\" not in item.filename
                assert ".." not in Path(item.filename).parts
                rendered.append(archive.read(item).decode("utf-8"))
            manifest_raw = archive.read("manifest.json")
        text = "\n".join(rendered)
        assert "\r\n" not in text
        assert not re.search(r"(?i)\b[A-Z]:[\\/](?:Users|AppData|Desktop|Temp)\b", text)
        assert not any(
            name.lower().endswith((".bat", ".cmd", ".exe", ".ps1", ".sh", ".wav", ".ckpt", ".pth"))
            for name in names
        )
        assert not any(
            token in name.casefold()
            for name in names
            for token in (
                ".env",
                "voice-pack.json",
                "local.json",
                "vendor",
                "installer",
                "hook",
            )
        )

        fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
        expected = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
        assert fragment["module_id"] == "voice_pack_registry"
        assert fragment["version"] == OFFICIAL_RELEASE_VERSION
        assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
        assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
        assert fragment["dependencies"] == ["voice"]
        assert fragment["data_policy"] == "preserve_on_uninstall"
        assert expected["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
        assert expected["package_size"] == first.stat().st_size
        assert expected["package_sha256"] == file_sha256(first)

        asset_root = root / "assets"
        asset_root.mkdir()
        official_asset = build_voice_pack_registry_package(asset_root / OFFICIAL_ASSET_NAME)
        output = root / "catalog.json"
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
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0
        catalog = json.loads(output.read_text(encoding="utf-8"))
        assert catalog["modules"] == [expected]
        assert official_asset.read_bytes() == first.read_bytes()


def test_install_switch_rollback_uninstall_preserves_assets_and_reinstall() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpr-lifecycle-") as temp:
        root = Path(temp)
        manager = make_manager(root)
        voice = write_voice_dependency(root / "packages")
        module = build_voice_pack_registry_package(root / OFFICIAL_ASSET_NAME)
        install_and_enable(manager, voice, "voice")
        install_and_enable(manager, module, "voice_pack_registry")

        pack_one = write_fake_voice_pack(root / "packs", "alpha", b"one")
        pack_two = write_fake_voice_pack(root / "packs", "beta", b"two")
        registry_path = root / "local-state" / "voice_pack_registry.local.json"
        voice_runtime = root / "local-state" / "voice-packs"
        activator = FakeActivator()
        app, results = make_loaded_app(
            manager,
            registry_path,
            voice_runtime,
            activator,
        )
        assert results == [
            {"module_id": "voice", "status": "loaded"},
            {"module_id": "voice_pack_registry", "status": "loaded"},
        ]
        assert activator.resolver is app.state.voice_pack_registry_service
        assert app.state.voice_pack_resolver is activator.resolver
        replacement_activator = FakeActivator()
        app.state.voice_pack_registry_bind_activator(replacement_activator)
        assert replacement_activator.resolver is app.state.voice_pack_resolver
        app.state.voice_pack_registry_bind_activator(activator)
        assert app.state.voice_pack_registry_module_mode == "installable"
        assert app.state.fake_voice_contract_loaded is True

        for package in (pack_one, pack_two):
            response = asyncio.run(
                call(
                    app,
                    "POST",
                    "/api/v1/voice-packs/import",
                    json={"package_path": str(package)},
                )
            )
            assert response.status_code == 200
            assert str(root) not in response.text

        for pack_id in ("alpha", "beta"):
            enabled = asyncio.run(
                call(
                    app,
                    "POST",
                    f"/api/v1/voice-packs/{pack_id}/1.0.0/enable",
                )
            )
            assert enabled.status_code == 200
        selected = asyncio.run(
            call(app, "POST", "/api/v1/voice-packs/alpha/1.0.0/select")
        )
        assert selected.status_code == 200
        assert activator.active.pack_id == "alpha"

        before_failed_switch = registry_path.read_bytes()
        activator.fail_pack_id = "beta"
        failed = asyncio.run(
            call(app, "POST", "/api/v1/voice-packs/beta/1.0.0/select")
        )
        assert failed.status_code == 503
        assert registry_path.read_bytes() == before_failed_switch
        snapshot = asyncio.run(call(app, "GET", "/api/v1/voice-packs")).json()
        assert snapshot["active"] == "alpha@1.0.0"
        assert activator.active.pack_id == "alpha"

        source_sentinels = {
            path: path.read_bytes()
            for path in (pack_one / "models").iterdir()
        }
        source_sentinels.update({
            path: path.read_bytes()
            for path in (pack_two / "reference").iterdir()
        })
        registry_bytes = registry_path.read_bytes()
        removed = manager.uninstall("voice_pack_registry")
        assert removed["data_preserved"] is True
        assert registry_path.read_bytes() == registry_bytes
        for path, content in source_sentinels.items():
            assert path.read_bytes() == content
        assert pack_one.is_dir() and pack_two.is_dir()

        install_and_enable(manager, module, "voice_pack_registry")
        restored_activator = FakeActivator()
        restored_app, restored_results = make_loaded_app(
            manager,
            registry_path,
            voice_runtime,
            restored_activator,
        )
        assert restored_results == [
            {"module_id": "voice", "status": "loaded"},
            {"module_id": "voice_pack_registry", "status": "loaded"},
        ]
        restored = asyncio.run(
            call(restored_app, "GET", "/api/v1/voice-packs")
        )
        assert restored.status_code == 200
        assert restored.json()["active"] == "alpha@1.0.0"
        assert {item["id"] for item in restored.json()["packs"]} == {"alpha", "beta"}
        assert registry_path.read_bytes() == registry_bytes


def test_empty_registry_no_engine_and_duplicate_routes_are_safe() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpr-empty-") as temp:
        root = Path(temp)
        manager = make_manager(root)
        voice = write_voice_dependency(root / "packages")
        module = build_voice_pack_registry_package(root / OFFICIAL_ASSET_NAME)
        install_and_enable(manager, voice, "voice")
        install_and_enable(manager, module, "voice_pack_registry")

        registry_path = root / "empty" / "voice_pack_registry.local.json"
        app = FastAPI()

        @app.get("/core-health")
        async def core_health() -> dict:
            return {"ok": True}

        app.state.voice_pack_registry_path = registry_path
        app.state.voice_pack_runtime_root = root / "empty" / "runtime"
        loader = InProcessModuleLoader()
        first = loader.load(app, manager.enabled_in_process_descriptors())
        assert all(item["status"] == "loaded" for item in first)
        paths_before = [route.path for route in app.routes]
        second = loader.load(app, manager.enabled_in_process_descriptors())
        assert all(item["status"] == "already_loaded" for item in second)
        third = InProcessModuleLoader().load(
            app,
            manager.enabled_in_process_descriptors(),
        )
        assert all(item["status"] == "loaded" for item in third)
        assert [route.path for route in app.routes] == paths_before
        assert len(
            [path for path in paths_before if path.startswith("/api/v1/voice-packs")]
        ) == 6
        assert asyncio.run(call(app, "GET", "/core-health")).json() == {"ok": True}
        empty = asyncio.run(call(app, "GET", "/api/v1/voice-packs"))
        assert empty.status_code == 200
        assert empty.json()["active"] is None
        assert empty.json()["packs"] == []
        assert not registry_path.exists()

        static_app = FastAPI()

        @static_app.get("/api/v1/voice-packs")
        async def existing() -> dict:
            return {"existing": True}

        static_app.state.voice_pack_registry_path = root / "must-not-exist.json"
        static_results = InProcessModuleLoader().load(
            static_app,
            [
                item
                for item in manager.enabled_in_process_descriptors()
                if item["manifest"]["id"] == "voice_pack_registry"
            ],
        )
        assert static_results == [
            {"module_id": "voice_pack_registry", "status": "loaded"}
        ]
        assert static_app.state.voice_pack_registry_module_mode == "existing_routes"
        assert len(
            [
                route
                for route in static_app.routes
                if route.path.startswith("/api/v1/voice-packs")
            ]
        ) == 1
        assert not (root / "must-not-exist.json").exists()


def _malicious_archive(path: Path, info: zipfile.ZipInfo) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr(info, "malicious")
    return path


def _assert_rejected_without_state(manager: ModuleManager, archive: Path) -> None:
    try:
        manager.install(
            archive,
            manager.calculate_package_sha256(archive),
            expected_module_id="voice_pack_registry",
        )
    except (PackageValidationError, ManifestValidationError):
        pass
    else:
        raise AssertionError("malicious module archive was accepted")
    assert manager.snapshot() == {}
    assert not (manager.runtime_root / "voice_pack_registry").exists()


def test_malicious_module_zips_are_rejected_without_runtime_state() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpr-malicious-") as temp:
        root = Path(temp)
        cases = {
            "traversal": zipfile.ZipInfo("../escape.txt"),
            "absolute": zipfile.ZipInfo("/escape.txt"),
            "drive": zipfile.ZipInfo("C:/escape.txt"),
        }
        symlink = zipfile.ZipInfo("linked.txt")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases["symlink"] = symlink
        reparse = zipfile.ZipInfo("junction")
        reparse.create_system = 0
        reparse.external_attr = 0x400
        cases["reparse"] = reparse

        for name, info in cases.items():
            manager = make_manager(root / name)
            archive = _malicious_archive(root / f"{name}.zip", info)
            _assert_rejected_without_state(manager, archive)
        assert not (root / "escape.txt").exists()

        script_source = build_voice_pack_registry_package(root / "script-source")
        manifest_path = script_source / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["install_script"] = "evil.ps1"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (script_source / "evil.ps1").write_text(
            "Write-Output 'must never run'",
            encoding="utf-8",
        )
        script_zip = root / "script.zip"
        with zipfile.ZipFile(script_zip, "w") as archive:
            for path in sorted(script_source.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(script_source).as_posix())
        script_manager = make_manager(root / "script-manager")
        _assert_rejected_without_state(script_manager, script_zip)
        assert not (root / "script-manager" / "evil-ran.txt").exists()


def test_dashboard_entrypoint_is_scoped_and_has_no_browser_persistence() -> None:
    source = (
        FEATURE_ROOT / "package_source" / "dashboard" / "index.js"
    ).read_text(encoding="utf-8")
    assert "export async function mount(context)" in source
    assert "export async function unmount()" in source
    assert "/api/v1/voice-packs" in source
    assert "/api/v1/modules" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "indexedDB" not in source
    assert "source_assets_deleted" not in source
    assert "不会删除" in source


def main() -> int:
    test_deterministic_asset_free_package_and_release_metadata()
    test_install_switch_rollback_uninstall_preserves_assets_and_reinstall()
    test_empty_registry_no_engine_and_duplicate_routes_are_safe()
    test_malicious_module_zips_are_rejected_without_runtime_state()
    test_dashboard_entrypoint_is_scoped_and_has_no_browser_persistence()
    print("voice_pack_registry installable module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
