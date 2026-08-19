"""Isolated PK-210 tests: fake providers, fake PK-200, and temporary audio roots."""
from __future__ import annotations

import asyncio
import io
import json
import tempfile
from datetime import datetime
from pathlib import Path

import _path_setup  # noqa: F401
import httpx
from fastapi import FastAPI

from features.conversation.models import ConversationReply
from features.voice.errors import VoiceError
from features.voice.media import (
    OUTPUT_PROFILE,
    PcmAudio,
    PcmUtterancePipeline,
    SynthesisMediaError,
    duration_milliseconds,
)
from features.voice.models import (
    AudioResult,
    AudioSegment,
    EncodedUtterance,
    ProviderCapabilities,
    ProviderHealth,
    SynthesizedUtterance,
    SynthesisRequest,
    Transcript,
    TranscriptionRequest,
    VoicePackRef,
    VoiceRequest,
)
from features.voice.providers.conversation import ConversationServiceProvider
from features.voice.providers.asr_http import ASRClient, ASRConfig
from features.voice.providers.tts_http import TTSClient, TTSConfig
from features.voice.router import create_voice_router, read_limited_audio
from features.voice.service import VoiceService
from features.voice.storage import VoiceArtifactStore


class FakeASR:
    def __init__(self, text: str = "老师你好", *, delay: float = 0, error: Exception | None = None):
        self.text = text
        self.delay = delay
        self.error = error
        self.calls = []
        self.cancelled = []
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available" if not self.closed else "closed")

    def capabilities(self):
        return ProviderCapabilities("fake-asr", ("transcribe",), ("wav",))

    async def transcribe(self, request):
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return Transcript(
            text=self.text,
            language="zh",
            language_probability=0.99,
            duration=1.25,
            segments=[{"start": 0.0, "end": 1.0, "text": self.text}],
        )

    async def cancel(self, request_id):
        self.cancelled.append(request_id)

    async def close(self):
        self.closed = True


class FakeConversation:
    def __init__(self, *, delay: float = 0, error: Exception | None = None):
        self.delay = delay
        self.error = error
        self.calls = []
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available" if not self.closed else "closed")

    def capabilities(self):
        return ProviderCapabilities("fake-pk200", ("chat",))

    async def chat(self, message: str, *, request_id: str):
        self.calls.append((request_id, message))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return ConversationReply(text=f"回复：{message}", emotion="calm", timestamp="2026-07-21T12:00:00")

    async def cancel(self, _request_id):
        return None

    async def close(self):
        self.closed = True


class FakeTTS:
    def __init__(self, *, fail_on_call: int = 0, delay: float = 0):
        self.fail_on_call = fail_on_call
        self.delay = delay
        self.calls = []
        self.cancelled = []
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available" if not self.closed else "closed")

    def capabilities(self):
        return ProviderCapabilities("fake-tts", ("synthesize",), ("wav",))

    async def synthesize(self, request, voice_pack):
        self.calls.append((request, voice_pack))
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.fail_on_call and len(self.calls) == self.fail_on_call:
                raise VoiceError(stage="tts", code="tts_failed", message="语音合成失败", status_code=502)
            return AudioResult(audio=f"WAVE:{request.request_id}:{request.text}".encode("utf-8"))
        except asyncio.CancelledError:
            self.cancelled.append(request.request_id)
            raise

    async def cancel(self, request_id):
        self.cancelled.append(request_id)

    async def close(self):
        self.closed = True


class FakePackResolver:
    def __init__(self):
        self.closed = False

    async def health(self):
        return ProviderHealth(not self.closed, "available" if not self.closed else "closed")

    def capabilities(self):
        return ProviderCapabilities("fake-pack", ("resolve",))

    async def resolve_active_pack(self):
        return VoicePackRef("fake-kei", "1.0", "fake-tts", handle=Path("C:/must-not-leak/model.bin"))

    async def resolve_pack(self, pack_id):
        if pack_id != "fake-kei":
            raise LookupError
        return await self.resolve_active_pack()

    async def cancel(self, _request_id):
        return None

    async def close(self):
        self.closed = True


class ContractTTS(FakeTTS):
    def __init__(self, *, mode: str = "segments", wait: asyncio.Event | None = None, error=None):
        super().__init__()
        self.mode = mode
        self.wait = wait
        self.error = error

    async def synthesize(self, request, voice_pack):
        self.calls.append((request, voice_pack))
        try:
            if self.wait is not None:
                await self.wait.wait()
            if self.error is not None:
                raise self.error
            segments = [
                AudioSegment(item.segment_id, item.sequence, f"pcm-{item.sequence}".encode())
                for item in request.segments
            ]
            if self.mode == "missing" and segments:
                segments.pop()
            elif self.mode == "duplicate" and len(segments) > 1:
                segments[-1] = segments[0]
            elif self.mode == "reversed":
                segments.reverse()
            elif self.mode == "full":
                return AudioResult(audio=b"provider-wav")
            return AudioResult(audio=b"", segments=tuple(segments))
        except asyncio.CancelledError:
            self.cancelled.append(request.request_id)
            raise


class FakeSilkEncoder:
    def __init__(self, *, available: bool = True, error=None, oversized: bool = False):
        self.available = available
        self.error = error
        self.oversized = oversized
        self.calls = []
        self.cancelled = []
        self.closed = False

    async def health(self):
        return ProviderHealth(self.available and not self.closed, "available" if self.available else "unavailable")

    def capabilities(self):
        return ProviderCapabilities("fake-silk", ("encode",), (OUTPUT_PROFILE,))

    async def encode(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        audio = b"SILK" + request.pcm_s16le[:16]
        if self.oversized:
            audio = b"S" * 1024
        return EncodedUtterance(audio, "audio/silk", OUTPUT_PROFILE)

    async def cancel(self, request_id):
        self.cancelled.append(request_id)

    async def close(self):
        self.closed = True


def fake_pcm_decoder(_audio, _media_type, _audio_format):
    return PcmAudio(tuple([0] * 10 + [1200] * 240 + [0] * 10), 24_000)


class FakePK200Service:
    """Only the public PK-200 methods used by the adapter are exposed."""

    def __init__(self):
        self.messages = []

    async def chat(self, message):
        self.messages.append(message)
        return ConversationReply("来自 PK-200", "happy", "2026-07-21T12:00:00")

    async def get_profile(self):
        return object()


def build_service(root: Path, *, asr=None, conversation=None, tts_marker=True, **kwargs):
    tts = FakeTTS() if tts_marker is True else tts_marker
    resolver = FakePackResolver() if tts is not None else None
    service = VoiceService(
        asr=FakeASR() if asr is None else asr,
        conversation=FakeConversation() if conversation is None else conversation,
        tts=tts,
        voice_packs=resolver,
        artifacts=VoiceArtifactStore(root / "temp", root / "output"),
        **kwargs,
    )
    return service, tts


async def request_json(app: FastAPI, method: str, path: str, **kwargs):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def check_normal_and_legacy(root: Path):
    conversation = FakeConversation()
    service, tts = build_service(root, conversation=conversation)
    app = FastAPI()
    app.include_router(create_voice_router(lambda: service, max_upload_bytes=1024))
    files = {"file": ("sample.wav", b"fake-wave", "audio/wav")}

    health = await request_json(app, "GET", "/api/v1/voice/health")
    assert health.status_code == 200 and health.json()["status"] == "ready"
    assert health.json()["providers"]["asr"]["capabilities"]["operations"] == ["transcribe"]

    versioned = await request_json(
        app,
        "POST",
        "/api/v1/voice/chat",
        files=files,
        data={"include_audio_base64": "true"},
    )
    assert versioned.status_code == 200, versioned.text
    body = versioned.json()
    assert body["user_text"] == "老师你好"
    assert body["assistant_text"] == "回复：老师你好"
    assert body["audio_available"] is True and body["mode"] == "audio"
    assert body["audio_base64"]
    assert body["audio_path"].startswith("/api/v1/voice/audio/")
    assert "C:/" not in json.dumps(body, ensure_ascii=False)
    audio = await request_json(app, "GET", body["audio_path"])
    assert audio.status_code == 200 and audio.content.startswith(b"WAVE:")

    legacy = await request_json(app, "POST", "/voice/chat", files=files)
    assert legacy.status_code == 200, legacy.text
    legacy_body = legacy.json()
    for key in ("user_text", "assistant_text", "emotion", "audio_path", "audio_paths", "timestamp", "timings_ms", "asr_segments"):
        assert key in legacy_body
    assert legacy_body["audio_path"].startswith("/voice/audio/")
    assert len(conversation.calls) == 2 and len(tts.calls) == 2
    assert not any((root / "temp").iterdir())


async def check_missing_and_failures(root: Path):
    missing_asr = VoiceService(
        asr=None,
        conversation=FakeConversation(),
        tts=None,
        voice_packs=None,
        artifacts=VoiceArtifactStore(root / "missing-temp", root / "missing-output"),
    )
    app = FastAPI()
    app.include_router(create_voice_router(lambda: missing_asr))
    response = await request_json(app, "POST", "/api/v1/voice/chat", files={"file": ("a.wav", b"x", "audio/wav")})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "asr_unavailable"

    conversation = FakeConversation()
    service, _ = build_service(root / "empty", asr=FakeASR(""), conversation=conversation)
    try:
        await service.chat(VoiceRequest(audio=b"x"))
        raise AssertionError("empty transcript should fail")
    except VoiceError as exc:
        assert exc.code == "asr_empty_transcript"
    assert conversation.calls == []
    assert not list((root / "empty" / "output").glob("*.wav"))

    timeout_service, _ = build_service(
        root / "timeout",
        asr=FakeASR(delay=0.05),
        asr_timeout_seconds=0.005,
    )
    try:
        await timeout_service.chat(VoiceRequest(audio=b"x"))
        raise AssertionError("ASR timeout should fail")
    except VoiceError as exc:
        assert exc.code == "asr_timeout"

    conversation_timeout, _ = build_service(
        root / "conversation-timeout",
        conversation=FakeConversation(delay=0.05),
        conversation_timeout_seconds=0.005,
    )
    try:
        await conversation_timeout.chat(VoiceRequest(audio=b"x"))
        raise AssertionError("conversation timeout should fail")
    except VoiceError as exc:
        assert exc.code == "conversation_timeout"

    secret = "C:/private/models/kei.pth upstream-body-secret"
    failure_service, _ = build_service(root / "failure", asr=FakeASR(error=RuntimeError(secret)))
    events = [event async for event in failure_service.stream(VoiceRequest(audio=b"x"))]
    serialized = json.dumps(events, ensure_ascii=False)
    assert events[-1]["event"] == "error" and events[-1]["error"]["code"] == "asr_failed"
    assert "private" not in serialized and "upstream-body-secret" not in serialized


async def check_text_degrade_and_partial_cleanup(root: Path):
    no_tts, _ = build_service(root / "no-tts", tts_marker=None)
    result = await no_tts.chat(VoiceRequest(audio=b"x"))
    assert result.mode == "text_only" and result.degraded is True and not result.audio
    assert result.errors[0]["code"] == "tts_unavailable"
    assert not list((root / "no-tts" / "output").glob("*.wav"))

    slow_tts = FakeTTS(delay=0.05)
    timed_tts, _ = build_service(
        root / "tts-timeout",
        tts_marker=slow_tts,
        tts_timeout_seconds=0.005,
    )
    timed_result = await timed_tts.chat(VoiceRequest(audio=b"x"))
    assert timed_result.mode == "text_only" and timed_result.errors[0]["code"] == "tts_timeout"

    class SplitConversation(FakeConversation):
        async def chat(self, message: str, *, request_id: str):
            self.calls.append((request_id, message))
            return ConversationReply(text="第一句。第二句。", emotion="calm", timestamp="2026-07-21T12:00:00")

    failing_tts = FakeTTS(fail_on_call=2)
    partial, _ = build_service(
        root / "partial",
        conversation=SplitConversation(),
        tts_marker=failing_tts,
    )
    result = await partial.chat(VoiceRequest(audio=b"x", split_tts=True))
    # The reply has punctuation and splits into two chunks; no partial file is published.
    assert result.mode == "text_only" and result.degraded is True
    assert not list((root / "partial" / "output").glob("*.wav"))
    assert not any((root / "partial" / "temp").iterdir())


async def check_stream_interruption(root: Path):
    service, _ = build_service(root)
    stream = service.stream(VoiceRequest(audio=b"x"))
    first = await stream.__anext__()
    second = await stream.__anext__()
    assert first["event"] == "reply" and second["event"] == "audio_part"
    published = list((root / "output").glob("*.wav"))
    assert len(published) == 1
    await stream.aclose()
    assert not list((root / "output").glob("*.wav"))
    assert not any((root / "temp").iterdir())

    slow_tts = FakeTTS(delay=0.2)
    cancelled, _ = build_service(root / "cancelled", tts_marker=slow_tts)
    cancelled_stream = cancelled.stream(VoiceRequest(audio=b"x"))
    assert (await cancelled_stream.__anext__())["event"] == "reply"
    pending = asyncio.create_task(cancelled_stream.__anext__())
    for _ in range(50):
        if slow_tts.calls:
            break
        await asyncio.sleep(0.002)
    assert slow_tts.calls
    pending.cancel()
    try:
        await pending
    except asyncio.CancelledError:
        pass
    assert slow_tts.cancelled
    assert not list((root / "cancelled" / "output").glob("*.wav"))
    assert not any((root / "cancelled" / "temp").iterdir())


async def check_concurrency(root: Path):
    service, _ = build_service(root)
    results = await asyncio.gather(
        service.chat(VoiceRequest(audio=b"one")),
        service.chat(VoiceRequest(audio=b"two")),
    )
    names = [result.audio[0].filename for result in results]
    assert len(set(names)) == 2
    assert all((root / "output" / name).is_file() for name in names)
    assert not any((root / "temp").iterdir())


async def check_upload_limits(root: Path):
    service, _ = build_service(root)
    app = FastAPI()
    app.include_router(create_voice_router(lambda: service, max_upload_bytes=4))
    too_large = await request_json(app, "POST", "/api/v1/voice/chat", files={"file": ("a.wav", b"12345", "audio/wav")})
    assert too_large.status_code == 413 and too_large.json()["detail"]["code"] == "audio_too_large"
    bad_type = await request_json(app, "POST", "/voice/chat", files={"file": ("a.txt", b"123", "text/plain")})
    assert bad_type.status_code == 415 and bad_type.json()["detail"]["code"] == "audio_type_not_allowed"

    class TrackingUpload:
        filename = "bounded.wav"
        content_type = "audio/wav"

        def __init__(self):
            self.data = io.BytesIO(b"0123456789")
            self.requested = []
            self.closed = False

        async def read(self, size):
            self.requested.append(size)
            return self.data.read(size)

        async def close(self):
            self.closed = True

    tracked = TrackingUpload()
    try:
        await read_limited_audio(tracked, 4)
        raise AssertionError("bounded reader should reject")
    except VoiceError as exc:
        assert exc.code == "audio_too_large"
    assert tracked.requested == [5] and tracked.closed


async def check_pk200_contract_and_close(root: Path):
    pk200 = FakePK200Service()
    adapter = ConversationServiceProvider(pk200)
    service, tts = build_service(root, conversation=adapter)
    asr = service.asr
    voice_packs = service.voice_packs
    result = await service.chat(VoiceRequest(audio=b"x"))
    assert result.draft.assistant_text == "来自 PK-200"
    assert pk200.messages == ["老师你好"]
    await service.close()
    assert tts.closed is True and asr.closed is True and voice_packs.closed is True
    assert service.asr is None
    assert service.conversation is None
    assert service.tts is None
    assert service.voice_packs is None


async def check_stream_protocol(root: Path):
    service, _ = build_service(root)
    app = FastAPI()
    app.include_router(create_voice_router(lambda: service))
    response = await request_json(
        app,
        "POST",
        "/api/v1/voice/chat/stream",
        files={"file": ("a.wav", b"x", "audio/wav")},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [item["event"] for item in events] == ["reply", "audio_part", "done"]
    assert events[1]["audio_url"].startswith("/api/v1/voice/audio/")
    assert events[-1]["audio_available"] is True
    assert sum(item["event"] in {"done", "error"} for item in events) == 1


async def check_http_provider_sanitization():
    def asr_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "text": "安全转写",
            "language": "zh",
            "language_probability": 0.9,
            "duration": 1.0,
            "segments": [{
                "start": 0,
                "end": 1,
                "text": "安全转写",
                "local_path": "C:/private/audio.wav",
                "upstream_body": "secret",
            }],
        })

    asr = ASRClient(ASRConfig(), transport=httpx.MockTransport(asr_handler))
    transcript = await asr.transcribe(TranscriptionRequest(request_id="safe", audio=b"x"))
    assert transcript.segments == [{"start": 0.0, "end": 1.0, "text": "安全转写"}]
    await asr.close()

    def tts_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="C:/private/model.pth upstream-secret", headers={"content-type": "text/plain"})

    tts = TTSClient(TTSConfig(), transport=httpx.MockTransport(tts_handler))
    try:
        await tts.synthesize(
            SynthesisRequest(request_id="safe", text="测试"),
            VoicePackRef("fake", "1", "fake"),
        )
        raise AssertionError("non-audio response must fail")
    except VoiceError as exc:
        public = json.dumps(exc.to_public_dict(), ensure_ascii=False)
        assert exc.code == "tts_failed"
        assert "private" not in public and "upstream-secret" not in public
    await tts.close()


async def check_synthesize_contract(root: Path):
    asr = FakeASR()
    conversation = FakeConversation()
    tts = ContractTTS()
    encoder = FakeSilkEncoder()
    pipeline = PcmUtterancePipeline(decoder=fake_pcm_decoder)
    service = VoiceService(
        asr=asr,
        conversation=conversation,
        tts=tts,
        voice_packs=FakePackResolver(),
        utterance_encoder=encoder,
        utterance_pipeline=pipeline,
        artifacts=VoiceArtifactStore(root / "temp", root / "output"),
    )
    app = FastAPI()
    app.include_router(create_voice_router(lambda: service))
    headers = {"Idempotency-Key": "qqmsg_0123456789abcdef"}
    response = await request_json(
        app,
        "POST",
        "/api/v1/voice/synthesize",
        headers=headers,
        json={"purpose": "qq_reply", "text": "你好，世界！第二句。"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/silk"
    assert response.headers["x-kei-audio-final"] == "true"
    assert response.headers["x-kei-audio-duration-ms"] == "80"
    assert response.headers["x-kei-audio-profile"] == "qq_c2c_voice_v1"
    assert response.headers["content-length"] == str(len(response.content))
    assert response.content.startswith(b"SILK") and not response.content.startswith(b"RIFF")
    assert len(tts.calls) == 1 and len(encoder.calls) == 1
    assert asr.calls == [] and conversation.calls == []
    assert len(tts.calls[0][0].segments) == 2
    assert tts.calls[0][0].text == "你好，世界！第二句。"
    serialized = response.text
    assert "C:/" not in serialized and "base64" not in serialized and "voice_pack" not in serialized
    assert not (root / "temp").exists() and not (root / "output").exists()

    assert duration_milliseconds(0.000001) == 1
    assert duration_milliseconds(1.000001) == 1001
    assert duration_milliseconds(60.0) == 60_000

    class DurationOnlyService:
        def __init__(self, duration):
            self.duration = duration

        async def synthesize_text(self, **_kwargs):
            return SynthesizedUtterance(
                b"SILK",
                "audio/silk",
                OUTPUT_PROFILE,
                self.duration,
                "opaque-duration-id",
            )

    for duration in (0.0, float("nan"), float("inf"), 60.000001):
        invalid_duration_app = FastAPI()
        invalid_duration_app.include_router(
            create_voice_router(lambda duration=duration: DurationOnlyService(duration))
        )
        invalid_duration = await request_json(
            invalid_duration_app,
            "POST",
            "/api/v1/voice/synthesize",
            json={"purpose": "qq_reply", "text": "duration"},
        )
        assert invalid_duration.status_code == 502
        assert invalid_duration.json() == {"code": "audio_invalid"}
        assert "opaque-duration-id" not in invalid_duration.text

    health_calls = (len(tts.calls), len(encoder.calls))
    health = await request_json(app, "GET", "/api/v1/voice/health")
    profile = health.json()["synthesis_profiles"]["qq_c2c_voice_v1"]
    assert profile == {
        "available": True,
        "content_type": "audio/silk",
        "final": True,
        "max_bytes": 8 * 1024 * 1024,
        "max_duration_seconds": 60.0,
    }
    assert "qq_media_upload_capability" not in health.json()
    assert health_calls == (len(tts.calls), len(encoder.calls))

    invalid_requests = [
        ({"purpose": "other", "text": "hello"}, None),
        ({"purpose": "qq_reply", "text": ""}, None),
        ({"purpose": "qq_reply", "text": "x" * 1501}, None),
        ({"purpose": "qq_reply", "text": "bad\u0000text"}, None),
        ({"purpose": "qq_reply", "text": "ok", "codec": "wav"}, None),
    ]
    for payload, _unused in invalid_requests:
        rejected = await request_json(
            app,
            "POST",
            "/api/v1/voice/synthesize",
            json=payload,
        )
        assert rejected.status_code == 422 and rejected.json() == {"code": "invalid_request"}
    duplicate = await request_json(
        app,
        "POST",
        "/api/v1/voice/synthesize",
        content=b'{"purpose":"qq_reply","text":"one","text":"two"}',
        headers={"Content-Type": "application/json"},
    )
    assert duplicate.status_code == 422 and duplicate.json() == {"code": "invalid_request"}
    browser_key = await request_json(
        app,
        "POST",
        "/api/v1/voice/synthesize",
        headers={**headers, "Origin": "http://127.0.0.1:8000"},
        json={"purpose": "qq_reply", "text": "browser"},
    )
    assert browser_key.status_code == 422
    evil_origin = await request_json(
        app,
        "POST",
        "/api/v1/voice/synthesize",
        headers={"Origin": "https://evil.example", "X-Forwarded-For": "127.0.0.1"},
        json={"purpose": "qq_reply", "text": "evil"},
    )
    assert evil_origin.status_code == 403
    remote = httpx.ASGITransport(app=app, client=("203.0.113.4", 44000))
    async with httpx.AsyncClient(transport=remote, base_url="http://127.0.0.1:8000") as client:
        spoofed = await client.post(
            "/api/v1/voice/synthesize",
            headers={
                "Host": "127.0.0.1:8000",
                "Origin": "http://127.0.0.1:8000",
                "X-Forwarded-For": "127.0.0.1",
                "Forwarded": "for=127.0.0.1",
            },
            json={"purpose": "qq_reply", "text": "spoofed"},
        )
    assert spoofed.status_code == 403

    unavailable_tts = ContractTTS()
    unavailable_service = VoiceService(
        asr=asr,
        conversation=conversation,
        tts=unavailable_tts,
        voice_packs=FakePackResolver(),
        utterance_encoder=None,
        utterance_pipeline=pipeline,
        artifacts=VoiceArtifactStore(root / "none-temp", root / "none-output"),
    )
    unavailable_app = FastAPI()
    unavailable_app.include_router(create_voice_router(lambda: unavailable_service))
    unavailable = await request_json(
        unavailable_app,
        "POST",
        "/api/v1/voice/synthesize",
        json={"purpose": "qq_reply", "text": "没有 encoder"},
    )
    assert unavailable.status_code == 503
    assert unavailable.json() == {"code": "encoding_unavailable"}
    assert unavailable_tts.calls == []

    for mode in ("missing", "duplicate", "reversed"):
        malformed_tts = ContractTTS(mode=mode)
        malformed_encoder = FakeSilkEncoder()
        malformed = VoiceService(
            asr=asr,
            conversation=conversation,
            tts=malformed_tts,
            voice_packs=FakePackResolver(),
            utterance_encoder=malformed_encoder,
            utterance_pipeline=pipeline,
            artifacts=VoiceArtifactStore(root / f"{mode}-temp", root / f"{mode}-output"),
        )
        malformed_app = FastAPI()
        malformed_app.include_router(create_voice_router(lambda: malformed))
        failed_response = await request_json(
            malformed_app,
            "POST",
            "/api/v1/voice/synthesize",
            json={"purpose": "qq_reply", "text": "第一句。第二句。"},
        )
        assert failed_response.status_code == 502
        assert failed_response.json() == {"code": "audio_invalid"}
        assert len(malformed_tts.calls) == 1 and malformed_encoder.calls == []

    malicious_tts = ContractTTS(error=RuntimeError("C:/private/model upstream secret"))
    malicious = VoiceService(
        asr=asr,
        conversation=conversation,
        tts=malicious_tts,
        voice_packs=FakePackResolver(),
        utterance_encoder=FakeSilkEncoder(),
        utterance_pipeline=pipeline,
        artifacts=VoiceArtifactStore(root / "malicious-temp", root / "malicious-output"),
    )
    malicious_app = FastAPI()
    malicious_app.include_router(create_voice_router(lambda: malicious))
    failed_response = await request_json(
        malicious_app,
        "POST",
        "/api/v1/voice/synthesize",
        json={"purpose": "qq_reply", "text": "安全错误"},
    )
    assert failed_response.json() == {"code": "tts_failed"}
    assert "private" not in failed_response.text and "secret" not in failed_response.text

    async def failure_case(
        expected_code,
        *,
        case_tts=None,
        case_pack=True,
        case_encoder=None,
        case_pipeline=None,
        tts_timeout=60.0,
    ):
        selected_tts = case_tts or ContractTTS()
        selected_encoder = case_encoder if case_encoder is not None else FakeSilkEncoder()
        selected = VoiceService(
            asr=asr,
            conversation=conversation,
            tts=selected_tts,
            voice_packs=FakePackResolver() if case_pack else None,
            utterance_encoder=selected_encoder,
            utterance_pipeline=case_pipeline or pipeline,
            artifacts=VoiceArtifactStore(root / f"{expected_code}-temp", root / f"{expected_code}-output"),
            tts_timeout_seconds=tts_timeout,
        )
        selected_app = FastAPI()
        selected_app.include_router(create_voice_router(lambda: selected))
        result = await request_json(
            selected_app,
            "POST",
            "/api/v1/voice/synthesize",
            json={"purpose": "qq_reply", "text": "失败分支"},
        )
        assert result.json() == {"code": expected_code}
        assert "C:/" not in result.text
        return selected_tts, selected_encoder

    no_pack_tts, _ = await failure_case("voice_pack_unavailable", case_pack=False)
    assert no_pack_tts.calls == []
    unavailable_encoder_tts, _ = await failure_case(
        "encoding_unavailable",
        case_encoder=FakeSilkEncoder(available=False),
    )
    assert unavailable_encoder_tts.calls == []
    timeout_tts, _ = await failure_case(
        "tts_timeout",
        case_tts=ContractTTS(wait=asyncio.Event()),
        tts_timeout=0.005,
    )
    assert len(timeout_tts.calls) == 1 and timeout_tts.cancelled
    encoding_tts, failing_encoder = await failure_case(
        "encoding_unavailable",
        case_encoder=FakeSilkEncoder(error=RuntimeError("C:/private/encoder secret")),
    )
    assert len(encoding_tts.calls) == 1 and len(failing_encoder.calls) == 1
    duration_tts, duration_encoder = await failure_case(
        "audio_too_large",
        case_pipeline=PcmUtterancePipeline(
            decoder=fake_pcm_decoder,
            max_duration_seconds=0.001,
        ),
    )
    assert len(duration_tts.calls) == 1 and duration_encoder.calls == []


async def check_synthesize_idempotency_cancel_and_limits(root: Path):
    release = asyncio.Event()
    tts = ContractTTS(wait=release)
    encoder = FakeSilkEncoder()
    service = VoiceService(
        asr=FakeASR(),
        conversation=FakeConversation(),
        tts=tts,
        voice_packs=FakePackResolver(),
        utterance_encoder=encoder,
        utterance_pipeline=PcmUtterancePipeline(decoder=fake_pcm_decoder),
        artifacts=VoiceArtifactStore(root / "temp", root / "output"),
    )
    app = FastAPI()
    app.include_router(create_voice_router(lambda: service))
    kwargs = {
        "headers": {"Idempotency-Key": "qqmsg_same_0123456789"},
        "json": {"purpose": "qq_reply", "text": "并发同一条消息。"},
    }
    first = asyncio.create_task(request_json(app, "POST", "/api/v1/voice/synthesize", **kwargs))
    second = asyncio.create_task(request_json(app, "POST", "/api/v1/voice/synthesize", **kwargs))
    for _ in range(100):
        if tts.calls:
            break
        await asyncio.sleep(0.002)
    assert len(tts.calls) == 1
    release.set()
    first_result, second_result = await asyncio.gather(first, second)
    assert first_result.content == second_result.content
    assert first_result.headers["x-kei-utterance-id"] == second_result.headers["x-kei-utterance-id"]
    assert len(tts.calls) == 1 and len(encoder.calls) == 1
    replay = await request_json(app, "POST", "/api/v1/voice/synthesize", **kwargs)
    assert replay.content == first_result.content
    assert len(tts.calls) == 1 and len(encoder.calls) == 1
    shared = await service.synthesize_text(
        purpose="qq_reply",
        text="并发同一条消息。",
        idempotency_key="qqmsg_same_0123456789",
    )
    assert shared.utterance_id == first_result.headers["x-kei-utterance-id"]
    assert shared.pcm is not None and shared.pcm.sample_rate == 24_000
    assert len(tts.calls) == 1 and len(encoder.calls) == 1
    conflict = await request_json(
        app,
        "POST",
        "/api/v1/voice/synthesize",
        headers=kwargs["headers"],
        json={"purpose": "qq_reply", "text": "不同文本"},
    )
    assert conflict.status_code == 409 and conflict.json() == {"code": "idempotency_conflict"}

    failed_tts = ContractTTS(error=RuntimeError("paid call failed"))
    failed_service = VoiceService(
        asr=FakeASR(),
        conversation=FakeConversation(),
        tts=failed_tts,
        voice_packs=FakePackResolver(),
        utterance_encoder=FakeSilkEncoder(),
        utterance_pipeline=PcmUtterancePipeline(decoder=fake_pcm_decoder),
        artifacts=VoiceArtifactStore(root / "failed-temp", root / "failed-output"),
    )
    for _index in range(2):
        try:
            await failed_service.synthesize_text(
                purpose="qq_reply",
                text="失败也不重试",
                idempotency_key="qqmsg_failed_01234567",
            )
            raise AssertionError("failed synthesis must remain failed")
        except SynthesisMediaError as exc:
            assert exc.code == "tts_failed"
    assert len(failed_tts.calls) == 1

    slow = ContractTTS(wait=asyncio.Event())
    cancelled_service = VoiceService(
        asr=FakeASR(),
        conversation=FakeConversation(),
        tts=slow,
        voice_packs=FakePackResolver(),
        utterance_encoder=FakeSilkEncoder(),
        utterance_pipeline=PcmUtterancePipeline(decoder=fake_pcm_decoder),
        artifacts=VoiceArtifactStore(root / "cancel-temp", root / "cancel-output"),
    )
    cancelled = asyncio.create_task(cancelled_service.synthesize_text(
        purpose="qq_reply",
        text="取消请求",
        idempotency_key=None,
        disconnected=lambda: asyncio.sleep(0, result=True),
    ))
    try:
        await cancelled
        raise AssertionError("disconnected request must cancel")
    except VoiceError as exc:
        assert exc.code == "request_cancelled"
    assert slow.cancelled
    assert not (root / "cancel-temp").exists() and not (root / "cancel-output").exists()

    oversized_encoder = FakeSilkEncoder(oversized=True)
    limited = VoiceService(
        asr=FakeASR(),
        conversation=FakeConversation(),
        tts=ContractTTS(),
        voice_packs=FakePackResolver(),
        utterance_encoder=oversized_encoder,
        utterance_pipeline=PcmUtterancePipeline(
            decoder=fake_pcm_decoder,
            max_output_bytes=32,
        ),
        artifacts=VoiceArtifactStore(root / "limit-temp", root / "limit-output"),
    )
    limited_app = FastAPI()
    limited_app.include_router(create_voice_router(lambda: limited))
    too_large = await request_json(
        limited_app,
        "POST",
        "/api/v1/voice/synthesize",
        json={"purpose": "qq_reply", "text": "超限"},
    )
    assert too_large.status_code == 413 and too_large.json() == {"code": "audio_too_large"}

    shutdown_tts = ContractTTS(wait=asyncio.Event())
    shutdown = VoiceService(
        asr=FakeASR(),
        conversation=FakeConversation(),
        tts=shutdown_tts,
        voice_packs=FakePackResolver(),
        utterance_encoder=FakeSilkEncoder(),
        utterance_pipeline=PcmUtterancePipeline(decoder=fake_pcm_decoder),
        artifacts=VoiceArtifactStore(root / "shutdown-temp", root / "shutdown-output"),
    )
    pending = asyncio.create_task(shutdown.synthesize_text(
        purpose="qq_reply",
        text="关闭时取消",
        idempotency_key=None,
    ))
    for _ in range(100):
        if shutdown_tts.calls:
            break
        await asyncio.sleep(0.002)
    await shutdown.close()
    try:
        await pending
        raise AssertionError("shutdown must cancel the active synthesis")
    except asyncio.CancelledError:
        pass
    assert pending.done()
    assert shutdown_tts.cancelled and shutdown.utterance_encoder is None
    assert not (root / "shutdown-temp").exists() and not (root / "shutdown-output").exists()


async def check() -> None:
    with tempfile.TemporaryDirectory(prefix="kei-pk210-") as temp_dir:
        root = Path(temp_dir)
        await check_normal_and_legacy(root / "http")
        await check_missing_and_failures(root / "failures")
        await check_text_degrade_and_partial_cleanup(root / "degrade")
        await check_stream_interruption(root / "interrupt")
        await check_concurrency(root / "concurrency")
        await check_upload_limits(root / "uploads")
        await check_pk200_contract_and_close(root / "pk200")
        await check_stream_protocol(root / "stream")
        await check_http_provider_sanitization()
        await check_synthesize_contract(root / "synthesize")
        await check_synthesize_idempotency_cancel_and_limits(root / "synthesize-lifecycle")


def main() -> int:
    asyncio.run(check())
    print("voice module tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
