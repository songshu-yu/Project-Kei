"""Offline installable-module checks for PK-213 Voice Pack distribution."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
from fastapi import FastAPI

import _path_setup  # noqa: F401

from core.modules import InProcessModuleLoader, ModuleManager
from core.modules.exceptions import ModuleConflictError
from features.voice.voice_packs.distribution import (
    package_builder as distribution_package_builder,
)
from features.voice.voice_packs.distribution.package_builder import (
    EXPECTED_PACKAGE_FILES,
    FIXED_ZIP_DATETIME,
    OFFICIAL_ASSET_NAME,
    OFFICIAL_RELEASE_TAG,
    OFFICIAL_RELEASE_VERSION,
    build_voice_pack_distribution_package,
    file_sha256,
)
from features.voice_pack_registry.package_builder import (
    build_voice_pack_registry_package,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_ROOT = (
    PROJECT_ROOT / "server" / "features" / "voice" / "voice_packs" / "distribution"
)
RELEASE_FRAGMENT = FEATURE_ROOT / "release" / "official-release-fragment.json"
CATALOG_ENTRY = FEATURE_ROOT / "release" / "official-catalog-entry.json"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def write_fake_pack(
    root: Path,
    *,
    pack_id: str = "fake-kei",
    version: str = "1.0.0",
    marker: bytes = b"A",
) -> Path:
    package = root / f"{pack_id}-{version}-{marker.decode('ascii')}"
    (package / "models").mkdir(parents=True)
    (package / "references").mkdir(parents=True)
    assets = {
        "models/gpt.ckpt": b"fake-gpt-" + marker,
        "models/sovits.pth": b"fake-sovits-" + marker,
        "references/sample.wav": b"RIFF-fake-wave-" + marker,
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
        "name": "Fictional test voice",
        "version": version,
        "engine": {"provider": "gpt-sovits", "protocol_version": "1.0"},
        "supported_languages": ["zh"],
        "gpt_checkpoint": asset("models/gpt.ckpt"),
        "sovits_checkpoint": asset("models/sovits.pth"),
        "reference_audio": asset("references/sample.wav"),
        "reference_text": "完全虚构的测试文本",
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
    (package / "README.md").write_text("fake\n", encoding="utf-8")
    (package / "LICENSE.txt").write_text("test-only\n", encoding="utf-8")
    (package / "NOTICE.txt").write_text("fictional\n", encoding="utf-8")
    return package


def release_zip(pack: Path, destination: Path, *, root_name: str) -> Path:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(
            (item for item in pack.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(pack).as_posix(),
        ):
            archive.write(
                path,
                f"{root_name}/{path.relative_to(pack).as_posix()}",
            )
    return destination


def catalog_payload(archive: Path, *, pack_id: str = "fake-kei") -> dict:
    return {
        "catalog_schema_version": 1,
        "pack_id": pack_id,
        "version": "1.0.0",
        "display_name": "Fictional test voice",
        "engine_id": "gpt-sovits-v2pro-nvidia50",
        "language": "zh",
        "core_compatibility": ">=1.0.0 <2.0.0",
        "voice_pack_schema_version": 1,
        "engine_protocol": "pk210-tts-v1",
        "engine_compatibility": ">=1.0.0 <2.0.0",
        "download_url": "https://releases.example.test/fake.zip",
        "allowed_redirect_hosts": ["releases.example.test"],
        "size_bytes": archive.stat().st_size,
        "sha256": file_sha256(archive),
        "archive_root": f"{pack_id}-voice-pack",
        "max_files": 16,
        "max_file_bytes": 1024 * 1024,
        "max_uncompressed_bytes": 4 * 1024 * 1024,
        "max_compression_ratio": 20.0,
        "license_url": "https://docs.example.test/license",
        "notice_url": "https://docs.example.test/notice",
        "release_tag": "fake-voice-v1.0.0",
        "revision": "1" * 40,
        "published_at": "2026-01-01T00:00:00Z",
        "recommend_select": False,
    }


class FakeDownloader:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = 0

    def download(self, _entry, destination: Path) -> dict:
        self.calls += 1
        Path(destination).write_bytes(self.payload)
        return {
            "size_bytes": len(self.payload),
            "sha256": sha256_bytes(self.payload),
            "redirects": 0,
        }


def install_and_enable(manager: ModuleManager, package: Path, module_id: str) -> None:
    digest = manager.calculate_package_sha256(package)
    manager.install(package, digest, expected_module_id=module_id)
    manager.enable(module_id)


def prepare_packages(root: Path, archive: Path) -> tuple[ModuleManager, Path]:
    manager = make_manager(root)
    voice = write_voice_dependency(root / "packages")
    registry = build_voice_pack_registry_package(
        root / "packages" / "voice_pack_registry"
    )
    distribution = build_voice_pack_distribution_package(
        root / "packages" / "voice_pack_distribution"
    )
    entry = catalog_payload(archive)
    (distribution / "catalog" / "fake-kei-1.0.0.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    install_and_enable(manager, voice, "voice")
    install_and_enable(manager, registry, "voice_pack_registry")
    install_and_enable(manager, distribution, "voice_pack_distribution")
    return manager, distribution


def load_app(
    manager: ModuleManager,
    root: Path,
    downloader: FakeDownloader,
) -> FastAPI:
    for module_id in ("voice_pack_registry", "voice_pack_distribution"):
        prefix = f"_project_kei_module_{module_id}_"
        for name in list(sys.modules):
            if name.startswith(prefix):
                sys.modules.pop(name, None)
    app = FastAPI()
    app.state.voice_pack_registry_path = root / "voice-pack-registry.json"
    app.state.voice_pack_runtime_root = root / "voice-pack-runtime"
    app.state.voice_pack_distribution_cache_root = root / "download-cache"
    app.state.voice_pack_distribution_downloader = downloader
    app.state.voice_pack_engine_status = lambda: {
        "engine_id": "gpt-sovits-v2pro-nvidia50",
        "configured": False,
        "entrypoints_ready": False,
        "status": "unregistered",
    }
    results = InProcessModuleLoader().load(
        app,
        manager.enabled_in_process_descriptors(),
    )
    manager.record_load_results(results)
    assert all(item["status"] == "loaded" for item in results), results
    return app


def test_package_source_exact_allowlist_and_unknown_file_fails_closed() -> None:
    current = {
        path.relative_to(distribution_package_builder.PACKAGE_SOURCE).as_posix()
        for path in distribution_package_builder._source_files()
    }
    assert current == EXPECTED_PACKAGE_FILES

    with tempfile.TemporaryDirectory(prefix="kei-vpd-allowlist-") as temp:
        root = Path(temp)
        source = root / "package_source"
        shutil.copytree(
            distribution_package_builder.PACKAGE_SOURCE,
            source,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        cache = source / "backend" / "__pycache__"
        cache.mkdir()
        (cache / "service.cpython-310.opt-1.pyc").write_bytes(
            b"synthetic-bytecode-cache"
        )
        original_source = distribution_package_builder.PACKAGE_SOURCE
        distribution_package_builder.PACKAGE_SOURCE = source
        try:
            cached = {
                path.relative_to(source).as_posix()
                for path in distribution_package_builder._source_files()
            }
            assert cached == EXPECTED_PACKAGE_FILES

            (source / "backend" / "unexpected.py").write_text(
                "raise RuntimeError('must never be packaged')\n",
                encoding="utf-8",
            )
            destination = root / "unexpected.zip"
            try:
                build_voice_pack_distribution_package(destination)
            except RuntimeError as exc:
                assert str(exc) == "package source file allowlist changed"
            else:
                raise AssertionError("unknown package source must fail closed")
            assert not destination.exists()
        finally:
            distribution_package_builder.PACKAGE_SOURCE = original_source


def test_deterministic_asset_free_package_and_release_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpd-build-") as temp:
        root = Path(temp)
        first = build_voice_pack_distribution_package(root / "first.zip")
        second = build_voice_pack_distribution_package(root / "second.zip")
        assert first.read_bytes() == second.read_bytes()
        assert file_sha256(first) == file_sha256(second)
        with zipfile.ZipFile(first) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            assert {item.filename for item in infos} == EXPECTED_PACKAGE_FILES
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["version"] == OFFICIAL_RELEASE_VERSION
            assert manifest["permissions"] == [
                "local_state",
                "network_download",
            ]
            rendered = []
            for item in infos:
                assert item.date_time == FIXED_ZIP_DATETIME
                assert item.compress_type == zipfile.ZIP_STORED
                assert item.external_attr == 0o100644 << 16
                rendered.append(archive.read(item).decode("utf-8"))
        text = "\n".join(rendered)
        assert "\r\n" not in text
        assert "api_key" not in text.lower()
        assert "cookie" not in text.lower()
        fragment = json.loads(RELEASE_FRAGMENT.read_text(encoding="utf-8"))
        assert fragment["release_tag"] == OFFICIAL_RELEASE_TAG
        assert fragment["asset_name"] == OFFICIAL_ASSET_NAME
        assert fragment["version"] == OFFICIAL_RELEASE_VERSION
        assert fragment["dependencies"] == ["voice_pack_registry"]
        assert fragment["permissions"] == ["local_state", "network_download"]
        catalog_entry = json.loads(CATALOG_ENTRY.read_text(encoding="utf-8"))
        assert catalog_entry["version"] == OFFICIAL_RELEASE_VERSION
        assert catalog_entry["permissions"] == [
            "local_state",
            "network_download",
        ]
        assert catalog_entry["package_sha256"] == file_sha256(first)
        assert catalog_entry["package_size"] == first.stat().st_size
        with zipfile.ZipFile(first) as archive:
            manifest_bytes = archive.read("manifest.json")
        assert catalog_entry["manifest_sha256"] == sha256_bytes(manifest_bytes)


def test_module_install_idempotency_conflict_and_uninstall_retains_data() -> None:
    async def scenario() -> None:
        with tempfile.TemporaryDirectory(prefix="kei-vpd-module-") as temp:
            root = Path(temp)
            trusted_pack = write_fake_pack(root / "fixtures", marker=b"A")
            archive = release_zip(
                trusted_pack,
                root / "trusted.zip",
                root_name="fake-kei-voice-pack",
            )
            downloader = FakeDownloader(archive.read_bytes())
            manager, distribution_source = prepare_packages(root, archive)
            app = load_app(manager, root, downloader)
            service = app.state.voice_pack_distribution_service

            snapshot = await service.list()
            assert downloader.calls == 0
            assert snapshot["releases"][0]["installed"] is False
            status = await service.status("fake-kei@1.0.0")
            assert status["installed"] is False
            assert downloader.calls == 0
            downloaded = await service.download_only(
                "fake-kei@1.0.0",
                confirmation="fake-kei@1.0.0",
            )
            assert downloaded["status"] == "downloaded"
            assert downloader.calls == 1

            installed = await service.install(
                "fake-kei@1.0.0",
                confirmation="fake-kei@1.0.0",
                select=False,
            )
            assert installed["status"] == "installed"
            same = await service.install(
                "fake-kei@1.0.0",
                confirmation="fake-kei@1.0.0",
                select=False,
            )
            assert same["status"] == "already_installed"
            assert downloader.calls == 1

            registry = app.state.voice_pack_registry_service
            await registry.unregister("fake-kei", "1.0.0")
            await registry.import_pack(trusted_pack)
            same_local = await service.install(
                "fake-kei@1.0.0",
                confirmation="fake-kei@1.0.0",
                select=False,
            )
            assert same_local["status"] == "already_installed"
            assert downloader.calls == 1

            await registry.unregister("fake-kei", "1.0.0")
            conflict = write_fake_pack(root / "fixtures", marker=b"B")
            await registry.import_pack(conflict)
            before = await registry.list_packs()
            cache_file = next((root / "download-cache").glob("*.zip"))
            cache_bytes = cache_file.read_bytes()
            try:
                await service.install(
                    "fake-kei@1.0.0",
                    confirmation="fake-kei@1.0.0",
                    select=False,
                )
            except Exception as exc:
                assert getattr(exc, "code", None) == "voice_pack_install_conflict"
            else:
                raise AssertionError("different content must not be idempotent")
            assert await registry.list_packs() == before
            assert cache_file.read_bytes() == cache_bytes
            assert conflict.is_dir()

            registry_bytes = (root / "voice-pack-registry.json").read_bytes()
            manager.disable("voice_pack_distribution")
            manager.uninstall("voice_pack_distribution")
            assert cache_file.read_bytes() == cache_bytes
            assert (root / "voice-pack-registry.json").read_bytes() == registry_bytes
            assert conflict.is_dir()

            install_and_enable(
                manager,
                distribution_source,
                "voice_pack_distribution",
            )
            reloaded = load_app(manager, root, downloader)
            status = await reloaded.state.voice_pack_distribution_service.status(
                "fake-kei@1.0.0"
            )
            assert status["installed"] is True
            assert downloader.calls == 1

    asyncio.run(scenario())


def test_explicit_install_rejects_malicious_redirect_before_body() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpd-redirect-") as temp:
        root = Path(temp)
        pack = write_fake_pack(root / "fixtures")
        archive = release_zip(
            pack,
            root / "trusted.zip",
            root_name="fake-kei-voice-pack",
        )
        manager, _ = prepare_packages(root, archive)
        placeholder = FakeDownloader(archive.read_bytes())
        app = load_app(manager, root, placeholder)
        service = app.state.voice_pack_distribution_service
        backend_prefix = service.__class__.__module__.rsplit(".", 1)[0]
        downloader_module = importlib.import_module(f"{backend_prefix}.downloader")
        body_calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "releases.example.test":
                return httpx.Response(
                    302,
                    headers={"location": "https://evil.example.test/payload.zip"},
                )
            body_calls.append(request.url.host)
            return httpx.Response(200, content=archive.read_bytes())

        service.downloader = downloader_module.HTTPSDownloader(
            client=httpx.Client(
                transport=httpx.MockTransport(handler),
                follow_redirects=False,
            )
        )
        try:
            asyncio.run(
                service.download_only(
                    "fake-kei@1.0.0",
                    confirmation="fake-kei@1.0.0",
                )
            )
        except Exception as exc:
            assert getattr(exc, "code", None) == "voice_pack_source_untrusted"
        else:
            raise AssertionError("cross-host redirect must be rejected")
        assert body_calls == []
        assert not (root / "download-cache").exists() or not list(
            (root / "download-cache").glob("*.zip")
        )


def test_fixed_https_downloader_rejects_size_and_digest() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpd-integrity-") as temp:
        root = Path(temp)
        package = build_voice_pack_distribution_package(root / "module")
        import_name = "_test_voice_pack_distribution_integrity"
        spec = importlib.util.spec_from_file_location(
            import_name,
            package / "backend" / "__init__.py",
            submodule_search_locations=[str(package / "backend")],
        )
        assert spec is not None and spec.loader is not None
        backend = importlib.util.module_from_spec(spec)
        sys.modules[import_name] = backend
        spec.loader.exec_module(backend)
        catalog_module = importlib.import_module(f"{import_name}.catalog")
        downloader_module = importlib.import_module(f"{import_name}.downloader")
        payload = b"fixed-fake-package"
        (root / "placeholder.zip").write_bytes(payload)
        entry_payload = {
            **catalog_payload(root / "placeholder.zip"),
            "size_bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }
        entry = catalog_module.VoicePackCatalog.from_payloads([entry_payload]).get(
            "fake-kei@1.0.0"
        )

        def wrong_size(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-length": str(len(payload) + 1)},
                content=payload,
            )

        destination = root / "wrong-size.zip"
        downloader = downloader_module.HTTPSDownloader(
            client=httpx.Client(transport=httpx.MockTransport(wrong_size))
        )
        try:
            downloader.download(entry, destination)
        except Exception as exc:
            assert getattr(exc, "code", None) == "voice_pack_size_mismatch"
        else:
            raise AssertionError("catalog size mismatch must fail")
        assert not destination.exists()

        tampered = bytearray(payload)
        tampered[-1] ^= 1

        def wrong_digest(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=bytes(tampered))

        destination = root / "wrong-digest.zip"
        downloader = downloader_module.HTTPSDownloader(
            client=httpx.Client(transport=httpx.MockTransport(wrong_digest))
        )
        try:
            downloader.download(entry, destination)
        except Exception as exc:
            assert getattr(exc, "code", None) == "voice_pack_integrity_mismatch"
        else:
            raise AssertionError("catalog digest mismatch must fail")
        assert not destination.exists()
        for name in list(sys.modules):
            if name == import_name or name.startswith(import_name + "."):
                sys.modules.pop(name, None)


def test_missing_registry_dependency_exposes_stable_core_hint() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpd-missing-") as temp:
        root = Path(temp)
        package = build_voice_pack_distribution_package(root / "package")
        manager = make_manager(root)
        digest = manager.calculate_package_sha256(package)
        manager.install(
            package,
            digest,
            expected_module_id="voice_pack_distribution",
        )
        try:
            manager.enable("voice_pack_distribution")
        except ModuleConflictError as exc:
            assert "voice_pack_registry" in str(exc)
        else:
            raise AssertionError("Core must name the missing registry dependency")


def test_outer_archive_rejects_symlink_before_registry_write() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-vpd-link-") as temp:
        root = Path(temp)
        pack = write_fake_pack(root / "fixtures")
        archive = release_zip(
            pack,
            root / "malicious.zip",
            root_name="fake-kei-voice-pack",
        )
        with zipfile.ZipFile(archive, "a") as package:
            info = zipfile.ZipInfo("fake-kei-voice-pack/models/link.ckpt")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            package.writestr(info, "outside")
        manager, _ = prepare_packages(root, archive)
        downloader = FakeDownloader(archive.read_bytes())
        app = load_app(manager, root, downloader)
        service = app.state.voice_pack_distribution_service
        registry_path = root / "voice-pack-registry.json"
        before = registry_path.read_bytes() if registry_path.exists() else None
        try:
            asyncio.run(
                service.download_only(
                    "fake-kei@1.0.0",
                    confirmation="fake-kei@1.0.0",
                )
            )
        except Exception as exc:
            assert getattr(exc, "code", None) == "voice_pack_archive_unsafe"
        else:
            raise AssertionError("ZIP symlink must be rejected")
        after = registry_path.read_bytes() if registry_path.exists() else None
        assert after == before


def main() -> int:
    test_package_source_exact_allowlist_and_unknown_file_fails_closed()
    test_deterministic_asset_free_package_and_release_metadata()
    test_module_install_idempotency_conflict_and_uninstall_retains_data()
    test_explicit_install_rejects_malicious_redirect_before_body()
    test_fixed_https_downloader_rejects_size_and_digest()
    test_missing_registry_dependency_exposes_stable_core_hint()
    test_outer_archive_rejects_symlink_before_registry_write()
    print("voice_pack_distribution installable module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
