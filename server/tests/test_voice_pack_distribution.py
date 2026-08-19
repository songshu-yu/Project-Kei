"""PK-213 tests: fake HTTPS, tiny assets, temporary Registry and no real services."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import tempfile
import unittest
import zipfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from features.voice.voice_packs.catalog import CatalogError, VoicePackCatalog
from features.voice.voice_packs.distribution.archive import audit_archive
from features.voice.voice_packs.distribution import builder as builder_module
from features.voice.voice_packs.distribution.builder import build_release
from features.voice.voice_packs.distribution.downloader import HTTPSDownloader
from features.voice.voice_packs.distribution.errors import DistributionError
from features.voice.voice_packs.distribution.service import VoicePackDistributionService
from features.voice.voice_packs.registry import VoicePackRegistry
from features.voice.voice_packs.service import VoicePackRegistryService


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_source(root: Path, *, pack_id: str = "fake-kei", version: str = "1.0.0") -> Path:
    root.mkdir(parents=True)
    assets = {
        "models/fake-gpt.ckpt": b"fake-gpt",
        "models/fake-sovits.pth": b"fake-sovits",
        "references/fake-reference.wav": b"RIFF-fake-wave",
    }
    for relative, content in assets.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        "schema_version": 1,
        "id": pack_id,
        "name": "Tiny Fake Voice",
        "version": version,
        "engine": {
            "provider": "gpt-sovits",
            "protocol_version": "pk210-tts-v1",
        },
        "supported_languages": ["zh", "ja"],
        "gpt_checkpoint": {
            "path": "models/fake-gpt.ckpt",
            "integrity": {
                "mode": "sha256",
                "size_bytes": len(assets["models/fake-gpt.ckpt"]),
                "sha256": _digest(assets["models/fake-gpt.ckpt"]),
            },
        },
        "sovits_checkpoint": {
            "path": "models/fake-sovits.pth",
            "integrity": {
                "mode": "sha256",
                "size_bytes": len(assets["models/fake-sovits.pth"]),
                "sha256": _digest(assets["models/fake-sovits.pth"]),
            },
        },
        "reference_audio": {
            "path": "references/fake-reference.wav",
            "integrity": {
                "mode": "sha256",
                "size_bytes": len(assets["references/fake-reference.wav"]),
                "sha256": _digest(assets["references/fake-reference.wav"]),
            },
        },
        "reference_text": "这是完全虚构的测试音频。",
        "reference_language": "zh",
        "default_text_language": "zh",
        "generation_parameters": {
            "top_k": 15,
            "top_p": 1.0,
            "temperature": 1.0,
            "speed_factor": 1.0,
            "text_split_method": "cut5",
        },
        "metadata": {
            "source": "synthetic test fixture",
            "author": "Project Kei tests",
            "license": "synthetic only",
            "redistribution": "allowed",
        },
    }
    (root / "voice-pack.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "README.md").write_text("Synthetic package.\n", encoding="utf-8")
    (root / "LICENSE.txt").write_text("Synthetic license.\n", encoding="utf-8")
    (root / "NOTICE.txt").write_text("Synthetic notice.\n", encoding="utf-8")
    return root


def _catalog_payload(zip_path: Path, *, pack_id: str = "fake-kei", version: str = "1.0.0"):
    raw = zip_path.read_bytes()
    return {
        "catalog_schema_version": 1,
        "pack_id": pack_id,
        "version": version,
        "display_name": "Tiny Fake Voice",
        "engine_id": "gpt-sovits-v2pro-nvidia50",
        "language": "zh",
        "core_compatibility": ">=0.1,<1",
        "voice_pack_schema_version": 1,
        "engine_protocol": "pk210-tts-v1",
        "engine_compatibility": "20250606v2pro",
        "download_url": f"https://releases.example.test/{zip_path.name}",
        "allowed_redirect_hosts": ["releases.example.test", "objects.example.test"],
        "size_bytes": len(raw),
        "sha256": _digest(raw),
        "archive_root": f"{pack_id}-voice-pack",
        "max_files": 32,
        "max_file_bytes": 1024 * 1024,
        "max_uncompressed_bytes": 4 * 1024 * 1024,
        "max_compression_ratio": 100,
        "license_url": "https://project.example.test/license",
        "notice_url": "https://project.example.test/notice",
        "release_tag": f"voice-{pack_id}-v{version}",
        "revision": "a" * 40,
        "published_at": "2030-01-01T00:00:00Z",
        "recommend_select": True,
    }


def _replace_gpt_asset(source: Path, content: bytes) -> None:
    asset = source / "models" / "fake-gpt.ckpt"
    asset.write_bytes(content)
    manifest_path = source / "voice-pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["gpt_checkpoint"]["integrity"].update(
        size_bytes=len(content),
        sha256=_digest(content),
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class VoicePackDistributionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pk213-")
        self.root = Path(self.temp.name)
        self.source = _make_source(self.root / "source")
        self.release = self.root / "fake-kei-voice-pack-1.0.0.zip"
        self.build = build_release(
            self.source,
            self.release,
            version="1.0.0",
            confirmation="fake-kei@1.0.0",
        )
        self.payload = _catalog_payload(self.release)

    def tearDown(self):
        self.temp.cleanup()

    def _registry_service(self):
        return VoicePackRegistryService(
            VoicePackRegistry(self.root / "state" / "registry.json"),
            runtime_root=self.root / "runtime",
        )

    def _distribution(self, handler, *, engine_ready=False):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        downloader = HTTPSDownloader(client=client)
        service = VoicePackDistributionService(
            catalog=VoicePackCatalog.from_payloads([self.payload]),
            registry_service=self._registry_service(),
            cache_root=self.root / "cache",
            downloader=downloader,
            engine_status=lambda: {
                "engine_id": "gpt-sovits-v2pro-nvidia50",
                "configured": engine_ready,
                "entrypoints_ready": engine_ready,
                "status": "installed_verified" if engine_ready else "unregistered",
            },
        )
        return service, client

    def test_fake_https_install_reuses_pk212_and_is_idempotent(self):
        requests = []
        package = self.release.read_bytes()

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(
                200, headers={"content-length": str(len(package))}, content=package
            )

        service, client = self._distribution(handler)
        try:
            first = asyncio.run(
                service.install(
                    "fake-kei@1.0.0",
                    confirmation="fake-kei@1.0.0",
                )
            )
            self.assertEqual(first["status"], "installed")
            self.assertEqual(first["selection_error"], "voice_pack_engine_unavailable")
            self.assertFalse(first["selected"])
            self.assertEqual(len(requests), 1)
            second = asyncio.run(
                service.install(
                    "fake-kei@1.0.0",
                    confirmation="fake-kei@1.0.0",
                )
            )
            self.assertEqual(second["status"], "already_installed")
            self.assertEqual(len(requests), 1)
            verified = asyncio.run(service.verify("fake-kei@1.0.0"))
            self.assertEqual(verified["status"], "verified")
            self.assertTrue(verified["catalog_cache_verified"])
        finally:
            client.close()

    def test_same_key_different_content_is_conflict_without_state_change(self):
        requests = []
        package = self.release.read_bytes()

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(200, content=package)

        service, client = self._distribution(handler)
        try:
            downloaded = asyncio.run(
                service.download_only(
                    "fake-kei@1.0.0", confirmation="fake-kei@1.0.0"
                )
            )
            self.assertEqual(downloaded["status"], "downloaded")
            conflicting = _make_source(self.root / "conflicting")
            _replace_gpt_asset(conflicting, b"different-fake-gpt")
            imported = asyncio.run(
                service.import_local(
                    conflicting, expected_key="fake-kei@1.0.0"
                )
            )
            self.assertEqual(imported["release_status"], "local_unpublished")
            asyncio.run(service.registry_service.enable("fake-kei", "1.0.0"))
            asyncio.run(service.registry_service.select("fake-kei", "1.0.0"))
            before_status = asyncio.run(service.registry_service.list_packs())
            registry_path = self.root / "state" / "registry.json"
            before_registry = registry_path.read_bytes()
            before_cache = {
                path.name: _digest(path.read_bytes())
                for path in (self.root / "cache").iterdir()
            }
            before_runtime = sorted(
                path.relative_to(self.root / "runtime").as_posix()
                for path in (self.root / "runtime").rglob("*")
            ) if (self.root / "runtime").exists() else []

            with self.assertRaises(DistributionError) as raised:
                asyncio.run(
                    service.install(
                        "fake-kei@1.0.0",
                        confirmation="fake-kei@1.0.0",
                    )
                )
            self.assertEqual(raised.exception.code, "voice_pack_install_conflict")
            self.assertEqual(registry_path.read_bytes(), before_registry)
            self.assertEqual(
                asyncio.run(service.registry_service.list_packs()), before_status
            )
            self.assertEqual(
                {
                    path.name: _digest(path.read_bytes())
                    for path in (self.root / "cache").iterdir()
                },
                before_cache,
            )
            after_runtime = sorted(
                path.relative_to(self.root / "runtime").as_posix()
                for path in (self.root / "runtime").rglob("*")
            ) if (self.root / "runtime").exists() else []
            self.assertEqual(after_runtime, before_runtime)
            self.assertEqual(len(requests), 1)
        finally:
            client.close()

    def test_download_only_has_no_registry_side_effect(self):
        package = self.release.read_bytes()
        service, client = self._distribution(
            lambda request: httpx.Response(200, content=package)
        )
        try:
            result = asyncio.run(
                service.download_only(
                    "fake-kei@1.0.0", confirmation="fake-kei@1.0.0"
                )
            )
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(
                asyncio.run(self._registry_service().list_packs())["packs"], []
            )
        finally:
            client.close()

    def test_untrusted_redirect_is_rejected_before_second_request(self):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://evil.test/pack.zip"})

        service, client = self._distribution(handler)
        try:
            with self.assertRaisesRegex(DistributionError, "trusted"):
                asyncio.run(
                    service.download_only(
                        "fake-kei@1.0.0", confirmation="fake-kei@1.0.0"
                    )
                )
            self.assertEqual(len(requests), 1)
            self.assertFalse((self.root / "cache").exists() and any((self.root / "cache").glob("*.zip")))
        finally:
            client.close()

    def test_allowed_redirect_and_timeout_have_bounded_network_effects(self):
        package = self.release.read_bytes()
        requests = []

        def redirect_handler(request):
            requests.append(request.url.host)
            if request.url.host == "releases.example.test":
                return httpx.Response(
                    302,
                    headers={"location": "https://objects.example.test/fixed.zip"},
                )
            return httpx.Response(200, content=package)

        service, client = self._distribution(redirect_handler)
        try:
            result = asyncio.run(
                service.download_only(
                    "fake-kei@1.0.0", confirmation="fake-kei@1.0.0"
                )
            )
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(
                requests, ["releases.example.test", "objects.example.test"]
            )
        finally:
            client.close()

        timeout_root = self.root / "timeout-cache"
        timeout_client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    httpx.ReadTimeout("synthetic timeout", request=request)
                )
            )
        )
        timeout_service = VoicePackDistributionService(
            catalog=VoicePackCatalog.from_payloads([self.payload]),
            registry_service=self._registry_service(),
            cache_root=timeout_root,
            downloader=HTTPSDownloader(client=timeout_client),
        )
        try:
            with self.assertRaises(DistributionError) as raised:
                asyncio.run(
                    timeout_service.download_only(
                        "fake-kei@1.0.0", confirmation="fake-kei@1.0.0"
                    )
                )
            self.assertEqual(raised.exception.code, "voice_pack_download_timeout")
            self.assertEqual(list(timeout_root.glob("*")), [])
        finally:
            timeout_client.close()

    def test_wrong_digest_and_confirmation_leave_no_cache(self):
        package = self.release.read_bytes()
        bad_payload = deepcopy(self.payload)
        bad_payload["sha256"] = "0" * 64
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=package)
            )
        )
        service = VoicePackDistributionService(
            catalog=VoicePackCatalog.from_payloads([bad_payload]),
            registry_service=self._registry_service(),
            cache_root=self.root / "bad-cache",
            downloader=HTTPSDownloader(client=client),
        )
        try:
            with self.assertRaisesRegex(DistributionError, "confirmation"):
                asyncio.run(
                    service.download_only("fake-kei@1.0.0", confirmation="wrong")
                )
            with self.assertRaisesRegex(DistributionError, "integrity"):
                asyncio.run(
                    service.download_only(
                        "fake-kei@1.0.0", confirmation="fake-kei@1.0.0"
                    )
                )
            self.assertEqual(list((self.root / "bad-cache").glob("*")), [])
        finally:
            client.close()

    def test_archive_rejects_traversal_executable_and_bomb(self):
        entry = VoicePackCatalog.from_payloads([self.payload]).get("fake-kei@1.0.0")
        for name, writer in {
            "traversal": lambda z: z.writestr("../escape.txt", b"x"),
            "executable": lambda z: z.writestr("fake-kei-voice-pack/run.ps1", b"x"),
            "extra": lambda z: z.writestr("fake-kei-voice-pack/secret.bin", b"x"),
            "bomb": lambda z: z.writestr("fake-kei-voice-pack/models/bomb.ckpt", b"0" * 200000),
        }.items():
            path = self.root / f"{name}.zip"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                writer(archive)
            with self.subTest(name=name), self.assertRaises(DistributionError):
                audit_archive(path, entry)

    def test_catalog_is_strict_and_has_no_builtin_production_entry(self):
        for field, value in {
            "unexpected": True,
            "headers": {"authorization": "forbidden"},
            "proxy": "https://proxy.example.test",
            "download_command": "forbidden",
        }.items():
            unknown = deepcopy(self.payload)
            unknown[field] = value
            with self.subTest(field=field), self.assertRaises(CatalogError):
                VoicePackCatalog.from_payloads([unknown])
        mutable = deepcopy(self.payload)
        mutable["release_tag"] = "latest"
        with self.assertRaises(CatalogError):
            VoicePackCatalog.from_payloads([mutable])
        builtin = VoicePackCatalog.load(
            Path(__file__).resolve().parents[1]
            / "features"
            / "voice"
            / "voice_packs"
            / "catalog"
        )
        self.assertEqual(builtin.list(), [])

    def test_builder_is_deterministic_and_rejects_secrets(self):
        second = self.root / "second.zip"
        second_result = build_release(
            self.source,
            second,
            version="1.0.0",
            confirmation="fake-kei@1.0.0",
        )
        self.assertEqual(self.build["sha256"], second_result["sha256"])
        self.assertTrue(Path(str(second) + ".sha256").is_file())
        self.assertTrue((self.root / "second.release.json").is_file())
        with self.assertRaises(DistributionError):
            build_release(
                self.source,
                second,
                version="1.0.0",
                confirmation="fake-kei@1.0.0",
            )

        secret_source = _make_source(self.root / "secret", pack_id="secret-fake")
        (secret_source / "README.md").write_text(
            "API_KEY=not-a-real-but-forbidden-value", encoding="utf-8"
        )
        rejected = self.root / "rejected.zip"
        with self.assertRaises(DistributionError):
            build_release(
                secret_source,
                rejected,
                version="1.0.0",
                confirmation="secret-fake@1.0.0",
            )
        self.assertFalse(rejected.exists())

    def test_builder_rejects_source_external_hardlink_before_content_io(self):
        source = _make_source(self.root / "hardlink-source", pack_id="hardlink-fake")
        content = b"external-hardlinked-checkpoint"
        _replace_gpt_asset(source, content)
        asset = source / "models" / "fake-gpt.ckpt"
        external = self.root / "external-checkpoint.ckpt"
        external.write_bytes(content)
        asset.unlink()
        os.link(external, asset)
        output = self.root / "hardlink.zip"
        with patch.object(
            builder_module,
            "load_manifest",
            side_effect=AssertionError("manifest content read tripwire"),
        ) as manifest_read, patch.object(
            builder_module,
            "_hash_file",
            side_effect=AssertionError("asset content read tripwire"),
        ) as asset_read:
            with self.assertRaises(DistributionError) as raised:
                build_release(
                    source,
                    output,
                    version="1.0.0",
                    confirmation="hardlink-fake@1.0.0",
                )
        self.assertEqual(raised.exception.code, "voice_pack_build_rejected")
        manifest_read.assert_not_called()
        asset_read.assert_not_called()
        self.assertFalse(output.exists())

    def test_builder_rejects_symlink_and_reparse_points(self):
        source = _make_source(self.root / "link-source", pack_id="link-fake")
        target = source / "models" / "fake-gpt.ckpt"
        real_lstat = os.lstat
        used_fake_symlink = False
        try:
            target.unlink()
            os.symlink(self.root / "outside.ckpt", target)
        except OSError:
            used_fake_symlink = True
            target.write_bytes(b"fake-gpt")

        def symlink_lstat(path):
            metadata = real_lstat(path)
            if used_fake_symlink and Path(path) == target:
                return SimpleNamespace(
                    st_mode=stat.S_IFLNK | 0o777,
                    st_nlink=1,
                    st_file_attributes=0,
                )
            return metadata

        with self.assertRaises(DistributionError):
            build_release(
                source,
                self.root / "link.zip",
                version="1.0.0",
                confirmation="link-fake@1.0.0",
                _lstat=symlink_lstat,
            )

        reparse_source = _make_source(
            self.root / "reparse-source", pack_id="reparse-fake"
        )
        reparse_directory = reparse_source / "models"

        def reparse_lstat(path):
            metadata = real_lstat(path)
            if Path(path) == reparse_directory:
                return SimpleNamespace(
                    st_mode=metadata.st_mode,
                    st_nlink=metadata.st_nlink,
                    st_file_attributes=0x400,
                )
            return metadata

        with self.assertRaises(DistributionError):
            build_release(
                reparse_source,
                self.root / "reparse.zip",
                version="1.0.0",
                confirmation="reparse-fake@1.0.0",
                _lstat=reparse_lstat,
            )

    def test_builder_rejects_output_inside_source_and_reparse_parent(self):
        inside = self.source / "release.zip"
        with self.assertRaises(DistributionError) as raised:
            build_release(
                self.source,
                inside,
                version="1.0.0",
                confirmation="fake-kei@1.0.0",
            )
        self.assertEqual(raised.exception.code, "voice_pack_build_rejected")
        self.assertFalse(inside.exists())

        output_parent = self.root / "fake-reparse-output"
        output_parent.mkdir()
        real_lstat = os.lstat

        def reparse_parent_lstat(path):
            metadata = real_lstat(path)
            if Path(path) == output_parent:
                return SimpleNamespace(
                    st_mode=metadata.st_mode,
                    st_nlink=metadata.st_nlink,
                    st_file_attributes=0x400,
                )
            return metadata

        with self.assertRaises(DistributionError):
            build_release(
                self.source,
                output_parent / "release.zip",
                version="1.0.0",
                confirmation="fake-kei@1.0.0",
                _lstat=reparse_parent_lstat,
            )

    def test_local_directory_preserves_source_and_marks_unpublished(self):
        service = VoicePackDistributionService(
            catalog=VoicePackCatalog.from_payloads([]),
            registry_service=self._registry_service(),
            cache_root=self.root / "cache",
        )
        result = asyncio.run(
            service.import_local(
                self.source, expected_key="fake-kei@1.0.0"
            )
        )
        self.assertEqual(result["release_status"], "local_unpublished")
        self.assertTrue(result["source_preserved"])
        self.assertTrue(self.source.is_dir())


if __name__ == "__main__":
    unittest.main()
