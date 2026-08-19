"""PK-211/PK-212 shared-engine races using only MockTransport and fake assets."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

import _path_setup  # noqa: F401
import httpx

from features.voice.errors import VoiceError
from features.voice.models import SynthesisRequest, VoicePackRef
from features.voice.providers.gpt_sovits.provider import GPTSoVITSConfig, GPTSoVITSProvider
from features.voice.voice_packs.errors import VoicePackSwitchError
from features.voice.voice_packs.registry import VoicePackRegistry
from features.voice.voice_packs.service import VoicePackRegistryService


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _asset(path: Path, root: Path) -> dict:
    return {
        "path": path.relative_to(root).as_posix(),
        "integrity": {
            "mode": "sha256",
            "size_bytes": path.stat().st_size,
            "sha256": _digest(path),
        },
    }


def _make_pack(root: Path, pack_id: str) -> Path:
    package = root / pack_id
    assets = package / "assets"
    assets.mkdir(parents=True)
    gpt = assets / f"{pack_id}.ckpt"
    sovits = assets / f"{pack_id}.pth"
    reference = assets / f"{pack_id}.wav"
    gpt.write_bytes(f"fake-gpt-{pack_id}".encode())
    sovits.write_bytes(f"fake-sovits-{pack_id}".encode())
    reference.write_bytes(b"RIFF" + f"-fake-{pack_id}".encode())
    manifest = {
        "schema_version": 1,
        "id": pack_id,
        "name": f"Fake {pack_id}",
        "version": "1.0.0",
        "engine": {"provider": "gpt-sovits", "protocol_version": "pk210-tts-v1"},
        "supported_languages": ["zh"],
        "gpt_checkpoint": _asset(gpt, package),
        "sovits_checkpoint": _asset(sovits, package),
        "reference_audio": _asset(reference, package),
        "reference_text": "fake prompt",
        "reference_language": "zh",
        "default_text_language": "zh",
        "generation_parameters": {},
        "metadata": {"license": "test-only", "redistribution": "restricted"},
    }
    (package / "voice-pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package


class FakeEngine:
    def __init__(self):
        self.gpt = ""
        self.sovits = ""
        self.requests: list[tuple[str, str]] = []
        self.synthesis_states: list[tuple[str, str]] = []
        self.block_sovits = ""
        self.sovits_started = asyncio.Event()
        self.sovits_cancelled = asyncio.Event()
        self.fail_sovits_once = ""
        self.fail_rollback_gpt = ""
        self.rollback_armed = False
        self.block_next_synthesis = False
        self.synthesis_started = asyncio.Event()
        self.release_synthesis = asyncio.Event()
        self.synthesis_cancelled = asyncio.Event()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/set_gpt_weights":
            weight = request.url.params["weights_path"]
            self.requests.append((path, weight))
            if self.rollback_armed and weight == self.fail_rollback_gpt:
                return httpx.Response(500, json={"ok": False})
            self.gpt = weight
            return httpx.Response(200, json={"ok": True})
        if path == "/set_sovits_weights":
            weight = request.url.params["weights_path"]
            self.requests.append((path, weight))
            if weight == self.block_sovits:
                self.sovits_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    self.sovits_cancelled.set()
                    raise
            if weight == self.fail_sovits_once:
                self.fail_sovits_once = ""
                self.rollback_armed = True
                return httpx.Response(500, json={"ok": False})
            self.sovits = weight
            return httpx.Response(200, json={"ok": True})
        if path == "/":
            state = (self.gpt, self.sovits)
            self.synthesis_states.append(state)
            if self.block_next_synthesis:
                self.block_next_synthesis = False
                self.synthesis_started.set()
                try:
                    await self.release_synthesis.wait()
                except asyncio.CancelledError:
                    self.synthesis_cancelled.set()
                    raise
            audio = f"RIFF:{Path(state[0]).name}:{Path(state[1]).name}".encode()
            return httpx.Response(200, content=audio, headers={"content-type": "audio/wav"})
        return httpx.Response(404)


async def _system(root: Path) -> tuple[FakeEngine, GPTSoVITSProvider, VoicePackRegistryService]:
    engine = FakeEngine()
    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py", timeout_seconds=2.0),
        transport=httpx.MockTransport(engine.handle),
    )
    registry = VoicePackRegistryService(
        VoicePackRegistry(root / "registry.json"),
        runtime_root=root / "runtime",
        activator=provider,
    )
    provider.set_voice_pack_resolver(registry)
    for pack_id in ("pack-a", "pack-b"):
        await registry.import_pack(_make_pack(root / "packs", pack_id))
        await registry.enable(pack_id, "1.0.0")
    await registry.select("pack-a", "1.0.0")
    engine.requests.clear()
    return engine, provider, registry


def _is_pack(engine_path: str, pack_id: str, suffix: str) -> bool:
    return Path(engine_path).name == f"{pack_id}.{suffix}"


async def check_mid_switch_cancellation(root: Path) -> None:
    engine, provider, registry = await _system(root)
    pack_b = await registry.resolve_pack("pack-b")
    engine.block_sovits = pack_b.handle["sovits_checkpoint_path"]
    switching = asyncio.create_task(registry.select("pack-b", "1.0.0"))
    await asyncio.wait_for(engine.sovits_started.wait(), 1.0)
    switching.cancel()
    try:
        await switching
        raise AssertionError("cancelled selection completed")
    except asyncio.CancelledError:
        pass
    assert engine.sovits_cancelled.is_set()
    assert _is_pack(engine.gpt, "pack-a", "ckpt") and _is_pack(engine.sovits, "pack-a", "pth")
    assert (await registry.list_packs())["active"] == "pack-a@1.0.0"
    assert provider.voice_pack_state() == {"status": "ready", "active": "pack-a@1.0.0"}
    await provider.close()


async def check_second_stage_failure_and_old_pack_reuse(root: Path) -> None:
    engine, provider, registry = await _system(root)
    pack_b = await registry.resolve_pack("pack-b")
    engine.fail_sovits_once = pack_b.handle["sovits_checkpoint_path"]
    try:
        await registry.select("pack-b", "1.0.0")
        raise AssertionError("second-stage failure was accepted")
    except VoicePackSwitchError:
        pass
    assert _is_pack(engine.gpt, "pack-a", "ckpt") and _is_pack(engine.sovits, "pack-a", "pth")
    assert (await registry.list_packs())["active"] == "pack-a@1.0.0"
    old_pack = await registry.resolve_active_pack()
    result = await provider.synthesize(SynthesisRequest("old-after-failure", "fake", timeout_seconds=1.0), old_pack)
    assert result.audio.endswith(b"pack-a.ckpt:pack-a.pth")
    await provider.close()


async def check_rollback_failure_becomes_unknown(root: Path) -> None:
    engine, provider, registry = await _system(root)
    pack_a = await registry.resolve_pack("pack-a")
    pack_b = await registry.resolve_pack("pack-b")
    engine.fail_sovits_once = pack_b.handle["sovits_checkpoint_path"]
    engine.fail_rollback_gpt = pack_a.handle["gpt_checkpoint_path"]
    try:
        await registry.select("pack-b", "1.0.0")
        raise AssertionError("rollback failure was accepted")
    except VoicePackSwitchError as exc:
        assert "unknown" in str(exc)
    assert provider.voice_pack_state() == {"status": "unknown", "active": None}
    listing = await registry.list_packs()
    assert listing["active"] is None and listing["engine_state"] == "unknown"
    assert (await provider.health()).error_code == "tts_engine_state_unknown"
    assert (await registry.health()).error_code == "voice_pack_engine_state_unknown"
    try:
        await registry.resolve_active_pack()
        raise AssertionError("unknown engine exposed the old Pack")
    except VoiceError as exc:
        assert exc.code == "voice_pack_engine_state_unknown"
    await provider.close()


async def check_select_waits_for_inflight_synthesis(root: Path) -> None:
    engine, provider, registry = await _system(root)
    pack_a = await registry.resolve_active_pack()
    engine.block_next_synthesis = True
    synthesis = asyncio.create_task(provider.synthesize(SynthesisRequest("blocked-a", "fake"), pack_a))
    await asyncio.wait_for(engine.synthesis_started.wait(), 1.0)
    selection = asyncio.create_task(registry.select("pack-b", "1.0.0"))
    await asyncio.sleep(0)
    assert not selection.done()
    assert _is_pack(engine.gpt, "pack-a", "ckpt") and _is_pack(engine.sovits, "pack-a", "pth")
    engine.release_synthesis.set()
    await synthesis
    await selection
    assert _is_pack(engine.gpt, "pack-b", "ckpt") and _is_pack(engine.sovits, "pack-b", "pth")
    assert (await registry.list_packs())["active"] == "pack-b@1.0.0"
    await provider.close()


async def check_two_pack_syntheses_are_serial(root: Path) -> None:
    engine = FakeEngine()
    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py", timeout_seconds=2.0),
        transport=httpx.MockTransport(engine.handle),
    )
    pack_a = VoicePackRef("pack-a", "1.0.0", "gpt-sovits", handle={
        "gpt_checkpoint_path": str(root / "pack-a.ckpt"),
        "sovits_checkpoint_path": str(root / "pack-a.pth"),
    })
    pack_b = VoicePackRef("pack-b", "1.0.0", "gpt-sovits", handle={
        "gpt_checkpoint_path": str(root / "pack-b.ckpt"),
        "sovits_checkpoint_path": str(root / "pack-b.pth"),
    })
    await provider.activate_voice_pack(pack_a)
    engine.requests.clear()
    engine.block_next_synthesis = True
    first = asyncio.create_task(provider.synthesize(SynthesisRequest("concurrent-a", "a"), pack_a))
    await asyncio.wait_for(engine.synthesis_started.wait(), 1.0)
    second = asyncio.create_task(provider.synthesize(SynthesisRequest("concurrent-b", "b"), pack_b))
    await asyncio.sleep(0)
    assert not second.done() and not any("pack-b" in weight for _, weight in engine.requests)
    engine.release_synthesis.set()
    first_result, second_result = await asyncio.gather(first, second)
    assert first_result.audio.endswith(b"pack-a.ckpt:pack-a.pth")
    assert second_result.audio.endswith(b"pack-b.ckpt:pack-b.pth")
    assert engine.synthesis_states == [
        (str(root / "pack-a.ckpt"), str(root / "pack-a.pth")),
        (str(root / "pack-b.ckpt"), str(root / "pack-b.pth")),
    ]
    await provider.close()


async def check_repeated_selection_is_idempotent(root: Path) -> None:
    engine, provider, registry = await _system(root)
    await registry.select("pack-a", "1.0.0")
    await registry.select("pack-a", "1.0.0")
    assert engine.requests == []
    assert (await registry.list_packs())["active"] == "pack-a@1.0.0"
    await provider.close()


async def check_close_with_switch_and_synthesis(root: Path) -> None:
    engine, provider, registry = await _system(root / "switch")
    pack_b = await registry.resolve_pack("pack-b")
    engine.block_sovits = pack_b.handle["sovits_checkpoint_path"]
    switching = asyncio.create_task(registry.select("pack-b", "1.0.0"))
    await asyncio.wait_for(engine.sovits_started.wait(), 1.0)
    await provider.close()
    try:
        await switching
        raise AssertionError("close did not cancel switching")
    except asyncio.CancelledError:
        pass
    assert _is_pack(engine.gpt, "pack-a", "ckpt") and _is_pack(engine.sovits, "pack-a", "pth")
    assert provider.voice_pack_state()["status"] == "closed"

    engine, provider, registry = await _system(root / "synthesis")
    pack_a = await registry.resolve_active_pack()
    engine.block_next_synthesis = True
    synthesis = asyncio.create_task(provider.synthesize(SynthesisRequest("close-synthesis", "fake"), pack_a))
    await asyncio.wait_for(engine.synthesis_started.wait(), 1.0)
    await provider.close()
    try:
        await synthesis
        raise AssertionError("close did not cancel synthesis")
    except asyncio.CancelledError:
        pass
    assert engine.synthesis_cancelled.is_set()
    assert provider.voice_pack_state()["status"] == "closed"


async def main_async(root: Path) -> None:
    await check_mid_switch_cancellation(root / "cancel")
    await check_second_stage_failure_and_old_pack_reuse(root / "rollback")
    await check_rollback_failure_becomes_unknown(root / "rollback-failed")
    await check_select_waits_for_inflight_synthesis(root / "select-vs-synthesis")
    await check_two_pack_syntheses_are_serial(root / "two-syntheses")
    await check_repeated_selection_is_idempotent(root / "repeat")
    await check_close_with_switch_and_synthesis(root / "close")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kei-gpt-sovits-session-") as temp_dir:
        asyncio.run(main_async(Path(temp_dir)))
    print("gpt-sovits engine session tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
