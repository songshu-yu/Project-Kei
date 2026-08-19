"""PK-211 isolated tests: fake source, fake HTTP, fake archives, temporary roots."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import _path_setup  # noqa: F401
import httpx

from features.voice.errors import VoiceError
from features.voice.models import SynthesisRequest, VoicePackRef
from features.voice.providers.gpt_sovits.acquisition import (
    AcquisitionError,
    LocalEngineRegistry,
    acquire_engine,
)
from features.voice.providers.gpt_sovits.descriptor import DescriptorError, EngineDescriptor, load_descriptor
from features.voice.providers.gpt_sovits.provider import GPTSoVITSConfig, GPTSoVITSProvider


def _archive_bytes(*, unsafe: bool = False, include_script: bool = False) -> bytes:
    with tempfile.TemporaryDirectory(prefix="kei-pk211-archive-") as temp_dir:
        archive_path = Path(temp_dir) / "fake.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("engine-root/api.py", "# fake engine entry\n")
            archive.writestr("engine-root/runtime/python.exe", b"fake-python")
            if include_script:
                archive.writestr("engine-root/install.ps1", "Set-Content should-never-exist.txt executed")
            if unsafe:
                archive.writestr("../escaped.txt", "unsafe")
        return archive_path.read_bytes()


def _descriptor_mapping(archive: bytes) -> dict:
    commit = "a" * 40
    revision = "b" * 40
    return {
        "schema_version": 1,
        "engine_id": "gpt-sovits-test-fixed",
        "provider_key": "gpt-sovits",
        "provider_protocol_version": "pk210-tts-v1",
        "version": "test-v2pro",
        "upstream": {
            "repository": "https://github.com/RVC-Boss/GPT-SoVITS",
            "release": "test-release-v2pro",
            "commit": commit,
            "release_url": "https://github.com/RVC-Boss/GPT-SoVITS/releases/tag/test-release-v2pro",
            "license": "MIT",
            "license_url": f"https://github.com/RVC-Boss/GPT-SoVITS/blob/{commit}/LICENSE",
        },
        "distribution": {
            "source_id": "fake-official-metadata",
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
            "integrity": {"algorithm": "sha256", "digest": hashlib.sha256(archive).hexdigest()},
        },
        "api_styles": {
            "default": "auto",
            "supported": ["auto", "api_py", "legacy_v2"],
        },
        "health_check": {"method": "GET", "path": "/docs", "timeout_seconds": 0.2},
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
    }


def _descriptor(archive: bytes) -> EngineDescriptor:
    return EngineDescriptor.from_mapping(_descriptor_mapping(archive))


def _fake_downloader(archive: bytes):
    def download(_descriptor: EngineDescriptor, target: Path) -> None:
        target.write_bytes(archive)

    return download


def _expect_acquisition_error(code: str, action) -> None:
    try:
        action()
        raise AssertionError(f"expected acquisition error: {code}")
    except AcquisitionError as exc:
        assert exc.code == code, exc.to_public_dict()
        public = json.dumps(exc.to_public_dict(), ensure_ascii=False)
        assert "huggingface" not in public and "private" not in public and "secret" not in public


def check_descriptor_and_source_policy() -> None:
    builtin = load_descriptor()
    assert builtin.release_identity == "20250606v2pro@d7c2210da8c013e81a94bfc7b811a477c99fd506"
    assert builtin.distribution_revision == "fb387b7a65a5441e5e3985f4ab9b721a9d455363"
    assert builtin.size_bytes == 8835144925
    assert builtin.supported_api_styles == ("auto", "api_py", "legacy_v2")
    assert builtin.public_summary()["installation"]["status"] == "unregistered"

    archive = _archive_bytes()
    raw = _descriptor_mapping(archive)
    assert EngineDescriptor.from_mapping(raw).release_identity == "test-release-v2pro@" + "a" * 40

    wrong_source = copy.deepcopy(raw)
    wrong_source["distribution"]["repository"] = "https://example.invalid/arbitrary"
    try:
        EngineDescriptor.from_mapping(wrong_source)
        raise AssertionError("arbitrary source must be rejected")
    except DescriptorError as exc:
        assert exc.code == "source_not_approved"

    short_commit = copy.deepcopy(raw)
    short_commit["upstream"]["commit"] = "abc123"
    try:
        EngineDescriptor.from_mapping(short_commit)
        raise AssertionError("short commit must be rejected")
    except DescriptorError as exc:
        assert exc.code == "descriptor_unpinned"


def check_acquisition_failures(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    archive = _archive_bytes()
    descriptor = _descriptor(archive)
    project_root = root / "project"
    project_root.mkdir()

    bad_digest_raw = _descriptor_mapping(archive)
    bad_digest_raw["distribution"]["integrity"]["digest"] = "0" * 64
    bad_digest = EngineDescriptor.from_mapping(bad_digest_raw)
    mismatch_target = root / "external" / "mismatch"
    mismatch_config = root / "state" / "mismatch.json"
    _expect_acquisition_error(
        "integrity_mismatch",
        lambda: acquire_engine(
            bad_digest,
            mismatch_target,
            confirmation=bad_digest.engine_id,
            registry_path=mismatch_config,
            project_root=project_root,
            downloader=_fake_downloader(archive),
        ),
    )
    assert not mismatch_target.exists() and not mismatch_config.exists()

    def interrupted(_descriptor: EngineDescriptor, target: Path) -> None:
        target.write_bytes(archive[:8])
        raise AcquisitionError("download_interrupted", "固定来源下载中断")

    interrupted_target = root / "external" / "interrupted"
    _expect_acquisition_error(
        "download_interrupted",
        lambda: acquire_engine(
            descriptor,
            interrupted_target,
            confirmation=descriptor.engine_id,
            registry_path=root / "state" / "interrupted.json",
            project_root=project_root,
            downloader=interrupted,
        ),
    )
    assert not interrupted_target.exists()

    occupied = root / "external" / "occupied"
    occupied.mkdir(parents=True)
    (occupied / "keep.txt").write_text("user-owned", encoding="utf-8")
    _expect_acquisition_error(
        "target_exists",
        lambda: acquire_engine(
            descriptor,
            occupied,
            confirmation=descriptor.engine_id,
            registry_path=root / "state" / "occupied.json",
            project_root=project_root,
            downloader=_fake_downloader(archive),
        ),
    )
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "user-owned"

    failed_target = root / "external" / "extract-failed"
    failed_config = root / "state" / "extract-failed.json"

    def failed_extractor(_descriptor: EngineDescriptor, _archive: Path, staging: Path) -> None:
        (staging / "partial.tmp").write_text("partial", encoding="utf-8")
        raise AcquisitionError("archive_extract_failed", "归档解包失败")

    _expect_acquisition_error(
        "archive_extract_failed",
        lambda: acquire_engine(
            descriptor,
            failed_target,
            confirmation=descriptor.engine_id,
            registry_path=failed_config,
            project_root=project_root,
            downloader=_fake_downloader(archive),
            extractor=failed_extractor,
        ),
    )
    assert not failed_target.exists() and not failed_config.exists()

    blocked_parent = root / "state" / "blocked-parent"
    blocked_parent.parent.mkdir(parents=True, exist_ok=True)
    blocked_parent.write_text("not-a-directory", encoding="utf-8")
    commit_failed_target = root / "external" / "config-commit-failed"
    _expect_acquisition_error(
        "local_config_write_failed",
        lambda: acquire_engine(
            descriptor,
            commit_failed_target,
            confirmation=descriptor.engine_id,
            registry_path=blocked_parent / "engine.json",
            project_root=project_root,
            downloader=_fake_downloader(archive),
        ),
    )
    assert not commit_failed_target.exists(), "failed local-state commit must roll back the new install"
    assert blocked_parent.read_text(encoding="utf-8") == "not-a-directory"

    unsafe_archive = _archive_bytes(unsafe=True)
    unsafe_descriptor = _descriptor(unsafe_archive)
    unsafe_target = root / "external" / "unsafe"
    _expect_acquisition_error(
        "archive_unsafe",
        lambda: acquire_engine(
            unsafe_descriptor,
            unsafe_target,
            confirmation=unsafe_descriptor.engine_id,
            registry_path=root / "state" / "unsafe.json",
            project_root=project_root,
            downloader=_fake_downloader(unsafe_archive),
        ),
    )
    assert not unsafe_target.exists() and not (root / "external" / "escaped.txt").exists()


def check_success_repeat_offline_and_no_scripts(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    archive = _archive_bytes(include_script=True)
    descriptor = _descriptor(archive)
    project_root = root / "project"
    project_root.mkdir(exist_ok=True)
    target = root / "external" / "installed"
    config = root / "state" / "engine.json"
    sentinel = target.parent / "should-never-exist.txt"

    result = acquire_engine(
        descriptor,
        target,
        confirmation=descriptor.engine_id,
        registry_path=config,
        project_root=project_root,
        downloader=_fake_downloader(archive),
    )
    assert result.status == "installed_verified"
    assert (target / "install.ps1").is_file()
    assert not sentinel.exists(), "archive scripts must never execute"
    marker = json.loads((target / ".project-kei-engine.json").read_text(encoding="utf-8"))
    assert marker["scripts_executed"] is False

    def must_not_download(_descriptor: EngineDescriptor, _target: Path) -> None:
        raise AssertionError("repeat acquisition must reuse the fixed install")

    repeated = acquire_engine(
        descriptor,
        target,
        confirmation=descriptor.engine_id,
        registry_path=config,
        project_root=project_root,
        downloader=must_not_download,
    )
    assert repeated.status == "installed_verified"

    offline = acquire_engine(
        descriptor,
        target,
        confirmation=descriptor.engine_id,
        registry_path=config,
        project_root=project_root,
        downloader=must_not_download,
        offline=True,
    )
    assert offline.status == "installed_verified"
    status = LocalEngineRegistry(config).status(descriptor)
    assert status["entrypoints_ready"] is True
    assert str(target) not in json.dumps(status, ensure_ascii=False)

    existing = root / "external" / "existing"
    (existing / "runtime").mkdir(parents=True)
    (existing / "api.py").write_text("# existing\n", encoding="utf-8")
    (existing / "runtime" / "python.exe").write_bytes(b"existing")
    existing_config = root / "state" / "existing.json"
    LocalEngineRegistry(existing_config).register(
        descriptor,
        existing,
        api_style="legacy_v2",
        install_status="registered_existing",
        integrity_status="unverified_existing_install",
    )
    reused = acquire_engine(
        descriptor,
        existing,
        confirmation=descriptor.engine_id,
        registry_path=existing_config,
        project_root=project_root,
        downloader=must_not_download,
        offline=True,
    )
    assert reused.status == "offline_reuse"
    assert reused.integrity_status == "unverified_existing_install"


async def check_provider_health_and_styles() -> None:
    archive = _archive_bytes()
    descriptor = _descriptor(archive)
    requests: list[tuple[str, dict]] = []

    def auto_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/docs":
            return httpx.Response(200, text="fake docs")
        payload = json.loads(request.content.decode("utf-8"))
        requests.append((request.url.path, payload))
        if request.url.path == "/":
            return httpx.Response(404, text="secret C:/private/model.pth")
        return httpx.Response(200, content=b"RIFFfake", headers={"content-type": "audio/wav"})

    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="auto"),
        transport=httpx.MockTransport(auto_handler),
        descriptor=descriptor,
    )
    health = await provider.health()
    assert health.available and provider.capabilities().provider == "gpt-sovits"
    pack = VoicePackRef(
        "fake-pack",
        "1",
        "gpt-sovits",
        handle={
            "ref_audio_path": "opaque-reference.wav",
            "prompt_text": "fake prompt",
            "prompt_lang": "ja",
            "text_lang": "zh",
        },
    )
    result = await provider.synthesize(SynthesisRequest("auto", "测试", timeout_seconds=0.2), pack)
    assert result.audio == b"RIFFfake"
    assert [item[0] for item in requests] == ["/", "/tts"]
    assert requests[0][1]["text_language"] == "zh"
    assert requests[1][1]["ref_audio_path"] == "opaque-reference.wav"
    await provider.close()

    for style, expected_path, expected_key in (
        ("api_py", "/", "text_language"),
        ("legacy_v2", "/tts", "text_lang"),
        ("gptsovits", "/", "text_language"),
        ("legacy", "/tts", "text_lang"),
    ):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content=b"RIFFstyle", headers={"content-type": "audio/wav"})

        item = GPTSoVITSProvider(
            GPTSoVITSConfig(api_style=style),
            transport=httpx.MockTransport(handler),
            descriptor=descriptor,
        )
        audio = await item.synthesize(SynthesisRequest(style, "样式", timeout_seconds=0.2), pack)
        payload = json.loads(seen[0].content.decode("utf-8"))
        assert seen[0].url.path == expected_path and expected_key in payload and audio.audio
        if style in {"api_py", "gptsovits"}:
            assert seen[0].method == "POST"
            assert payload["prompt_language"] == "ja"
            assert payload["text_language"] == "zh"
        await item.close()


async def check_provider_installable_contract_bridge() -> None:
    """An isolated package copy must not fall through to the legacy bytes API."""

    descriptor = _descriptor(_archive_bytes())
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=b"RIFFisolated-contract",
            headers={"content-type": "audio/wav"},
        )

    class IsolatedSegment:
        segment_id = "segment-0001"
        sequence = 0
        text = "isolated text"

    class IsolatedRequest:
        request_id = "isolated-request"
        text = "isolated text"
        emotion = "calm"
        audio_format = "wav"
        timeout_seconds = 0.2
        segments = (IsolatedSegment(),)

    class IsolatedPack:
        pack_id = "isolated-pack"
        pack_version = "1.0.0"
        engine_provider = "gpt-sovits"
        handle = {
            "ref_audio_path": "opaque-reference.wav",
            "prompt_text": "opaque prompt",
            "prompt_lang": "ja",
            "text_lang": "zh",
        }

    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py"),
        transport=httpx.MockTransport(handler),
        descriptor=descriptor,
    )
    result = await provider.synthesize(IsolatedRequest(), IsolatedPack())
    assert result.audio == b"RIFFisolated-contract"
    assert result.media_type == "audio/wav" and result.audio_format == "wav"
    assert len(seen) == 1 and seen[0].url.path == "/"
    payload = json.loads(seen[0].content.decode("utf-8"))
    assert payload["text"] == "isolated text"
    assert payload["refer_wav_path"] == "opaque-reference.wav"
    await provider.close()


async def check_provider_timeout_and_sanitization() -> None:
    descriptor = _descriptor(_archive_bytes())

    def unavailable_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret upstream path", request=request)

    unavailable_provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py"),
        transport=httpx.MockTransport(unavailable_handler),
        descriptor=descriptor,
    )
    health = await unavailable_provider.health()
    assert health.available is False and health.error_code == "tts_unavailable"
    await unavailable_provider.close()

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret C:/private/model.pth", request=request)

    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py"),
        transport=httpx.MockTransport(timeout_handler),
        descriptor=descriptor,
    )
    try:
        await provider.synthesize(
            SynthesisRequest("timeout", "测试", timeout_seconds=0.01),
            VoicePackRef("fake", "1", "gpt-sovits"),
        )
        raise AssertionError("timeout must fail")
    except VoiceError as exc:
        public = json.dumps(exc.to_public_dict(), ensure_ascii=False)
        assert exc.code == "tts_timeout"
        assert "secret" not in public and "private" not in public and "model.pth" not in public
    await provider.close()

    def invalid_audio(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="secret C:/private/model.pth", headers={"content-type": "text/plain"})

    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="legacy_v2"),
        transport=httpx.MockTransport(invalid_audio),
        descriptor=descriptor,
    )
    try:
        await provider.synthesize(
            SynthesisRequest("invalid", "测试", timeout_seconds=0.2),
            VoicePackRef("fake", "1", "gpt-sovits"),
        )
        raise AssertionError("invalid response must fail")
    except VoiceError as exc:
        public = json.dumps(exc.to_public_dict(), ensure_ascii=False)
        assert exc.code == "tts_failed"
        assert "secret" not in public and "private" not in public
    await provider.close()


async def check_provider_voice_pack_activation() -> None:
    descriptor = _descriptor(_archive_bytes())
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/set_model":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, content=b"RIFFpack", headers={"content-type": "audio/wav"})

    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py"),
        transport=httpx.MockTransport(handler),
        descriptor=descriptor,
    )
    pack = VoicePackRef(
        "fake-kei", "1.0.0", "gpt-sovits",
        handle={
            "gpt_checkpoint_path": "opaque-gpt.ckpt",
            "sovits_checkpoint_path": "opaque-sovits.pth",
            "ref_audio_path": "opaque-reference.wav",
            "prompt_text": "fake prompt",
            "prompt_lang": "ja",
            "text_lang": "zh",
            "generation_parameters": {
                "top_k": 9,
                "temperature": 0.7,
                "speed_factor": 1.1,
                "text_split_method": "must-not-leak",
                "text": "must-not-override",
            },
        },
    )
    result = await provider.synthesize(SynthesisRequest("pack-config", "测试", timeout_seconds=0.2), pack)
    assert result.audio == b"RIFFpack"
    assert [request.url.path for request in seen] == ["/set_model", "/"]
    assert seen[0].url.params["gpt_model_path"] == "opaque-gpt.ckpt"
    assert seen[0].url.params["sovits_model_path"] == "opaque-sovits.pth"
    assert seen[1].method == "POST"
    payload = json.loads(seen[1].content.decode("utf-8"))
    assert payload["refer_wav_path"] == "opaque-reference.wav"
    assert payload["prompt_text"] == "fake prompt" and payload["prompt_language"] == "ja"
    assert payload["text"] != "must-not-override" and payload["text_language"] == "zh"
    assert payload["top_k"] == 9 and payload["temperature"] == 0.7 and payload["speed"] == 1.1
    assert "text_split_method" not in payload
    await provider.close()


async def check_provider_voice_pack_activation_falls_back_to_split() -> None:
    descriptor = _descriptor(_archive_bytes())
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/set_model":
            return httpx.Response(404, json={"detail": "not found"})
        if request.url.path in {"/set_gpt_weights", "/set_sovits_weights"}:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, content=b"RIFFpack", headers={"content-type": "audio/wav"})

    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py"),
        transport=httpx.MockTransport(handler),
        descriptor=descriptor,
    )
    pack = VoicePackRef(
        "fake-kei", "1.0.0", "gpt-sovits",
        handle={
            "gpt_checkpoint_path": "opaque-gpt.ckpt",
            "sovits_checkpoint_path": "opaque-sovits.pth",
        },
    )
    result = await provider.synthesize(SynthesisRequest("split-fallback", "test", timeout_seconds=0.2), pack)
    assert result.audio == b"RIFFpack"
    assert [request.url.path for request in seen] == [
        "/set_model", "/set_gpt_weights", "/set_sovits_weights", "/",
    ]
    assert seen[1].url.params["weights_path"] == "opaque-gpt.ckpt"
    assert seen[2].url.params["weights_path"] == "opaque-sovits.pth"
    await provider.close()


async def check_provider_voice_pack_activation_does_not_mask_engine_failure() -> None:
    descriptor = _descriptor(_archive_bytes())
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500, json={"detail": "private upstream failure"})

    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py"),
        transport=httpx.MockTransport(handler),
        descriptor=descriptor,
    )
    pack = VoicePackRef(
        "fake-kei", "1.0.0", "gpt-sovits",
        handle={
            "gpt_checkpoint_path": "opaque-gpt.ckpt",
            "sovits_checkpoint_path": "opaque-sovits.pth",
        },
    )
    try:
        await provider.synthesize(SynthesisRequest("combined-failure", "test", timeout_seconds=0.2), pack)
        raise AssertionError("combined endpoint failure must fail closed")
    except VoiceError as exc:
        assert exc.code == "tts_engine_state_unknown"
    assert [request.url.path for request in seen] == ["/set_model"]
    await provider.close()


async def check_provider_cancel() -> None:
    descriptor = _descriptor(_archive_bytes())

    class BlockingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def handle_async_request(self, _request: httpx.Request) -> httpx.Response:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

    transport = BlockingTransport()
    provider = GPTSoVITSProvider(
        GPTSoVITSConfig(api_style="api_py"),
        transport=transport,
        descriptor=descriptor,
    )
    task = asyncio.create_task(provider.synthesize(
        SynthesisRequest("cancel-me", "测试取消", timeout_seconds=1.0),
        VoicePackRef("fake", "1", "gpt-sovits"),
    ))
    await asyncio.wait_for(transport.started.wait(), timeout=1.0)
    await provider.cancel("cancel-me")
    try:
        await task
        raise AssertionError("cancelled synthesis must not complete")
    except asyncio.CancelledError:
        pass
    assert transport.cancelled.is_set()
    await provider.close()


def main() -> int:
    check_descriptor_and_source_policy()
    with tempfile.TemporaryDirectory(prefix="kei-pk211-") as temp_dir:
        root = Path(temp_dir)
        check_acquisition_failures(root / "failures")
        (root / "success").mkdir()
        check_success_repeat_offline_and_no_scripts(root / "success")
    asyncio.run(check_provider_health_and_styles())
    asyncio.run(check_provider_installable_contract_bridge())
    asyncio.run(check_provider_timeout_and_sanitization())
    asyncio.run(check_provider_voice_pack_activation())
    asyncio.run(check_provider_voice_pack_activation_falls_back_to_split())
    asyncio.run(check_provider_voice_pack_activation_does_not_mask_engine_failure())
    asyncio.run(check_provider_cancel())
    print("gpt-sovits provider tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
