"""Structural PK-210 adapter owned and distributed by daily briefing."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class BriefingSynthesisRequest:
    """Minimum structural request accepted by a public TTS provider."""

    request_id: str
    text: str
    emotion: str = "calm"
    audio_format: str = "wav"
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class _VoiceCapabilities:
    tts: Any
    voice_packs: Any
    artifacts: Any
    request_factory: Any = None


def _callable_method(value: Any, name: str) -> bool:
    return callable(getattr(value, name, None))


def _safe_failure(code: str = "voice_failed") -> Dict[str, Any]:
    return {
        "audio_available": False,
        "audio_path": "",
        "mode": "text_only",
        "degraded": True,
        "errors": [{
            "stage": "tts",
            "code": code,
            "message": "播报语音不可用，已返回文本",
        }],
    }


class PK210BriefingVoiceProvider:
    """Adapt structural TTS, VoicePack and artifact capabilities.

    The adapter intentionally imports no PK-210 or PK-212 implementation. A
    capability snapshot is supplied per request, so replacement cannot mix
    providers or artifact stores inside one narration.
    """

    def __init__(
        self,
        tts: Any,
        voice_packs: Any,
        artifacts: Any,
        *,
        request_factory: Any = None,
        timeout_seconds: float = 60.0,
        max_audio_bytes: int = 32 * 1024 * 1024,
        audio_url_prefix: str = "/api/v1/voice/audio",
    ):
        self.tts = tts
        self.voice_packs = voice_packs
        self.artifacts = artifacts
        self.request_factory = request_factory
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.max_audio_bytes = max(1, int(max_audio_bytes))
        self.audio_url_prefix = audio_url_prefix.rstrip("/")

    def _request(self, request_id: str, narration: str) -> Any:
        factory = self.request_factory
        if factory is None:
            factory = BriefingSynthesisRequest
        if not callable(factory):
            raise TypeError("invalid synthesis request factory")
        return factory(
            request_id=request_id,
            text=narration,
            emotion="calm",
            audio_format="wav",
            timeout_seconds=self.timeout_seconds,
        )

    async def _cancel(self, request_id: str) -> None:
        for provider in (self.tts, self.voice_packs):
            cancel = getattr(provider, "cancel", None)
            if callable(cancel):
                try:
                    await cancel(request_id)
                except Exception:
                    pass

    async def synthesize_briefing(
        self,
        text: str,
        *,
        local_date: str,
    ) -> Dict[str, Any]:
        del local_date
        narration = str(text or "").strip()
        if not narration:
            return _safe_failure("empty_narration")
        if (
            not _callable_method(self.tts, "synthesize")
            or not _callable_method(self.voice_packs, "resolve_active_pack")
            or not _callable_method(self.artifacts, "session")
        ):
            return _safe_failure("voice_unavailable")
        request_id = uuid.uuid4().hex
        try:
            voice_pack = await asyncio.wait_for(
                self.voice_packs.resolve_active_pack(),
                timeout=self.timeout_seconds,
            )
            audio_result = await asyncio.wait_for(
                self.tts.synthesize(
                    self._request(request_id, narration),
                    voice_pack,
                ),
                timeout=self.timeout_seconds,
            )
            audio = (
                audio_result
                if isinstance(audio_result, bytes)
                else getattr(audio_result, "audio", None)
            )
            if (
                not isinstance(audio, bytes)
                or not audio
                or len(audio) > self.max_audio_bytes
            ):
                raise ValueError("invalid audio result")
            with self.artifacts.session(request_id) as session:
                filename = session.publish(audio, index=1)
                if (
                    not isinstance(filename, str)
                    or Path(filename).name != filename
                    or not filename.lower().endswith(".wav")
                    or len(filename) > 180
                ):
                    raise ValueError("invalid audio reference")
                session.commit()
            return {
                "audio_available": True,
                "audio_path": f"{self.audio_url_prefix}/{filename}",
                "mode": "audio",
                "degraded": False,
                "errors": [],
            }
        except asyncio.CancelledError:
            await self._cancel(request_id)
            raise
        except Exception:
            await self._cancel(request_id)
            return _safe_failure()


class AppStateBriefingVoiceProvider:
    """Resolve the host's current public voice capabilities per request."""

    def __init__(
        self,
        app: Any,
        *,
        timeout_seconds: float = 60.0,
        max_audio_bytes: int = 32 * 1024 * 1024,
        audio_url_prefix: str = "/api/v1/voice/audio",
    ) -> None:
        self.app = app
        self.timeout_seconds = timeout_seconds
        self.max_audio_bytes = max_audio_bytes
        self.audio_url_prefix = audio_url_prefix

    def _capabilities(self) -> Optional[_VoiceCapabilities]:
        state = self.app.state
        service = getattr(state, "voice_service", None)
        tts = getattr(state, "voice_tts_provider", None)
        voice_packs = getattr(state, "voice_pack_resolver_binding", None)
        artifacts = getattr(state, "voice_artifact_store", None)
        request_factory = getattr(
            state,
            "voice_synthesis_request_factory",
            None,
        )
        if service is not None:
            tts = tts or getattr(service, "tts", None)
            voice_packs = voice_packs or getattr(service, "voice_packs", None)
            artifacts = artifacts or getattr(service, "artifacts", None)
        if (
            not _callable_method(tts, "synthesize")
            or not _callable_method(voice_packs, "resolve_active_pack")
            or not _callable_method(artifacts, "session")
        ):
            return None
        return _VoiceCapabilities(
            tts=tts,
            voice_packs=voice_packs,
            artifacts=artifacts,
            request_factory=request_factory,
        )

    async def synthesize_briefing(
        self,
        text: str,
        *,
        local_date: str,
    ) -> Dict[str, Any]:
        capabilities = self._capabilities()
        if capabilities is None:
            return _safe_failure("voice_unavailable")
        provider = PK210BriefingVoiceProvider(
            capabilities.tts,
            capabilities.voice_packs,
            capabilities.artifacts,
            request_factory=capabilities.request_factory,
            timeout_seconds=self.timeout_seconds,
            max_audio_bytes=self.max_audio_bytes,
            audio_url_prefix=self.audio_url_prefix,
        )
        return await provider.synthesize_briefing(
            text,
            local_date=local_date,
        )


__all__ = [
    "AppStateBriefingVoiceProvider",
    "BriefingSynthesisRequest",
    "PK210BriefingVoiceProvider",
]
