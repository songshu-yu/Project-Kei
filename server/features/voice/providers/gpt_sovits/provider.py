"""PK-210 TextToSpeechProvider for an existing local GPT-SoVITS service."""
from __future__ import annotations

import asyncio
import inspect
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar
from urllib.parse import urlparse

import httpx

from ...errors import VoiceError, failed, timed_out, unavailable
from ...models import (
    AudioResult,
    ProviderCapabilities,
    ProviderHealth,
    SynthesisRequest,
    SynthesisTextSegment,
    VoicePackRef,
)
from .descriptor import EngineDescriptor, load_descriptor


_AUDIO_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "application/octet-stream",
    "binary/octet-stream",
}

_API_PY_GENERATION_PARAMETERS = {
    "top_k",
    "top_p",
    "temperature",
    "speed",
    "sample_steps",
    "if_sr",
}
_STYLE_ALIASES = {
    "gptsovits": "auto",
    "legacy": "legacy_v2",
    "api": "api_py",
}
_T = TypeVar("_T")


def _coerce_synthesis_request(value: Any) -> SynthesisRequest | None:
    """Rebuild an installable-module request at the host contract boundary.

    In-process packages are loaded under an isolated module name, so their
    frozen dataclasses are not nominally identical to the host copies even
    when they implement the same reviewed contract.  Accept only the fixed
    public fields and reconstruct trusted host models; arbitrary mappings and
    partially matching objects remain on the legacy call path.
    """

    if isinstance(value, SynthesisRequest):
        return value
    required = (
        "request_id",
        "text",
        "emotion",
        "audio_format",
        "timeout_seconds",
        "segments",
    )
    if any(not hasattr(value, name) for name in required):
        return None
    request_id = getattr(value, "request_id")
    text = getattr(value, "text")
    emotion = getattr(value, "emotion")
    audio_format = getattr(value, "audio_format")
    timeout = getattr(value, "timeout_seconds")
    segments = getattr(value, "segments")
    if (
        not isinstance(request_id, str)
        or not request_id
        or len(request_id) > 256
        or not isinstance(text, str)
        or not isinstance(emotion, str)
        or not emotion
        or len(emotion) > 64
        or not isinstance(audio_format, str)
        or isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or not 0 < float(timeout) <= 600
        or not isinstance(segments, (tuple, list))
        or len(segments) > 512
    ):
        return None
    normalized_segments: list[SynthesisTextSegment] = []
    for segment in segments:
        segment_id = getattr(segment, "segment_id", None)
        sequence = getattr(segment, "sequence", None)
        segment_text = getattr(segment, "text", None)
        if (
            not isinstance(segment_id, str)
            or not segment_id
            or len(segment_id) > 256
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
            or not isinstance(segment_text, str)
        ):
            return None
        normalized_segments.append(
            SynthesisTextSegment(segment_id, sequence, segment_text)
        )
    return SynthesisRequest(
        request_id=request_id,
        text=text,
        emotion=emotion,
        audio_format=audio_format,
        timeout_seconds=float(timeout),
        segments=tuple(normalized_segments),
    )


def _coerce_voice_pack(value: Any) -> VoicePackRef | None:
    if isinstance(value, VoicePackRef):
        return value
    required = ("pack_id", "pack_version", "engine_provider", "handle")
    if any(not hasattr(value, name) for name in required):
        return None
    pack_id = getattr(value, "pack_id")
    version = getattr(value, "pack_version")
    provider = getattr(value, "engine_provider")
    handle = getattr(value, "handle")
    if (
        not isinstance(pack_id, str)
        or not pack_id
        or len(pack_id) > 128
        or not isinstance(version, str)
        or not version
        or len(version) > 128
        or not isinstance(provider, str)
        or not provider
        or len(provider) > 128
        or handle is not None
        and not isinstance(handle, Mapping)
    ):
        return None
    return VoicePackRef(pack_id, version, provider, handle=handle)


def split_text_for_tts(text: str, max_chars: int = 42) -> list[str]:
    text = re.sub(r"\s+", " ", str(text or "").strip())
    if not text:
        return []
    hard_breaks = set("。！？!?；;\n")
    soft_breaks = set("，,、~～…")
    sentences: list[str] = []
    buffer: list[str] = []
    for character in text:
        buffer.append(character)
        if character in hard_breaks:
            part = "".join(buffer).strip()
            if part:
                sentences.append(part)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        sentences.append(tail)
    chunks: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars and not any(character in sentence for character in soft_breaks):
            chunks.append(sentence)
            continue
        buffer = []
        for character in sentence:
            buffer.append(character)
            if len(buffer) >= max_chars or (len(buffer) >= 12 and character in soft_breaks):
                part = "".join(buffer).strip()
                if part:
                    chunks.append(part)
                buffer = []
        tail = "".join(buffer).strip()
        if tail:
            chunks.append(tail)
    return chunks or [text]


def _normalize_style(value: str, descriptor: EngineDescriptor) -> str:
    style = _STYLE_ALIASES.get(str(value or "").strip().lower(), str(value or "").strip().lower())
    if not style:
        style = descriptor.default_api_style
    if style not in descriptor.supported_api_styles:
        raise ValueError("unsupported GPT-SoVITS API style")
    return style


def _loopback_url(host: str, port: int, base_url: str | None) -> str:
    candidate = (base_url or f"http://{host}:{port}").rstrip("/")
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("GPT-SoVITS endpoint must be a local HTTP origin")
    return candidate


@dataclass
class GPTSoVITSConfig:
    host: str = "127.0.0.1"
    port: int = 9880
    base_url: str | None = None
    api_style: str = "gptsovits"
    timeout_seconds: float = 60.0
    text_lang: str = "zh"
    prompt_lang: str = "zh"
    cut_punc: str = "，。！？；：,.!?;"
    ref_audio: dict | None = None
    default_ref_audio: str = ""
    default_ref_text: str = ""

    def __post_init__(self) -> None:
        if not 1 <= int(self.port) <= 65535 or float(self.timeout_seconds) <= 0:
            raise ValueError("invalid GPT-SoVITS port or timeout")
        if self.ref_audio is None:
            self.ref_audio = {}
        _loopback_url(self.host, int(self.port), self.base_url)

    @property
    def api_url(self) -> str:
        return _loopback_url(self.host, int(self.port), self.base_url)


class GPTSoVITSProvider:
    """Stable engine adapter; role assets arrive only through an opaque pack handle."""

    def __init__(
        self,
        config: GPTSoVITSConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        descriptor: EngineDescriptor | None = None,
        voice_pack_resolver: Any | None = None,
    ):
        self.config = config or GPTSoVITSConfig()
        self.descriptor = descriptor or load_descriptor()
        self.api_style = _normalize_style(self.config.api_style, self.descriptor)
        self.client = httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            trust_env=False,
            transport=transport,
        )
        self._available: bool | None = None
        self._active: dict[str, asyncio.Task[Any]] = {}
        self._active_voice_pack: VoicePackRef | None = None
        self._pack_switch_lock = asyncio.Lock()
        self._engine_tasks: set[asyncio.Task[Any]] = set()
        self._engine_state = "unconfigured"
        self._weight_switch_style: str | None = None
        self._voice_pack_resolver = voice_pack_resolver
        self._closing = False
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None

    def set_voice_pack_resolver(self, resolver: Any) -> None:
        self._voice_pack_resolver = resolver

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.descriptor.provider_key,
            operations=("synthesize",),
            audio_formats=self.descriptor.audio_formats,
            streaming=self.descriptor.streaming,
            cancellable=True,
            default_timeout_seconds=self.config.timeout_seconds,
        )

    async def health(self) -> ProviderHealth:
        if self._closing or self._closed:
            return ProviderHealth(False, "closed", error_code="tts_closed")
        if self._engine_state == "unknown":
            return ProviderHealth(False, "unknown", error_code="tts_engine_state_unknown")
        if self._engine_state == "switching":
            return ProviderHealth(False, "switching", error_code="tts_engine_switching")
        started = time.perf_counter()
        try:
            response = await self.client.request(
                self.descriptor.health_method,
                f"{self.config.api_url}{self.descriptor.health_path}",
                timeout=self.descriptor.health_timeout_seconds,
            )
            self._available = response.status_code < 500
        except (httpx.HTTPError, TimeoutError):
            self._available = False
        return ProviderHealth(
            bool(self._available),
            "available" if self._available else "unavailable",
            int((time.perf_counter() - started) * 1000),
            None if self._available else "tts_unavailable",
        )

    async def check_available(self) -> bool:
        return (await self.health()).available

    def _pack_values(self, pack: VoicePackRef, emotion: str) -> dict[str, Any]:
        handle = pack.handle if isinstance(pack.handle, Mapping) else {}
        reference = handle.get("references", {}).get(emotion, {}) if isinstance(handle.get("references"), Mapping) else {}
        if not isinstance(reference, Mapping):
            reference = {}
        configured = (self.config.ref_audio or {}).get(emotion, {})
        if not isinstance(configured, Mapping):
            configured = {}
        return {
            "ref_audio_path": str(
                handle.get("ref_audio_path")
                or reference.get("path")
                or configured.get("path")
                or self.config.default_ref_audio
                or ""
            ),
            "prompt_text": str(
                handle.get("prompt_text")
                or reference.get("text")
                or configured.get("text")
                or self.config.default_ref_text
                or ""
            ),
            "text_lang": str(handle.get("text_lang") or self.config.text_lang),
            "prompt_lang": str(handle.get("prompt_lang") or self.config.prompt_lang),
            "generation_parameters": dict(handle.get("generation_parameters", {}))
            if isinstance(handle.get("generation_parameters"), Mapping) else {},
        }

    def _api_py_payload(self, request: SynthesisRequest, values: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "text": request.text,
            "text_language": values["text_lang"],
            "cut_punc": self.config.cut_punc,
        }
        if values["ref_audio_path"] and values["prompt_text"]:
            payload.update({
                "refer_wav_path": values["ref_audio_path"],
                "prompt_text": values["prompt_text"],
                "prompt_language": values["prompt_lang"],
            })
        generation = values["generation_parameters"]
        for key in _API_PY_GENERATION_PARAMETERS:
            if key in generation:
                payload[key] = generation[key]
        if "speed" not in payload and "speed_factor" in generation:
            payload["speed"] = generation["speed_factor"]
        return payload

    @staticmethod
    def _legacy_payload(request: SynthesisRequest, values: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "text": request.text,
            "text_lang": values["text_lang"],
            "ref_audio_path": values["ref_audio_path"],
            "prompt_text": values["prompt_text"],
            "prompt_lang": values["prompt_lang"],
            "text_split_method": "cut5",
            "media_type": request.audio_format,
        }
        payload.update(values["generation_parameters"])
        return payload

    async def _post(self, endpoint: str, payload: Mapping[str, Any], timeout: float) -> bytes:
        response = await self.client.post(f"{self.config.api_url}{endpoint}", json=dict(payload), timeout=timeout)
        return self._audio_response(response)

    @staticmethod
    def _audio_response(response: httpx.Response) -> bytes:
        response.raise_for_status()
        if not response.content:
            raise ValueError("empty audio response")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type and content_type not in _AUDIO_CONTENT_TYPES:
            raise ValueError("invalid audio response")
        return response.content

    @staticmethod
    def _pack_identity(pack: VoicePackRef | None) -> tuple[str, str] | None:
        return None if pack is None else (pack.pack_id, pack.pack_version)

    def voice_pack_state(self) -> dict[str, Any]:
        """Return a path-free snapshot used to keep Registry resolution honest."""
        identity = self._pack_identity(self._active_voice_pack)
        return {
            "status": "closed" if self._closed or self._closing else self._engine_state,
            "active": None if identity is None else f"{identity[0]}@{identity[1]}",
        }

    @staticmethod
    def _unknown_state_error() -> VoiceError:
        return VoiceError(
            stage="tts",
            code="tts_engine_state_unknown",
            message="语音引擎权重状态未知",
            status_code=503,
            retryable=False,
        )

    async def _set_weights(self, pack: VoicePackRef) -> None:
        if not isinstance(pack.handle, Mapping):
            return
        gpt_path = str(pack.handle.get("gpt_checkpoint_path") or "")
        sovits_path = str(pack.handle.get("sovits_checkpoint_path") or "")
        if not gpt_path and not sovits_path:
            return
        if pack.engine_provider != self.descriptor.provider_key:
            raise failed("tts")
        if not gpt_path or not sovits_path:
            raise failed("tts")

        if self._weight_switch_style != "split":
            combined_response = await self.client.get(
                f"{self.config.api_url}/set_model",
                params={
                    "gpt_model_path": gpt_path,
                    "sovits_model_path": sovits_path,
                },
                timeout=self.config.timeout_seconds,
            )
            if combined_response.status_code not in {404, 405}:
                combined_response.raise_for_status()
                self._weight_switch_style = "combined"
                return
            if self._weight_switch_style == "combined":
                combined_response.raise_for_status()

        gpt_response = await self.client.get(
            f"{self.config.api_url}/set_gpt_weights",
            params={"weights_path": gpt_path},
            timeout=self.config.timeout_seconds,
        )
        gpt_response.raise_for_status()
        sovits_response = await self.client.get(
            f"{self.config.api_url}/set_sovits_weights",
            params={"weights_path": sovits_path},
            timeout=self.config.timeout_seconds,
        )
        sovits_response.raise_for_status()
        self._weight_switch_style = "split"

    async def _restore_previous_locked(self, previous: VoicePackRef | None) -> bool:
        if previous is None:
            self._active_voice_pack = None
            self._engine_state = "unknown"
            self._available = False
            return False
        rollback = asyncio.create_task(self._set_weights(previous))
        cancelled = False
        try:
            while not rollback.done():
                try:
                    await asyncio.shield(rollback)
                except asyncio.CancelledError:
                    # Finish the only rollback attempt before propagating cancellation.
                    cancelled = True
            rollback.result()
        except Exception:
            self._active_voice_pack = None
            self._engine_state = "unknown"
            self._available = False
            if cancelled:
                raise asyncio.CancelledError
            return False
        self._active_voice_pack = previous
        self._engine_state = "ready"
        self._available = True
        if cancelled:
            raise asyncio.CancelledError
        return True

    async def _activate_locked(self, voice_pack: VoicePackRef) -> tuple[bool, VoicePackRef | None]:
        if self._engine_state == "ready" and self._pack_identity(self._active_voice_pack) == self._pack_identity(voice_pack):
            return False, self._active_voice_pack
        previous = self._active_voice_pack if self._engine_state == "ready" else None
        self._engine_state = "switching"
        try:
            await self._set_weights(voice_pack)
        except asyncio.CancelledError:
            await self._restore_previous_locked(previous)
            raise
        except Exception as exc:
            restored = await self._restore_previous_locked(previous)
            if not restored:
                raise self._unknown_state_error() from exc
            raise failed("tts") from exc
        self._active_voice_pack = voice_pack
        self._engine_state = "ready"
        self._available = True
        return True, previous

    async def _run_engine_session(self, operation: Callable[[], Any]) -> Any:
        task = asyncio.current_task()
        if task is not None:
            self._engine_tasks.add(task)
        try:
            async with self._pack_switch_lock:
                if self._closing or self._closed:
                    raise unavailable("tts")
                result = operation()
                return await result if inspect.isawaitable(result) else result
        finally:
            if task is not None:
                self._engine_tasks.discard(task)

    async def activate_voice_pack_transaction(
        self,
        voice_pack: VoicePackRef,
        commit: Callable[[], _T],
    ) -> _T:
        """Switch weights and publish the owning Registry identity in one engine session."""
        async def operation() -> _T:
            changed, previous = await self._activate_locked(voice_pack)
            try:
                result = commit()
                return await result if inspect.isawaitable(result) else result
            except asyncio.CancelledError:
                if changed:
                    await self._restore_previous_locked(previous)
                raise
            except Exception as exc:
                if changed and not await self._restore_previous_locked(previous):
                    raise self._unknown_state_error() from exc
                raise

        return await self._run_engine_session(operation)

    async def activate_voice_pack(self, voice_pack: VoicePackRef) -> None:
        """Atomically apply one validated Pack without publishing a Registry change."""
        await self.activate_voice_pack_transaction(voice_pack, lambda: None)

    async def synthesize(self, request_or_text, voice_pack=None, emotion="calm"):
        request = _coerce_synthesis_request(request_or_text)
        if request is not None:
            pack = _coerce_voice_pack(voice_pack) or VoicePackRef(
                "legacy", "0", self.descriptor.provider_key
            )
            return await self._synthesize_provider(request, pack)
        request = SynthesisRequest(
            request_id=f"legacy-{id(request_or_text)}",
            text=str(request_or_text),
            emotion=str(voice_pack or emotion),
            timeout_seconds=self.config.timeout_seconds,
        )
        try:
            pack = (
                await self._voice_pack_resolver.resolve_active_pack()
                if self._voice_pack_resolver is not None
                else VoicePackRef("legacy", "0", self.descriptor.provider_key)
            )
            result = await self._synthesize_provider(
                request,
                pack,
            )
            return result.audio
        except VoiceError:
            return None

    async def _synthesize_provider(self, request: SynthesisRequest, voice_pack: VoicePackRef) -> AudioResult:
        if self._closing or self._closed:
            raise unavailable("tts")
        if request.audio_format != "wav" or not request.text.strip():
            raise failed("tts")
        task = asyncio.current_task()
        if task:
            self._active[request.request_id] = task
        try:
            async def synthesize_in_session() -> bytes:
                confirmed_pack = voice_pack
                if self._voice_pack_resolver is not None:
                    confirmed_pack = await self._voice_pack_resolver.resolve_active_pack()
                await self._activate_locked(confirmed_pack)
                values = self._pack_values(confirmed_pack, request.emotion)
                if self.api_style == "legacy_v2":
                    return await self._post("/tts", self._legacy_payload(request, values), request.timeout_seconds)
                if self.api_style == "api_py":
                    return await self._post("/", self._api_py_payload(request, values), request.timeout_seconds)
                try:
                    return await self._post("/", self._api_py_payload(request, values), request.timeout_seconds)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
                    return await self._post("/tts", self._legacy_payload(request, values), request.timeout_seconds)

            audio = await self._run_engine_session(synthesize_in_session)
            self._available = True
            return AudioResult(audio=audio, media_type="audio/wav", audio_format="wav")
        except asyncio.CancelledError:
            raise
        except (httpx.TimeoutException, TimeoutError) as exc:
            self._available = False
            raise timed_out("tts") from exc
        except httpx.ConnectError as exc:
            self._available = False
            raise unavailable("tts") from exc
        except VoiceError:
            raise
        except Exception as exc:
            self._available = False
            raise failed("tts") from exc
        finally:
            self._active.pop(request.request_id, None)

    async def synthesize_to_file(self, text, path, emotion="calm") -> bool:
        audio = await self.synthesize(text, emotion)
        if audio:
            Path(path).write_bytes(audio)
            return True
        return False

    async def cancel(self, request_id: str) -> None:
        task = self._active.get(request_id)
        if task and task is not asyncio.current_task():
            task.cancel()

    async def _close_impl(self) -> None:
        current = asyncio.current_task()
        for task in list(self._engine_tasks):
            if task is not current:
                task.cancel()
        async with self._pack_switch_lock:
            self._closed = True
            self._active_voice_pack = None
            self._engine_state = "closed"
            self._available = False
            await self.client.aclose()

    async def close(self) -> None:
        if self._close_task is None:
            self._closing = True
            self._close_task = asyncio.create_task(self._close_impl())
        close_task = self._close_task
        cancelled = False
        while not close_task.done():
            try:
                await asyncio.shield(close_task)
            except asyncio.CancelledError:
                cancelled = True
        await close_task
        if cancelled:
            raise asyncio.CancelledError


# Compatibility names retained for existing imports and local configuration.
TTSClient = GPTSoVITSProvider
TTSConfig = GPTSoVITSConfig

__all__ = [
    "GPTSoVITSConfig",
    "GPTSoVITSProvider",
    "TTSClient",
    "TTSConfig",
    "split_text_for_tts",
]
