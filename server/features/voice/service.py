"""ASR -> PK-200 conversation -> TTS orchestration and artifact lifecycle."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

from .contracts import (
    ConversationProvider,
    SpeechToTextProvider,
    TextToSpeechProvider,
    UtteranceEncoder,
    VoicePackResolver,
)
from .errors import VoiceError, VoiceRequestCancelled, failed, timed_out, unavailable
from .media import (
    DEFAULT_MAX_DURATION_SECONDS,
    DEFAULT_MAX_OUTPUT_BYTES,
    OUTPUT_MEDIA_TYPE,
    OUTPUT_PROFILE,
    PcmUtterancePipeline,
    SynthesisMediaError,
)
from .models import (
    AudioResult,
    PublishedAudio,
    SynthesisRequest,
    SynthesisTextSegment,
    SynthesizedUtterance,
    Transcript,
    TranscriptionRequest,
    VoiceDraft,
    VoiceRequest,
    VoiceResult,
    UtteranceEncodingRequest,
)
from .storage import VoiceArtifactStore
from .text import normalize_voice_text, split_text_for_tts


DisconnectCheck = Callable[[], Awaitable[bool]]


@dataclass
class _IdempotencyRecord:
    fingerprint: str
    task: asyncio.Task[SynthesizedUtterance]
    expires_at: float
    waiters: int = 0


class VoiceService:
    def __init__(
        self,
        *,
        asr: SpeechToTextProvider | None,
        conversation: ConversationProvider | None,
        tts: TextToSpeechProvider | None,
        voice_packs: VoicePackResolver | None,
        utterance_encoder: UtteranceEncoder | None = None,
        utterance_pipeline: PcmUtterancePipeline | None = None,
        artifacts: VoiceArtifactStore,
        asr_timeout_seconds: float = 180.0,
        conversation_timeout_seconds: float = 120.0,
        tts_timeout_seconds: float = 60.0,
        health_timeout_seconds: float = 5.0,
        max_audio_bytes: int = 16 * 1024 * 1024,
        max_synthesized_bytes: int = 32 * 1024 * 1024,
        encoding_timeout_seconds: float = 30.0,
        idempotency_ttl_seconds: float = 300.0,
        max_idempotency_records: int = 8,
    ):
        self.asr = asr
        self.conversation = conversation
        self.tts = tts
        self.voice_packs = voice_packs
        self.utterance_encoder = utterance_encoder
        self.utterance_pipeline = utterance_pipeline or PcmUtterancePipeline()
        self.artifacts = artifacts
        self.asr_timeout_seconds = asr_timeout_seconds
        self.conversation_timeout_seconds = conversation_timeout_seconds
        self.tts_timeout_seconds = tts_timeout_seconds
        self.health_timeout_seconds = health_timeout_seconds
        self.max_audio_bytes = max_audio_bytes
        self.max_synthesized_bytes = max_synthesized_bytes
        self.encoding_timeout_seconds = encoding_timeout_seconds
        self.idempotency_ttl_seconds = idempotency_ttl_seconds
        self.max_idempotency_records = max_idempotency_records
        self._closed = False
        self._idempotency_lock = threading.RLock()
        self._idempotency: dict[str, _IdempotencyRecord] = {}
        self._active_synthesis: set[asyncio.Task[Any]] = set()

    async def health(self) -> dict:
        async def inspect(provider, stage: str) -> dict:
            if provider is None:
                return {"health": unavailable(stage).to_public_dict(), "capabilities": None}
            try:
                health = await asyncio.wait_for(provider.health(), timeout=self.health_timeout_seconds)
                capabilities = provider.capabilities()
                return {"health": health.to_dict(), "capabilities": capabilities.to_dict()}
            except asyncio.TimeoutError:
                return {"health": timed_out(stage).to_public_dict(), "capabilities": None}
            except Exception:
                return {"health": failed(stage).to_public_dict(), "capabilities": None}

        providers = {
            "asr": await inspect(self.asr, "asr"),
            "conversation": await inspect(self.conversation, "conversation"),
            "tts": await inspect(self.tts, "tts"),
            "voice_pack": await inspect(self.voice_packs, "voice_pack"),
            "utterance_encoder": await inspect(self.utterance_encoder, "utterance_encoder"),
        }
        required_ready = all(
            providers[name]["health"].get("available") is True
            for name in ("asr", "conversation")
        )
        profile_ready = all(
            providers[name]["health"].get("available") is True
            for name in ("tts", "voice_pack", "utterance_encoder")
        )
        encoder_capabilities = providers["utterance_encoder"].get("capabilities") or {}
        profile_ready = profile_ready and (
            "encode" in encoder_capabilities.get("operations", ())
            and OUTPUT_PROFILE in encoder_capabilities.get("audio_formats", ())
        )
        return {
            "status": "ready" if required_ready else "degraded",
            "providers": providers,
            "synthesis_profiles": {
                OUTPUT_PROFILE: {
                    "available": profile_ready,
                    "content_type": OUTPUT_MEDIA_TYPE,
                    "final": True,
                    "max_bytes": DEFAULT_MAX_OUTPUT_BYTES,
                    "max_duration_seconds": DEFAULT_MAX_DURATION_SECONDS,
                }
            },
        }

    async def _with_timeout(self, awaitable, timeout: float, stage: str):
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise timed_out(stage) from exc
        except VoiceError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise failed(stage) from exc

    def _validate(self, request: VoiceRequest) -> None:
        if self._closed:
            raise VoiceError(stage="request", code="voice_closed", message="语音服务已关闭", status_code=503)
        if not request.audio:
            raise VoiceError(stage="upload", code="audio_empty", message="上传音频为空", status_code=422)
        if len(request.audio) > self.max_audio_bytes:
            raise VoiceError(stage="upload", code="audio_too_large", message="上传音频超过大小限制", status_code=413)

    async def _draft(self, request: VoiceRequest, request_id: str) -> VoiceDraft:
        self._validate(request)
        if self.asr is None:
            raise unavailable("asr")
        if self.conversation is None:
            raise unavailable("conversation")
        started = time.perf_counter()
        transcript: Transcript = await self._with_timeout(
            self.asr.transcribe(TranscriptionRequest(
                request_id=request_id,
                audio=request.audio,
                filename=request.filename,
                media_type=request.media_type,
                language=request.language,
                vad_filter=request.vad_filter,
                timeout_seconds=self.asr_timeout_seconds,
            )),
            self.asr_timeout_seconds,
            "asr",
        )
        after_asr = time.perf_counter()
        user_text = normalize_voice_text(transcript.text)
        if not user_text:
            raise VoiceError(
                stage="asr",
                code="asr_empty_transcript",
                message="没有识别到可提交的语音文字",
                status_code=422,
            )
        if len(user_text) > 20_000:
            raise VoiceError(
                stage="asr",
                code="asr_transcript_too_large",
                message="识别文字超过对话输入限制",
                status_code=422,
            )
        reply = await self._with_timeout(
            self.conversation.chat(user_text, request_id=request_id),
            self.conversation_timeout_seconds,
            "conversation",
        )
        after_conversation = time.perf_counter()
        return VoiceDraft(
            request_id=request_id,
            user_text=user_text,
            assistant_text=reply.text,
            emotion=reply.emotion,
            timestamp=reply.timestamp,
            timings_ms={
                "asr": int((after_asr - started) * 1000),
                "llm": int((after_conversation - after_asr) * 1000),
            },
            asr_segments=transcript.segments,
            asr_language=transcript.language,
            asr_language_probability=transcript.language_probability,
        )

    async def _synthesize_all(self, draft: VoiceDraft, split_tts: bool) -> tuple[list[tuple[str, AudioResult, int]], list[dict]]:
        if self.tts is None:
            return [], [unavailable("tts").to_public_dict()]
        if self.voice_packs is None:
            return [], [unavailable("voice_pack").to_public_dict()]
        try:
            voice_pack = await self._with_timeout(
                self.voice_packs.resolve_active_pack(),
                self.tts_timeout_seconds,
                "voice_pack",
            )
            parts = split_text_for_tts(draft.assistant_text) if split_tts else [draft.assistant_text]
            generated: list[tuple[str, AudioResult, int]] = []
            total_bytes = 0
            for text in parts:
                started = time.perf_counter()
                result: AudioResult = await self._with_timeout(
                    self.tts.synthesize(SynthesisRequest(
                        request_id=draft.request_id,
                        text=text,
                        emotion=draft.emotion,
                        timeout_seconds=self.tts_timeout_seconds,
                    ), voice_pack),
                    self.tts_timeout_seconds,
                    "tts",
                )
                total_bytes += len(result.audio)
                if not result.audio or total_bytes > self.max_synthesized_bytes:
                    raise VoiceError(stage="tts", code="tts_invalid_audio", message="语音合成结果无效", status_code=502)
                generated.append((text, result, int((time.perf_counter() - started) * 1000)))
            return generated, []
        except VoiceError as exc:
            return [], [exc.to_public_dict()]

    async def _cancel(self, request_id: str) -> None:
        for provider in (self.asr, self.conversation, self.tts, self.voice_packs):
            if provider is not None:
                try:
                    await provider.cancel(request_id)
                except Exception:
                    pass

    @staticmethod
    def _synthesis_segments(text: str) -> tuple[SynthesisTextSegment, ...]:
        parts = split_text_for_tts(text)
        return tuple(
            SynthesisTextSegment(f"segment-{index:04d}", index - 1, part)
            for index, part in enumerate(parts, start=1)
        )

    async def _cancel_synthesis_providers(
        self,
        request_id: str,
        providers: tuple[Any, ...],
    ) -> None:
        for provider in providers:
            if provider is not None:
                try:
                    await provider.cancel(request_id)
                except Exception:
                    pass

    async def _synthesize_text_once(
        self,
        *,
        text: str,
        utterance_id: str,
    ) -> SynthesizedUtterance:
        if self._closed:
            raise SynthesisMediaError("voice_unavailable", 503)
        tts = self.tts
        voice_packs = self.voice_packs
        encoder = self.utterance_encoder
        if tts is None:
            raise SynthesisMediaError("voice_unavailable", 503)
        if voice_packs is None:
            raise SynthesisMediaError("voice_pack_unavailable", 503)
        if encoder is None:
            raise SynthesisMediaError("encoding_unavailable", 503)
        request_id = uuid.uuid4().hex
        providers = (tts, voice_packs, encoder)
        try:
            try:
                encoder_health = await asyncio.wait_for(
                    encoder.health(),
                    timeout=self.health_timeout_seconds,
                )
                encoder_capabilities = encoder.capabilities()
                if (
                    encoder_health.available is not True
                    or "encode" not in encoder_capabilities.operations
                    or OUTPUT_PROFILE not in encoder_capabilities.audio_formats
                ):
                    raise SynthesisMediaError("encoding_unavailable", 503)
            except SynthesisMediaError:
                raise
            except Exception as exc:
                raise SynthesisMediaError("encoding_unavailable", 503) from exc
            try:
                voice_pack = await asyncio.wait_for(
                    voice_packs.resolve_active_pack(),
                    timeout=self.tts_timeout_seconds,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise SynthesisMediaError("voice_pack_unavailable", 503) from exc
            segments = self._synthesis_segments(text)
            if not segments:
                raise SynthesisMediaError("audio_invalid", 422)
            try:
                result = await asyncio.wait_for(
                    tts.synthesize(
                        SynthesisRequest(
                            request_id=request_id,
                            text=text,
                            emotion="calm",
                            audio_format="wav",
                            timeout_seconds=self.tts_timeout_seconds,
                            segments=segments,
                        ),
                        voice_pack,
                    ),
                    timeout=self.tts_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise SynthesisMediaError("tts_timeout", 504) from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise SynthesisMediaError("tts_failed", 502) from exc
            if (
                not isinstance(getattr(result, "audio", None), (bytes, bytearray))
                or not isinstance(getattr(result, "segments", ()), (tuple, list))
            ):
                raise SynthesisMediaError("audio_invalid", 502)
            pcm = self.utterance_pipeline.prepare(result, segments)
            try:
                encoded = await asyncio.wait_for(
                    encoder.encode(UtteranceEncodingRequest(
                        request_id=request_id,
                        utterance_id=utterance_id,
                        output_profile=OUTPUT_PROFILE,
                        pcm_s16le=pcm.pcm_s16le,
                        sample_rate=pcm.sample_rate,
                        channels=pcm.channels,
                        sample_width=pcm.sample_width,
                        timeout_seconds=self.encoding_timeout_seconds,
                    )),
                    timeout=self.encoding_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise SynthesisMediaError("encoding_unavailable", 503) from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise SynthesisMediaError("encoding_unavailable", 503) from exc
            try:
                return self.utterance_pipeline.finalize(
                    encoded,
                    pcm,
                    utterance_id=utterance_id,
                )
            except SynthesisMediaError as exc:
                if exc.code == "audio_invalid":
                    raise SynthesisMediaError("encoding_unavailable", 503) from exc
                raise
        except asyncio.CancelledError:
            await self._cancel_synthesis_providers(request_id, providers)
            raise

    async def _await_synthesis_task(
        self,
        task: asyncio.Task[SynthesizedUtterance],
        disconnected: DisconnectCheck | None,
    ) -> SynthesizedUtterance:
        while True:
            done, _pending = await asyncio.wait({task}, timeout=0.05)
            if done:
                return await asyncio.shield(task)
            if disconnected is not None and await disconnected():
                raise VoiceRequestCancelled()

    def _new_synthesis_task(self, text: str, utterance_id: str) -> asyncio.Task[SynthesizedUtterance]:
        task = asyncio.create_task(
            self._synthesize_text_once(text=text, utterance_id=utterance_id)
        )
        self._active_synthesis.add(task)
        task.add_done_callback(self._active_synthesis.discard)
        return task

    async def synthesize_text(
        self,
        *,
        purpose: str,
        text: str,
        idempotency_key: str | None,
        disconnected: DisconnectCheck | None = None,
    ) -> SynthesizedUtterance:
        if self._closed or purpose != "qq_reply":
            raise SynthesisMediaError("voice_unavailable", 503)
        fingerprint = hashlib.sha256(
            (purpose + "\0" + text).encode("utf-8")
        ).hexdigest()
        if idempotency_key is None:
            task = self._new_synthesis_task(text, uuid.uuid4().hex)
            try:
                return await self._await_synthesis_task(task, disconnected)
            except (VoiceRequestCancelled, asyncio.CancelledError):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise

        now = time.monotonic()
        with self._idempotency_lock:
            for key, item in list(self._idempotency.items()):
                if item.expires_at <= now and item.task.done():
                    self._idempotency.pop(key, None)
            record = self._idempotency.get(idempotency_key)
            if record is not None and record.fingerprint != fingerprint:
                raise SynthesisMediaError("idempotency_conflict", 409)
            if record is None:
                if len(self._idempotency) >= self.max_idempotency_records:
                    completed = next(
                        (key for key, item in self._idempotency.items() if item.task.done()),
                        None,
                    )
                    if completed is None:
                        raise SynthesisMediaError("voice_unavailable", 503)
                    self._idempotency.pop(completed, None)
                record = _IdempotencyRecord(
                    fingerprint=fingerprint,
                    task=self._new_synthesis_task(text, uuid.uuid4().hex),
                    expires_at=now + self.idempotency_ttl_seconds,
                )
                self._idempotency[idempotency_key] = record
            record.waiters += 1
        cancel_task = False
        try:
            return await self._await_synthesis_task(record.task, disconnected)
        finally:
            with self._idempotency_lock:
                record.waiters = max(0, record.waiters - 1)
                cancel_task = record.waiters == 0 and not record.task.done()
            if cancel_task:
                record.task.cancel()
                await asyncio.gather(record.task, return_exceptions=True)
                with self._idempotency_lock:
                    if self._idempotency.get(idempotency_key) is record:
                        self._idempotency.pop(idempotency_key, None)

    async def chat(self, request: VoiceRequest) -> VoiceResult:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            with self.artifacts.session(request_id) as session:
                draft = await self._draft(request, request_id)
                tts_started = time.perf_counter()
                synthesized, errors = await self._synthesize_all(draft, request.split_tts)
                published: list[PublishedAudio] = []
                for index, (text, result, elapsed_ms) in enumerate(synthesized, start=1):
                    filename = session.publish(result.audio, index=index)
                    published.append(PublishedAudio(filename, text, index, len(synthesized), elapsed_ms))
                encoded = ""
                if request.include_audio_base64 and synthesized:
                    encoded = base64.b64encode(synthesized[0][1].audio).decode("ascii")
                session.commit()
                finished = time.perf_counter()
                return VoiceResult(
                    draft=draft,
                    audio=published,
                    audio_base64=encoded,
                    timings_ms={
                        **draft.timings_ms,
                        "tts": int((finished - tts_started) * 1000),
                        "total": int((finished - started) * 1000),
                    },
                    mode="audio" if published else "text_only",
                    degraded=bool(errors),
                    errors=errors,
                )
        except asyncio.CancelledError:
            await self._cancel(request_id)
            raise

    async def stream(
        self,
        request: VoiceRequest,
        *,
        disconnected: DisconnectCheck | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        session = self.artifacts.session(request_id)
        session.__enter__()
        terminal = False

        async def ensure_connected() -> None:
            if disconnected is not None and await disconnected():
                raise VoiceRequestCancelled()

        try:
            await ensure_connected()
            draft = await self._draft(request, request_id)
            yield {
                "event": "reply",
                "user_text": draft.user_text,
                "assistant_text": draft.assistant_text,
                "emotion": draft.emotion,
                "timestamp": draft.timestamp,
                "timings_ms": draft.timings_ms,
                "asr_segments": draft.asr_segments,
                "asr_language": draft.asr_language,
                "asr_language_probability": draft.asr_language_probability,
            }
            await ensure_connected()
            tts_started = time.perf_counter()
            synthesized, errors = await self._synthesize_all(draft, request.split_tts)
            published: list[PublishedAudio] = []
            for index, (text, result, elapsed_ms) in enumerate(synthesized, start=1):
                filename = session.publish(result.audio, index=index)
                published.append(PublishedAudio(filename, text, index, len(synthesized), elapsed_ms))
            for item in published:
                await ensure_connected()
                yield {
                    "event": "audio_part",
                    "audio_filename": item.filename,
                    "index": item.index,
                    "total": item.total,
                    "text": item.text,
                    "elapsed_ms": item.elapsed_ms,
                    "saved": True,
                }
            await ensure_connected()
            finished = time.perf_counter()
            session.commit()
            terminal = True
            yield {
                "event": "done",
                "audio_filenames": [item.filename for item in published],
                "audio_available": bool(published),
                "mode": "audio" if published else "text_only",
                "degraded": bool(errors),
                "errors": errors,
                "timings_ms": {
                    **draft.timings_ms,
                    "tts": int((finished - tts_started) * 1000),
                    "total": int((finished - started) * 1000),
                },
            }
        except VoiceRequestCancelled:
            await self._cancel(request_id)
        except asyncio.CancelledError:
            await self._cancel(request_id)
            raise
        except VoiceError as exc:
            if not terminal:
                terminal = True
                yield {"event": "error", "error": exc.to_public_dict()}
        except Exception:
            if not terminal:
                terminal = True
                yield {"event": "error", "error": failed("voice").to_public_dict()}
        finally:
            session.cleanup()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        active = tuple(self._active_synthesis)
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        with self._idempotency_lock:
            self._idempotency.clear()
        providers = (
            self.asr,
            self.conversation,
            self.tts,
            self.voice_packs,
            self.utterance_encoder,
        )
        self.asr = None
        self.conversation = None
        self.tts = None
        self.voice_packs = None
        self.utterance_encoder = None
        for provider in providers:
            if provider is not None:
                try:
                    await provider.close()
                except Exception:
                    pass
