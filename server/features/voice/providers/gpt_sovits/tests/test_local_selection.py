"""PK-211 local directory picker tests using fake pickers and temporary trees."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

SERVER_ROOT = Path(__file__).resolve().parents[5]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from features.voice.providers.gpt_sovits.acquisition import AcquisitionError, LocalEngineRegistry
from features.voice.providers.gpt_sovits.descriptor import EngineDescriptor, load_descriptor
from features.voice.providers.gpt_sovits.local_selection import (
    EngineSelectionError,
    LocalEngineSelectionService,
    validate_selected_existing_install,
)
from features.voice.providers.gpt_sovits.selection_router import create_gpt_sovits_engine_router


def _engine_tree(root: Path) -> Path:
    engine = root / "Existing GPT SoVITS"
    (engine / "runtime").mkdir(parents=True)
    (engine / "api.py").write_text("raise RuntimeError('must never run')\n", encoding="utf-8")
    (engine / "runtime" / "python.exe").write_bytes(b"fake-runtime")
    (engine / "install.ps1").write_text("throw 'must never run'\n", encoding="utf-8")
    (engine / "model.ckpt").write_bytes(b"fake-user-owned-weight")
    return engine


def _marker(descriptor: EngineDescriptor) -> dict[str, object]:
    return {
        "schema_version": 1,
        "engine_id": descriptor.engine_id,
        "release_identity": descriptor.release_identity,
        "distribution_revision": descriptor.distribution_revision,
        "integrity": {
            "algorithm": descriptor.integrity_algorithm,
            "digest": descriptor.integrity_digest,
        },
        "scripts_executed": False,
    }


def test_cancel_is_zero_write_and_existing_install_is_explicitly_unverified() -> None:
    descriptor = load_descriptor()
    with tempfile.TemporaryDirectory(prefix="kei-pk211-picker-") as temp:
        root = Path(temp)
        registry_path = root / "state" / "engine.json"
        cancelled = LocalEngineSelectionService(
            descriptor=descriptor,
            registry=LocalEngineRegistry(registry_path),
            picker=lambda: None,
        )
        result = cancelled.select_existing_install()
        assert result["action"] == "cancelled"
        assert result["registration_state"] == "unregistered"
        assert result["selection_in_progress"] is False
        assert not registry_path.exists()

        engine = _engine_tree(root)
        service = LocalEngineSelectionService(
            descriptor=descriptor,
            registry=LocalEngineRegistry(registry_path),
            picker=lambda: engine,
        )
        registered = service.select_existing_install()
        assert registered == {
            "action": "registered",
            "engine_id": descriptor.engine_id,
            "registration_state": "registered_existing",
            "integrity_status": "unverified_existing_install",
            "entrypoints_ready": True,
            "display_name": engine.name,
            "selection_in_progress": False,
            "can_select_existing": True,
        }
        assert (engine / "install.ps1").read_text(encoding="utf-8") == "throw 'must never run'\n"
        assert (engine / "model.ckpt").read_bytes() == b"fake-user-owned-weight"
        public = json.dumps(service.status(), ensure_ascii=False)
        assert str(engine) not in public
        assert str(root) not in public


def test_fixed_marker_is_verified_but_tampered_marker_and_malicious_layout_are_rejected() -> None:
    descriptor = load_descriptor()
    with tempfile.TemporaryDirectory(prefix="kei-pk211-structure-") as temp:
        root = Path(temp)
        verified = _engine_tree(root / "verified")
        (verified / descriptor.marker_file).write_text(
            json.dumps(_marker(descriptor)),
            encoding="utf-8",
        )
        result = validate_selected_existing_install(verified, descriptor)
        assert result.install_status == "installed_verified"
        assert result.integrity_status == "sha256_verified"

        tampered = _engine_tree(root / "tampered")
        marker = _marker(descriptor)
        marker["distribution_revision"] = "0" * 40
        (tampered / descriptor.marker_file).write_text(json.dumps(marker), encoding="utf-8")
        try:
            validate_selected_existing_install(tampered, descriptor)
        except EngineSelectionError as exc:
            assert exc.code == "install_marker_invalid"
        else:
            raise AssertionError("tampered fixed marker must be rejected")

        malicious = root / "malicious"
        (malicious / "api.py").mkdir(parents=True)
        (malicious / "runtime").mkdir()
        (malicious / "runtime" / "python.exe").write_bytes(b"fake")
        try:
            validate_selected_existing_install(malicious, descriptor)
        except EngineSelectionError as exc:
            assert exc.code in {"install_layout_invalid", "install_not_ready"}
        else:
            raise AssertionError("directory masquerading as api.py must be rejected")


def test_reparse_point_is_rejected_without_following_it() -> None:
    descriptor = load_descriptor()
    with tempfile.TemporaryDirectory(prefix="kei-pk211-reparse-") as temp:
        engine = _engine_tree(Path(temp))
        suspect = engine / "runtime"
        original = __import__(
            "features.voice.providers.gpt_sovits.local_selection",
            fromlist=["_is_reparse_point"],
        )._is_reparse_point

        def fake_reparse(path: Path) -> bool:
            return path == suspect or original(path)

        with patch(
            "features.voice.providers.gpt_sovits.local_selection._is_reparse_point",
            side_effect=fake_reparse,
        ):
            try:
                validate_selected_existing_install(engine, descriptor)
            except EngineSelectionError as exc:
                assert exc.code == "install_reparse_point"
            else:
                raise AssertionError("reparse point must be rejected")


def test_concurrent_selection_is_rejected_before_a_second_picker_opens() -> None:
    descriptor = load_descriptor()
    with tempfile.TemporaryDirectory(prefix="kei-pk211-concurrent-") as temp:
        root = Path(temp)
        engine = _engine_tree(root)
        started = threading.Event()
        release = threading.Event()
        picker_calls = []

        def blocking_picker() -> Path:
            picker_calls.append(True)
            started.set()
            assert release.wait(timeout=5)
            return engine

        service = LocalEngineSelectionService(
            descriptor=descriptor,
            registry=LocalEngineRegistry(root / "state" / "engine.json"),
            picker=blocking_picker,
        )
        first_result = []
        worker = threading.Thread(target=lambda: first_result.append(service.select_existing_install()))
        worker.start()
        assert started.wait(timeout=5)
        try:
            service.select_existing_install()
        except EngineSelectionError as exc:
            assert exc.code == "selection_in_progress"
        else:
            raise AssertionError("concurrent picker must be rejected")
        release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert len(picker_calls) == 1
        assert first_result[0]["action"] == "registered"


def test_save_failure_preserves_previous_registration() -> None:
    descriptor = load_descriptor()
    with tempfile.TemporaryDirectory(prefix="kei-pk211-save-") as temp:
        root = Path(temp)
        previous = _engine_tree(root / "previous")
        candidate = _engine_tree(root / "candidate")
        registry_path = root / "state" / "engine.json"
        LocalEngineRegistry(registry_path).register(
            descriptor,
            previous,
            api_style="auto",
            install_status="registered_existing",
            integrity_status="unverified_existing_install",
        )
        before = registry_path.read_bytes()

        class FailingRegistry(LocalEngineRegistry):
            def save(self, data):
                raise AcquisitionError("local_config_write_failed", "本机引擎配置写入失败")

        service = LocalEngineSelectionService(
            descriptor=descriptor,
            registry=FailingRegistry(registry_path),
            picker=lambda: candidate,
        )
        try:
            service.select_existing_install()
        except EngineSelectionError as exc:
            assert exc.code == "local_config_write_failed"
        else:
            raise AssertionError("save failure must be visible")
        assert registry_path.read_bytes() == before
        assert (previous / "model.ckpt").is_file()
        assert (candidate / "model.ckpt").is_file()


def test_http_api_accepts_only_empty_same_origin_post_and_never_accepts_a_path() -> None:
    descriptor = load_descriptor()
    with tempfile.TemporaryDirectory(prefix="kei-pk211-api-") as temp:
        root = Path(temp)
        engine = _engine_tree(root)
        picker_calls = []

        def picker() -> Path:
            picker_calls.append(True)
            return engine

        service = LocalEngineSelectionService(
            descriptor=descriptor,
            registry=LocalEngineRegistry(root / "state" / "engine.json"),
            picker=picker,
        )
        app = FastAPI()
        app.include_router(create_gpt_sovits_engine_router(service))

        async def scenario() -> None:
            transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 4567))
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                no_origin = await client.post("/api/v1/gpt-sovits-engine/select-existing")
                assert no_origin.status_code == 403
                evil_origin = await client.post(
                    "/api/v1/gpt-sovits-engine/select-existing",
                    headers={"origin": "https://evil.invalid"},
                )
                assert evil_origin.status_code == 403
                path_payload = await client.post(
                    "/api/v1/gpt-sovits-engine/select-existing",
                    headers={"origin": "http://127.0.0.1:8000"},
                    json={"path": str(engine), "command": "anything", "url": "https://invalid"},
                )
                assert path_payload.status_code == 422
                query_payload = await client.post(
                    "/api/v1/gpt-sovits-engine/select-existing?path=forbidden",
                    headers={"origin": "http://127.0.0.1:8000"},
                )
                assert query_payload.status_code == 422
                assert picker_calls == []

                selected = await client.post(
                    "/api/v1/gpt-sovits-engine/select-existing",
                    headers={"origin": "http://127.0.0.1:8000"},
                )
                assert selected.status_code == 200
                assert selected.json()["integrity_status"] == "unverified_existing_install"
                assert str(engine) not in selected.text
                status = await client.get("/api/v1/gpt-sovits-engine/status")
                assert status.status_code == 200
                assert status.json()["display_name"] == engine.name
                assert str(root) not in status.text

            remote = httpx.ASGITransport(app=app, client=("192.0.2.5", 4567))
            async with httpx.AsyncClient(transport=remote, base_url="http://test") as client:
                response = await client.get("/api/v1/gpt-sovits-engine/status")
                assert response.status_code == 403

        asyncio.run(scenario())
        assert picker_calls == [True]


def main() -> int:
    test_cancel_is_zero_write_and_existing_install_is_explicitly_unverified()
    test_fixed_marker_is_verified_but_tampered_marker_and_malicious_layout_are_rejected()
    test_reparse_point_is_rejected_without_following_it()
    test_concurrent_selection_is_rejected_before_a_second_picker_opens()
    test_save_failure_preserves_previous_registration()
    test_http_api_accepts_only_empty_same_origin_post_and_never_accepts_a_path()
    print("GPT-SoVITS local directory selection tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
