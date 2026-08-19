"""PK-211 sidecar package tests with fake engine, HTTP, downloader, and Core."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx

SERVER_ROOT = Path(__file__).resolve().parents[5]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from core.modules import ModuleManager
from core.modules.exceptions import (
    ModuleConflictError,
    PackageValidationError,
    SidecarReadinessError,
)
from features.voice.models import SynthesisRequest, VoicePackRef
from features.voice.providers.gpt_sovits.acquisition import (
    AcquisitionError,
    LocalEngineRegistry,
    acquire_engine,
)
from features.voice.providers.gpt_sovits.descriptor import EngineDescriptor, load_descriptor
from features.voice.providers.gpt_sovits.package_builder import (
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_gpt_sovits_provider_package,
    file_sha256,
)
from features.voice.providers.gpt_sovits.provider import GPTSoVITSConfig, GPTSoVITSProvider
from features.voice.providers.gpt_sovits.sidecar_adapter import (
    GPTSoVITSSidecarAdapter,
    register_gpt_sovits_sidecar,
)


FEATURE_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE_FILES = {
    "config.schema.json",
    "dashboard/index.js",
    "manifest.json",
    "provider/__init__.py",
    "provider/acquisition.py",
    "provider/descriptor.py",
    "provider/engine.json",
    "provider/local_selection.py",
    "provider/provider.py",
    "provider/selection_router.py",
    "provider/sidecar_adapter.py",
}


class FakeProcess:
    def __init__(self) -> None:
        self.return_code = None
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self.return_code

    def terminate(self):
        self.terminate_calls += 1
        self.return_code = 0

    def kill(self):
        self.kill_calls += 1
        self.return_code = -9

    def wait(self, timeout=None):
        return 0 if self.return_code is None else self.return_code


class FakeProcessFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self.processes: list[FakeProcess] = []

    def __call__(self, arguments: list[str], working_directory: Path) -> FakeProcess:
        process = FakeProcess()
        self.calls.append((list(arguments), Path(working_directory)))
        self.processes.append(process)
        return process


class FakeHealth:
    def __init__(self, values) -> None:
        self.values = list(values)
        self.last = bool(self.values[-1]) if self.values else False
        self.calls = 0

    def __call__(self, _descriptor: EngineDescriptor) -> bool:
        self.calls += 1
        if self.values:
            self.last = bool(self.values.pop(0))
        return self.last


def _new_manager(root: Path) -> ModuleManager:
    return ModuleManager(
        runtime_root=root / "runtime" / "modules",
        registry_path=root / "data" / "module_registry.json",
        data_root=root / "data" / "modules",
    )


def _write_voice_dependency(root: Path) -> Path:
    package = root / "voice-1.0.0"
    package.mkdir(parents=True)
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
        "api_namespaces": ["/api/v1/fake-voice-contract"],
        "legacy_endpoints": [],
        "dashboard_entrypoint": None,
        "data_namespace": "voice",
        "config_schema": None,
        "permissions": ["local_state"],
        "requires_restart": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (package / "backend.py").write_text("def register(app):\n    return None\n", encoding="utf-8")
    return package


def _install_voice_dependency(manager: ModuleManager, root: Path) -> None:
    package = _write_voice_dependency(root / "packages")
    manager.install(package, manager.calculate_package_sha256(package), "voice")
    manager.enable("voice")


def _register_fake_engine(root: Path, registry_path: Path) -> Path:
    engine_root = root / "external-engine"
    (engine_root / "runtime").mkdir(parents=True)
    (engine_root / "runtime" / "python.exe").write_bytes(b"fake executable")
    (engine_root / "api.py").write_text("# fake engine entry\n", encoding="utf-8")
    LocalEngineRegistry(registry_path).register(
        load_descriptor(),
        engine_root,
        api_style="auto",
        install_status="registered_existing",
        integrity_status="unverified_existing_install",
    )
    return engine_root


def _fake_archive() -> bytes:
    with tempfile.TemporaryDirectory(prefix="kei-pk211-sidecar-archive-") as temp:
        path = Path(temp) / "fake.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("engine-root/api.py", "# fake\n")
            archive.writestr("engine-root/runtime/python.exe", b"fake")
            archive.writestr("engine-root/install.ps1", "must never execute")
        return path.read_bytes()


def _fake_descriptor(archive: bytes, *, digest: str | None = None) -> EngineDescriptor:
    commit = "a" * 40
    revision = "b" * 40
    return EngineDescriptor.from_mapping({
        "schema_version": 1,
        "engine_id": "gpt-sovits-test-fixed",
        "provider_key": "gpt-sovits",
        "provider_protocol_version": "pk210-tts-v1",
        "version": "test",
        "upstream": {
            "repository": "https://github.com/RVC-Boss/GPT-SoVITS",
            "release": "test-release",
            "commit": commit,
            "release_url": "https://github.com/RVC-Boss/GPT-SoVITS/releases/tag/test-release",
            "license": "MIT",
            "license_url": f"https://github.com/RVC-Boss/GPT-SoVITS/blob/{commit}/LICENSE",
        },
        "distribution": {
            "source_id": "fake-official",
            "repository": "https://huggingface.co/lj1995/GPT-SoVITS-windows-package",
            "revision": revision,
            "download_url": (
                "https://huggingface.co/lj1995/GPT-SoVITS-windows-package/resolve/"
                f"{revision}/fake.zip?download=true"
            ),
            "archive_name": "fake.zip",
            "archive_format": "zip",
            "archive_root": "engine-root",
            "size_bytes": len(archive),
            "integrity": {
                "algorithm": "sha256",
                "digest": digest or hashlib.sha256(archive).hexdigest(),
            },
        },
        "api_styles": {"default": "auto", "supported": ["auto", "api_py", "legacy_v2"]},
        "health_check": {"method": "GET", "path": "/docs", "timeout_seconds": 0.1},
        "capabilities": {
            "operations": ["synthesize", "health", "cancel", "close"],
            "audio_formats": ["wav"],
            "streaming": False,
            "default_timeout_seconds": 0.2,
            "port": 9880,
        },
        "installation": {
            "bundled": False,
            "source_tree_policy": "do_not_scan",
            "local_config": "server/data/gpt_sovits_engine.local.json",
            "default_status": "unregistered",
            "required_files": ["api.py", "runtime/python.exe"],
            "marker_file": ".project-kei-engine.json",
        },
        "archive_limits": {
            "max_files": 20,
            "max_uncompressed_bytes": 1024 * 1024,
            "max_compression_ratio": 100,
        },
    })


def test_package_is_deterministic_and_strictly_scoped() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-pk211-package-") as temp:
        root = Path(temp)
        first = build_gpt_sovits_provider_package(root / OFFICIAL_ASSET_NAME)
        second = build_gpt_sovits_provider_package(root / ("copy-" + OFFICIAL_ASSET_NAME))
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)

        with zipfile.ZipFile(first) as archive:
            names = set(archive.namelist())
            assert names == EXPECTED_PACKAGE_FILES
            assert not any(
                name.lower().endswith((".bat", ".ps1", ".env", ".pth", ".ckpt", ".onnx", ".wav"))
                or name.lower().startswith(("vendor/", "runtime/", "models/", "weights/"))
                for name in names
            )
            manifest = json.loads(archive.read("manifest.json"))
            schema = json.loads(archive.read("config.schema.json"))
            assert manifest["type"] == "sidecar"
            assert manifest["version"] == OFFICIAL_RELEASE_VERSION
            assert manifest["sidecar"]["adapter"] == "gpt_sovits_provider"
            assert manifest["api_namespaces"] == ["/api/v1/gpt-sovits-engine"]
            assert schema["properties"]["endpoint"]["const"] == "http://127.0.0.1:9880"
            assert "install_root" not in json.dumps(schema)
            assert str(FEATURE_ROOT.parent.parent.parent.parent.parent) not in archive.read(
                "config.schema.json"
            ).decode("utf-8")
            catalog_entry = json.loads(
                (FEATURE_ROOT / "release" / "official-catalog-entry.json").read_text(encoding="utf-8")
            )
            assert catalog_entry["package_size"] == first.stat().st_size
            assert catalog_entry["version"] == OFFICIAL_RELEASE_VERSION
            assert catalog_entry["release_tag"] == OFFICIAL_RELEASE_TAG
            assert catalog_entry["asset_name"] == OFFICIAL_ASSET_NAME
            assert catalog_entry["package_sha256"] == file_sha256(first)
            assert catalog_entry["manifest_sha256"] == hashlib.sha256(
                archive.read("manifest.json")
            ).hexdigest()


def test_no_engine_degrades_without_half_module_or_process() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-pk211-no-engine-") as temp:
        root = Path(temp)
        manager = _new_manager(root)
        _install_voice_dependency(manager, root)
        process_factory = FakeProcessFactory()
        register_gpt_sovits_sidecar(
            manager,
            registry_path=root / "local" / "engine.json",
            process_factory=process_factory,
            health_probe=FakeHealth([False]),
        )
        package = build_gpt_sovits_provider_package(root / OFFICIAL_ASSET_NAME)
        digest = manager.calculate_package_sha256(package)
        installed = manager.install(package, digest, "gpt_sovits_engine_provider")
        assert installed["install_status"] == "needs_configuration"
        assert installed["configuration_ready"] is False
        assert installed["sidecar_readiness"] == {
            "status": "needs_configuration",
            "code": "configuration_missing",
            "message": "sidecar configuration requirements are missing",
            "missing_requirements": ["engine_registration"],
        }
        try:
            manager.enable("gpt_sovits_engine_provider")
            raise AssertionError("missing engine registration must reject sidecar enable")
        except SidecarReadinessError as exc:
            assert exc.detail()["code"] == "sidecar_needs_configuration"
            assert exc.readiness.code == "configuration_missing"
        state = manager.get("gpt_sovits_engine_provider")
        assert state["enabled"] is False
        assert state["install_status"] == "needs_configuration"
        assert state["last_operation"]["status"] == "attention_required"
        assert process_factory.calls == []
        assert (
            root
            / "runtime"
            / "modules"
            / "gpt_sovits_engine_provider"
            / OFFICIAL_RELEASE_VERSION
        ).is_dir()
        assert set(manager.registry.load()["modules"]) == {
            "voice",
            "gpt_sovits_engine_provider",
        }
        assert manager.get("voice")["enabled"] is True


def test_deployment_readiness_maps_tamper_registration_and_entry_failures() -> None:
    cases = (
        ("package_tampered", "package_tampered"),
        ("registration_invalid", "deployment_invalid"),
        ("entrypoint_missing", "entrypoint_missing"),
    )
    for case, expected_code in cases:
        with tempfile.TemporaryDirectory(prefix="kei-pk211-readiness-") as temp:
            root = Path(temp)
            registry_path = root / "local" / "engine.json"
            manager = _new_manager(root)
            _install_voice_dependency(manager, root)
            register_gpt_sovits_sidecar(
                manager,
                registry_path=registry_path,
                process_factory=FakeProcessFactory(),
                health_probe=FakeHealth([False]),
            )
            package = build_gpt_sovits_provider_package(
                root / "gpt_sovits_engine_provider"
            )
            if case == "package_tampered":
                descriptor_path = package / "provider" / "engine.json"
                descriptor_payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
                descriptor_payload["engine_id"] = "gpt-sovits-tampered"
                descriptor_path.write_text(
                    json.dumps(descriptor_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            elif case == "registration_invalid":
                registry_path.parent.mkdir(parents=True)
                registry_path.write_text("{invalid", encoding="utf-8")
            else:
                engine_root = root / "external-engine"
                (engine_root / "runtime").mkdir(parents=True)
                (engine_root / "runtime" / "python.exe").write_bytes(b"fake")
                LocalEngineRegistry(registry_path).save({
                    "schema_version": 1,
                    "engine_id": load_descriptor().engine_id,
                    "install_root": str(engine_root),
                    "api_style": "auto",
                    "install_status": "registered_existing",
                    "integrity_status": "unverified_existing_install",
                })
            installed = manager.install(
                package,
                manager.calculate_package_sha256(package),
                "gpt_sovits_engine_provider",
            )
            assert installed["install_status"] == "needs_configuration"
            assert installed["sidecar_readiness"]["status"] == "unavailable"
            assert installed["sidecar_readiness"]["code"] == expected_code
            public = json.dumps(installed["sidecar_readiness"], ensure_ascii=False)
            assert str(root) not in public
            assert "{invalid" not in public.lower()


def test_digest_failure_and_interrupted_acquisition_leave_no_half_state() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-pk211-half-state-") as temp:
        root = Path(temp)
        manager = _new_manager(root)
        package = build_gpt_sovits_provider_package(root / OFFICIAL_ASSET_NAME)
        try:
            manager.install(package, "0" * 64, "gpt_sovits_engine_provider")
            raise AssertionError("wrong package digest must fail")
        except PackageValidationError:
            pass
        assert manager.snapshot() == {}
        assert not (root / "runtime" / "modules" / "gpt_sovits_engine_provider").exists()

        archive = _fake_archive()
        descriptor = _fake_descriptor(archive, digest="0" * 64)
        target = root / "external" / "bad-engine"
        registry_path = root / "local" / "engine.json"

        def fake_downloader(_descriptor: EngineDescriptor, destination: Path) -> None:
            destination.write_bytes(archive)

        try:
            acquire_engine(
                descriptor,
                target,
                confirmation=descriptor.engine_id,
                registry_path=registry_path,
                project_root=root / "project",
                downloader=fake_downloader,
            )
            raise AssertionError("wrong engine digest must fail")
        except AcquisitionError as exc:
            assert exc.code == "integrity_mismatch"
        assert not target.exists()
        assert not registry_path.exists()

        def interrupted(_descriptor: EngineDescriptor, _destination: Path) -> None:
            raise AcquisitionError("download_interrupted", "固定来源下载中断")

        try:
            acquire_engine(
                _fake_descriptor(archive),
                root / "external" / "interrupted-engine",
                confirmation="gpt-sovits-test-fixed",
                registry_path=registry_path,
                project_root=root / "project",
                downloader=interrupted,
            )
            raise AssertionError("interrupted download must fail")
        except AcquisitionError as exc:
            assert exc.code == "download_interrupted"
        assert not (root / "external" / "interrupted-engine").exists()
        assert not registry_path.exists()


def test_lifecycle_duplicate_start_and_uninstall_preserve_external_assets() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-pk211-lifecycle-") as temp:
        root = Path(temp)
        registry_path = root / "local" / "engine.json"
        engine_root = _register_fake_engine(root, registry_path)
        model_sentinel = engine_root / "user-model.ckpt"
        reference_sentinel = engine_root / "reference.wav"
        model_sentinel.write_bytes(b"user-owned-model")
        reference_sentinel.write_bytes(b"user-owned-reference")

        manager = _new_manager(root)
        _install_voice_dependency(manager, root)
        process_factory = FakeProcessFactory()
        health = FakeHealth([False, True, True, True])
        register_gpt_sovits_sidecar(
            manager,
            registry_path=registry_path,
            process_factory=process_factory,
            health_probe=health,
            sleeper=lambda _seconds: None,
        )
        package = build_gpt_sovits_provider_package(root / OFFICIAL_ASSET_NAME)
        digest = manager.calculate_package_sha256(package)
        manager.install(package, digest, "gpt_sovits_engine_provider")
        try:
            manager.install(package, digest, "gpt_sovits_engine_provider")
            raise AssertionError("duplicate package install must fail")
        except ModuleConflictError:
            pass

        enabled = manager.enable("gpt_sovits_engine_provider")
        assert enabled["enabled"] is True
        assert len(process_factory.calls) == 1
        arguments, working_directory = process_factory.calls[0]
        assert arguments[-4:] == ["-a", "127.0.0.1", "-p", "9880"]
        assert working_directory == engine_root
        assert not any(value.lower().endswith((".bat", ".ps1")) for value in arguments)

        assert manager.start_enabled_sidecars() == [
            {"module_id": "gpt_sovits_engine_provider", "status": "started"}
        ]
        assert len(process_factory.calls) == 1
        disabled = manager.disable("gpt_sovits_engine_provider")
        assert disabled["enabled"] is False
        assert process_factory.processes[0].terminate_calls == 1
        removed = manager.uninstall("gpt_sovits_engine_provider")
        assert removed["data_preserved"] is True
        assert model_sentinel.read_bytes() == b"user-owned-model"
        assert reference_sentinel.read_bytes() == b"user-owned-reference"
        assert registry_path.is_file()

        reinstalled = manager.install(package, digest, "gpt_sovits_engine_provider")
        assert reinstalled["install_status"] == "installed_disabled"
        assert model_sentinel.is_file() and reference_sentinel.is_file()


def test_existing_9880_is_attached_but_never_terminated() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-pk211-existing-") as temp:
        root = Path(temp)
        registry_path = root / "local" / "engine.json"
        _register_fake_engine(root, registry_path)
        manager = _new_manager(root)
        _install_voice_dependency(manager, root)
        process_factory = FakeProcessFactory()
        register_gpt_sovits_sidecar(
            manager,
            registry_path=registry_path,
            process_factory=process_factory,
            health_probe=FakeHealth([True, True]),
        )
        package = build_gpt_sovits_provider_package(root / OFFICIAL_ASSET_NAME)
        manager.install(package, manager.calculate_package_sha256(package), "gpt_sovits_engine_provider")
        manager.enable("gpt_sovits_engine_provider")
        manager.disable("gpt_sovits_engine_provider")
        assert process_factory.calls == []


def test_provider_session_uses_fake_9880_only() -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/docs":
            return httpx.Response(200, text="fake docs")
        if request.method == "POST" and request.url.path == "/":
            return httpx.Response(200, content=b"RIFFfake-wave", headers={"content-type": "audio/wav"})
        return httpx.Response(404)

    async def scenario() -> None:
        provider = GPTSoVITSProvider(
            GPTSoVITSConfig(timeout_seconds=0.2),
            transport=httpx.MockTransport(handler),
        )
        health = await provider.health()
        assert health.available is True
        result = await provider.synthesize(
            SynthesisRequest(
                request_id="fake-session",
                text="测试",
                emotion="calm",
                timeout_seconds=0.2,
            ),
            VoicePackRef("fake", "1.0.0", "gpt-sovits", handle={}),
        )
        assert result.audio == b"RIFFfake-wave"
        await provider.close()

    asyncio.run(scenario())
    assert calls == [("GET", "/docs"), ("POST", "/")]


def main() -> int:
    test_package_is_deterministic_and_strictly_scoped()
    test_no_engine_degrades_without_half_module_or_process()
    test_deployment_readiness_maps_tamper_registration_and_entry_failures()
    test_digest_failure_and_interrupted_acquisition_leave_no_half_state()
    test_lifecycle_duplicate_start_and_uninstall_preserve_external_assets()
    test_existing_9880_is_attached_but_never_terminated()
    test_provider_session_uses_fake_9880_only()
    print("GPT-SoVITS installable Provider package tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
