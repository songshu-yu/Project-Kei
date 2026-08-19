"""PK-212 tests use only tiny fake assets and temporary local state."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import _path_setup  # noqa: F401

from features.voice.models import VoicePackRef
from features.voice.voice_packs.errors import (
    VoicePackConflictError,
    VoicePackManifestError,
    VoicePackPackageError,
    VoicePackRegistryError,
    VoicePackSwitchError,
)
from features.voice.voice_packs.manifest import parse_manifest
from features.voice.voice_packs.registry import VoicePackRegistry
from features.voice.voice_packs.router import create_voice_pack_router
from features.voice.voice_packs.service import VoicePackRegistryService


def run(awaitable):
    return asyncio.run(awaitable)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_pack(root: Path, pack_id: str, version: str = "1.0.0") -> tuple[Path, dict]:
    package = root / f"{pack_id}-{version}"
    assets = package / "assets"
    assets.mkdir(parents=True)
    files = {
        "gpt_checkpoint": assets / f"{pack_id}.ckpt",
        "sovits_checkpoint": assets / f"{pack_id}.pth",
        "reference_audio": assets / f"{pack_id}.wav",
    }
    files["gpt_checkpoint"].write_bytes(b"fake-gpt-" + pack_id.encode())
    files["sovits_checkpoint"].write_bytes(b"fake-sovits-" + pack_id.encode())
    files["reference_audio"].write_bytes(b"RIFF-fake-" + pack_id.encode())
    manifest = {
        "schema_version": 1,
        "id": pack_id,
        "name": f"Fake {pack_id}",
        "version": version,
        "engine": {"provider": "gpt-sovits", "protocol_version": "pk210-tts-v1"},
        "supported_languages": ["zh", "ja"],
        "gpt_checkpoint": asset(files["gpt_checkpoint"], package),
        "sovits_checkpoint": asset(files["sovits_checkpoint"], package),
        "reference_audio": asset(files["reference_audio"], package),
        "reference_text": "fake prompt",
        "reference_language": "ja",
        "default_text_language": "zh",
        "generation_parameters": {"top_k": 7, "temperature": 0.8, "text_split_method": "cut5"},
        "metadata": {"license": "test-only", "redistribution": "restricted"},
    }
    (package / "voice-pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package, manifest


def asset(path: Path, root: Path) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        "integrity": {"mode": "sha256", "size_bytes": path.stat().st_size, "sha256": digest(path)},
    }


class FakeActivator:
    def __init__(self):
        self.calls: list[VoicePackRef] = []
        self.active: tuple[str, str] | None = None
        self.fail_for: str | None = None

    async def activate_voice_pack(self, voice_pack: VoicePackRef) -> None:
        self.calls.append(voice_pack)
        if voice_pack.pack_id == self.fail_for:
            raise RuntimeError("fake provider rejection")
        self.active = (voice_pack.pack_id, voice_pack.pack_version)


class FailNextRegistry(VoicePackRegistry):
    fail_next = False

    def save(self, payload):
        if self.fail_next:
            self.fail_next = False
            raise VoicePackRegistryError("fake atomic save failure")
        return super().save(payload)


def service_for(root: Path, activator=None, registry_class=VoicePackRegistry):
    registry = registry_class(root / "registry.json")
    return VoicePackRegistryService(registry, runtime_root=root / "runtime", activator=activator), registry


def expect(exc_type, awaitable):
    try:
        run(awaitable)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}")


def test_manifest_validation(root: Path) -> None:
    package, manifest = make_pack(root, "valid")
    parse_manifest(manifest)

    invalid = dict(manifest)
    invalid["schema_version"] = 99
    exc = None
    try:
        parse_manifest(invalid)
    except VoicePackManifestError as error:
        exc = error
    assert exc is not None and exc.code == "voice_pack_schema_unsupported"

    invalid = json.loads(json.dumps(manifest))
    invalid["engine"]["provider"] = "unknown-engine"
    try:
        parse_manifest(invalid)
    except VoicePackManifestError as error:
        assert error.code == "voice_pack_engine_unknown"
    else:
        raise AssertionError("unknown engine accepted")

    for bad in ("../escape.ckpt", "/absolute/model.ckpt", "C:/model.ckpt", "assets\\model.ckpt"):
        invalid = json.loads(json.dumps(manifest))
        invalid["gpt_checkpoint"]["path"] = bad
        try:
            parse_manifest(invalid)
        except VoicePackManifestError:
            pass
        else:
            raise AssertionError(f"unsafe path accepted: {bad}")

    invalid = json.loads(json.dumps(manifest))
    invalid["install_command"] = "powershell -File install.ps1"
    try:
        parse_manifest(invalid)
    except VoicePackManifestError:
        pass
    else:
        raise AssertionError("executable hook field accepted")
    assert package.exists()


def test_import_integrity_and_symlink(root: Path) -> None:
    service, _ = service_for(root / "valid-state")
    package, _ = make_pack(root, "importable")
    imported = run(service.import_pack(package))
    assert imported["id"] == "importable" and imported["enabled"] is False
    expect(VoicePackConflictError, service.import_pack(package))

    missing, _ = make_pack(root, "missing")
    (missing / "assets" / "missing.wav").unlink()
    missing_service, _ = service_for(root / "missing-state")
    expect(VoicePackPackageError, missing_service.import_pack(missing))

    corrupt, _ = make_pack(root, "corrupt")
    (corrupt / "assets" / "corrupt.ckpt").write_bytes(b"changed")
    corrupt_service, _ = service_for(root / "corrupt-state")
    expect(VoicePackPackageError, corrupt_service.import_pack(corrupt))

    linked, _ = make_pack(root, "linked")
    link_path = linked / "assets" / "linked.wav"
    link_service, _ = service_for(root / "link-state")
    original = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == link_path or original(path)

    with patch.object(Path, "is_symlink", fake_is_symlink):
        expect(VoicePackPackageError, link_service.import_pack(linked))

    executable, _ = make_pack(root, "executable")
    (executable / "install.ps1").write_text("Write-Host forbidden", encoding="utf-8")
    executable_service, _ = service_for(root / "executable-state")
    expect(VoicePackPackageError, executable_service.import_pack(executable))

    zipped, _ = make_pack(root, "zipped")
    archive = root / "zipped.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as handle:
        for path in zipped.rglob("*"):
            if path.is_file():
                handle.write(path, path.relative_to(zipped).as_posix())
    zip_service, _ = service_for(root / "zip-state")
    zip_result = run(zip_service.import_pack(archive))
    assert zip_result["id"] == "zipped" and archive.exists()


def test_content_comparison_is_read_only_and_path_free(root: Path) -> None:
    service, registry = service_for(root / "state")
    installed, _ = make_pack(root / "installed", "compare-pack")
    candidate, candidate_manifest = make_pack(root / "candidate", "compare-pack")
    run(service.import_pack(installed))
    before = registry.path.read_bytes()

    identical = run(
        service.compare_content("compare-pack", "1.0.0", candidate)
    )
    assert identical == {
        "id": "compare-pack",
        "version": "1.0.0",
        "equivalent": True,
    }
    assert str(root) not in json.dumps(identical)

    changed = candidate / "assets" / "compare-pack.ckpt"
    changed.write_bytes(b"different-fake-gpt")
    candidate_manifest["gpt_checkpoint"] = asset(changed, candidate)
    (candidate / "voice-pack.json").write_text(
        json.dumps(candidate_manifest), encoding="utf-8"
    )
    conflict = run(
        service.compare_content("compare-pack", "1.0.0", candidate)
    )
    assert conflict["equivalent"] is False
    assert registry.path.read_bytes() == before


def test_switch_rollback_and_provider_config(root: Path) -> None:
    activator = FakeActivator()
    service, _ = service_for(root / "switch-state", activator)
    first, _ = make_pack(root, "first")
    second, _ = make_pack(root, "second")
    run(service.import_pack(first))
    run(service.import_pack(second))
    run(service.enable("first", "1.0.0"))
    run(service.enable("second", "1.0.0"))
    run(service.select("first", "1.0.0"))
    received = activator.calls[-1]
    assert received.pack_id == "first"
    assert received.handle["gpt_checkpoint_path"].endswith("first.ckpt")
    assert received.handle["sovits_checkpoint_path"].endswith("first.pth")
    assert received.handle["ref_audio_path"].endswith("first.wav")
    assert received.handle["prompt_text"] == "fake prompt"
    assert received.handle["generation_parameters"]["top_k"] == 7

    activator.fail_for = "second"
    expect(VoicePackSwitchError, service.select("second", "1.0.0"))
    listing = run(service.list_packs())
    assert listing["active"] == "first@1.0.0"
    assert activator.active == ("first", "1.0.0")
    assert [call.pack_id for call in activator.calls[-2:]] == ["second", "first"]


def test_registry_atomicity_and_save_rollback(root: Path) -> None:
    registry = VoicePackRegistry(root / "atomic.json")
    initial = {"registry_version": 1, "active": None, "packs": {"old@1.0.0": {"marker": "old"}}}
    registry.save(initial)
    with patch("features.voice.voice_packs.registry.os.replace", side_effect=OSError("fake")):
        try:
            registry.save({"registry_version": 1, "active": None, "packs": {}})
        except VoicePackRegistryError:
            pass
        else:
            raise AssertionError("atomic replace failure accepted")
    assert registry.load() == initial
    assert not list(root.glob("atomic.json.*.tmp"))

    activator = FakeActivator()
    service, fail_registry = service_for(root / "save-state", activator, FailNextRegistry)
    first, _ = make_pack(root, "save-first")
    second, _ = make_pack(root, "save-second")
    run(service.import_pack(first)); run(service.import_pack(second))
    run(service.enable("save-first", "1.0.0")); run(service.enable("save-second", "1.0.0"))
    run(service.select("save-first", "1.0.0"))
    fail_registry.fail_next = True
    expect(VoicePackRegistryError, service.select("save-second", "1.0.0"))
    assert run(service.list_packs())["active"] == "save-first@1.0.0"
    assert activator.active == ("save-first", "1.0.0")


def test_unregister_preserves_source_and_api_redaction(root: Path) -> None:
    service, _ = service_for(root / "unregister-state")
    package, _ = make_pack(root, "preserve")
    run(service.import_pack(package))
    run(service.enable("preserve", "1.0.0"))
    result = run(service.unregister("preserve", "1.0.0"))
    assert result["source_assets_deleted"] is False
    assert package.exists() and (package / "assets" / "preserve.ckpt").exists()

    api_service, _ = service_for(root / "api-state")
    api_package, _ = make_pack(root, "api-pack")
    run(api_service.import_pack(api_package))
    app = FastAPI()
    app.include_router(create_voice_pack_router(lambda: api_service))
    with TestClient(app) as client:
        response = client.get("/api/v1/voice-packs")
        assert response.status_code == 200
        serialized = json.dumps(response.json(), ensure_ascii=False)
        assert str(root) not in serialized
        assert "asset_bindings" not in serialized and "package_root" not in serialized


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-voice-pack-test-") as temp:
        root = Path(temp)
        test_manifest_validation(root / "manifest")
        test_import_integrity_and_symlink(root / "imports")
        test_content_comparison_is_read_only_and_path_free(root / "compare")
        test_switch_rollback_and_provider_config(root / "switch")
        test_registry_atomicity_and_save_rollback(root / "atomic")
        test_unregister_preserves_source_and_api_redaction(root / "unregister")
    print("voice pack registry tests passed")


if __name__ == "__main__":
    main()
