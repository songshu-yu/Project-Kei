"""PK-212 browser-origin regression using only temporary fake Voice Packs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import _path_setup  # noqa: F401

from features.voice.voice_packs import VoicePackRegistry, VoicePackRegistryService, create_voice_pack_router
from features.voice.voice_packs.security import VoicePackOriginGuardMiddleware


PACK_ID = "origin-pack"
PACK_VERSION = "1.0.0"
EVIL_ORIGIN = "https://evil.example"
LOCAL_ORIGIN = "http://127.0.0.1:8000"


def _asset(path: Path, package_root: Path) -> dict:
    content = path.read_bytes()
    return {
        "path": path.relative_to(package_root).as_posix(),
        "integrity": {
            "mode": "sha256",
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    }


def _make_fake_pack(root: Path, pack_id: str) -> Path:
    package = root / pack_id
    assets = package / "assets"
    assets.mkdir(parents=True)
    gpt = assets / "fake.ckpt"
    sovits = assets / "fake.pth"
    audio = assets / "fake.wav"
    gpt.write_bytes(b"fake-gpt")
    sovits.write_bytes(b"fake-sovits")
    audio.write_bytes(b"RIFF-fake-audio")
    manifest = {
        "schema_version": 1,
        "id": pack_id,
        "name": "Origin Test Voice",
        "version": PACK_VERSION,
        "engine": {"provider": "gpt-sovits", "protocol_version": "pk210-tts-v1"},
        "supported_languages": ["zh", "ja"],
        "gpt_checkpoint": _asset(gpt, package),
        "sovits_checkpoint": _asset(sovits, package),
        "reference_audio": _asset(audio, package),
        "reference_text": "fake prompt",
        "reference_language": "ja",
        "default_text_language": "zh",
        "generation_parameters": {},
        "metadata": {"license": "test-only", "redistribution": "restricted"},
    }
    (package / "voice-pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package


def _build_app(service: VoicePackRegistryService) -> FastAPI:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    # Added after CORS so it is outermost and rejects unsafe preflight first.
    app.add_middleware(VoicePackOriginGuardMiddleware)
    app.include_router(create_voice_pack_router(lambda: service))
    return app


async def _request_client(app: FastAPI, client_host: str = "127.0.0.1"):
    transport = httpx.ASGITransport(app=app, client=(client_host, 53000))
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000")


async def check_origin_guard(root: Path) -> None:
    package = _make_fake_pack(root, PACK_ID)
    second_package = _make_fake_pack(root, "second-origin-pack")
    registry = VoicePackRegistry(root / "registry.json")
    service = VoicePackRegistryService(registry, runtime_root=root / "runtime")
    await service.import_pack(package)
    app = _build_app(service)

    evil_headers = {"Origin": EVIL_ORIGIN}
    write_cases = [
        ("POST", "/api/v1/voice-packs/import", {"json": {"package_path": str(second_package)}}),
        ("POST", f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/enable", {}),
        ("POST", f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/select", {}),
        ("POST", f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/disable", {}),
        ("DELETE", f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}", {}),
    ]
    async with await _request_client(app) as client:
        before = registry.path.read_bytes()
        for method, path, kwargs in write_cases:
            response = await client.request(method, path, headers=evil_headers, **kwargs)
            assert response.status_code == 403, (method, path, response.text)
            assert response.json()["detail"]["code"] in {
                "voice_pack_origin_forbidden", "voice_pack_write_forbidden"
            }
            assert registry.path.read_bytes() == before

        # Read-only queries remain available even with a foreign Origin.
        read = await client.get("/api/v1/voice-packs", headers=evil_headers)
        assert read.status_code == 200
        assert read.headers.get("access-control-allow-origin") == "*"
        assert registry.path.read_bytes() == before

        # A trusted local dashboard Origin may mutate state.
        enabled = await client.post(
            f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/enable",
            headers={"Origin": LOCAL_ORIGIN},
        )
        assert enabled.status_code == 200 and enabled.json()["enabled"] is True

        selected = await client.post(
            f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/select",
            headers={"Origin": "http://localhost:8000"},
        )
        assert selected.status_code == 200 and selected.json()["active"] is True

        # Local scripts/test clients without Origin remain compatible.
        disabled = await client.post(f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/disable")
        assert disabled.status_code == 200 and disabled.json()["enabled"] is False
        no_origin_enable = await client.post(f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/enable")
        assert no_origin_enable.status_code == 200 and no_origin_enable.json()["enabled"] is True

        # Unsafe write preflight is rejected before wildcard CORS and cannot alter state.
        state_before_preflight = registry.path.read_bytes()
        for requested_method in ("POST", "DELETE"):
            preflight = await client.options(
                f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/select",
                headers={
                    "Origin": EVIL_ORIGIN,
                    "Access-Control-Request-Method": requested_method,
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 403
            assert "access-control-allow-origin" not in preflight.headers
            assert registry.path.read_bytes() == state_before_preflight

        trusted_preflight = await client.options(
            f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/select",
            headers={
                "Origin": LOCAL_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert trusted_preflight.status_code == 200
        assert trusted_preflight.headers.get("access-control-allow-origin") == "*"
        assert registry.path.read_bytes() == state_before_preflight

        # Foreign read preflight remains unaffected.
        read_preflight = await client.options(
            "/api/v1/voice-packs",
            headers={"Origin": EVIL_ORIGIN, "Access-Control-Request-Method": "GET"},
        )
        assert read_preflight.status_code == 200
        assert registry.path.read_bytes() == state_before_preflight

    # Client IP remains an independent requirement even when Origin is absent.
    async with await _request_client(app, "203.0.113.10") as remote:
        before_remote = registry.path.read_bytes()
        rejected = await remote.post(f"/api/v1/voice-packs/{PACK_ID}/{PACK_VERSION}/disable")
        assert rejected.status_code == 403
        assert rejected.json()["detail"]["code"] == "voice_pack_local_only"
        assert registry.path.read_bytes() == before_remote


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-voice-pack-origin-") as temp_dir:
        asyncio.run(check_origin_guard(Path(temp_dir)))
    print("voice pack origin guard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
