"""HTTP adapter for the existing faster-whisper service on port 8010."""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from ..errors import VoiceError, failed, timed_out, unavailable
from ..models import ProviderCapabilities, ProviderHealth, Transcript, TranscriptionRequest


@dataclass
class ASRConfig:
    url: str = "http://127.0.0.1:8010/asr/transcribe"
    language: str = "zh"
    timeout_seconds: float = 180.0
    initial_prompt: str = ""
    postprocess: bool = True


@dataclass
class ASRResult:
    text: str
    language: str
    language_probability: float
    duration: float
    segments: List[Dict[str, Any]]
    raw: Dict[str, Any]


class ASRClient:
    def __init__(self, config: Optional[ASRConfig] = None, *, transport=None):
        self.config = config or ASRConfig()
        self.client = httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            trust_env=False,
            transport=transport,
        )
        self._active: dict[str, asyncio.Task] = {}
        self._closed = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="faster-whisper-http",
            operations=("transcribe",),
            audio_formats=("wav", "mp3", "m4a", "flac", "ogg", "webm"),
            default_timeout_seconds=self.config.timeout_seconds,
        )

    @staticmethod
    def _finite_number(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) else default

    @classmethod
    def _normalize_segments(cls, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("invalid segments")
        normalized: List[Dict[str, Any]] = []
        for item in value[:1000]:
            if not isinstance(item, dict):
                continue
            normalized.append({
                "start": max(0.0, cls._finite_number(item.get("start"))),
                "end": max(0.0, cls._finite_number(item.get("end"))),
                "text": str(item.get("text", ""))[:4000],
            })
        return normalized

    async def health(self) -> ProviderHealth:
        if self._closed:
            return ProviderHealth(False, "closed", error_code="asr_closed")
        started = time.perf_counter()
        try:
            response = await self.client.get(self.config.url.rsplit("/asr/transcribe", 1)[0] + "/docs", timeout=3.0)
            return ProviderHealth(response.status_code < 500, "available", int((time.perf_counter() - started) * 1000))
        except Exception:
            return ProviderHealth(False, "unavailable", error_code="asr_unavailable")

    async def transcribe(self, request: TranscriptionRequest) -> Transcript:
        if self._closed:
            raise unavailable("asr")
        task = asyncio.current_task()
        if task:
            self._active[request.request_id] = task
        files = {"file": (request.filename, request.audio, request.media_type)}
        data = {
            "language": request.language or self.config.language,
            "vad_filter": "true" if request.vad_filter else "false",
            "postprocess": "true" if self.config.postprocess else "false",
        }
        if self.config.initial_prompt:
            data["initial_prompt"] = self.config.initial_prompt
        try:
            response = await self.client.post(self.config.url, files=files, data=data, timeout=request.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("invalid payload")
            segments = self._normalize_segments(payload.get("segments", []))
            return Transcript(
                text=str(payload.get("text", "")),
                language=str(payload.get("language", "")),
                language_probability=max(0.0, min(1.0, self._finite_number(payload.get("language_probability")))),
                duration=max(0.0, self._finite_number(payload.get("duration"))),
                segments=segments,
            )
        except asyncio.CancelledError:
            raise
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise timed_out("asr") from exc
        except httpx.ConnectError as exc:
            raise unavailable("asr") from exc
        except VoiceError:
            raise
        except Exception as exc:
            raise failed("asr") from exc
        finally:
            self._active.pop(request.request_id, None)

    async def transcribe_bytes(
        self,
        audio: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
        vad_filter: bool = False,
    ) -> ASRResult:
        request_id = f"legacy-{id(audio)}"
        result = await self.transcribe(TranscriptionRequest(
            request_id=request_id,
            audio=audio,
            filename=Path(filename).name or "audio.wav",
            media_type="application/octet-stream",
            language=language or self.config.language,
            vad_filter=vad_filter,
            timeout_seconds=self.config.timeout_seconds,
        ))
        raw = {
            "text": result.text,
            "language": result.language,
            "language_probability": result.language_probability,
            "duration": result.duration,
            "segments": result.segments,
        }
        return ASRResult(**raw, raw=raw)

    async def transcribe_file(self, path: Union[str, Path], language: Optional[str] = None, vad_filter: bool = False) -> ASRResult:
        audio_path = Path(path)
        return await self.transcribe_bytes(audio_path.read_bytes(), audio_path.name, language, vad_filter)

    async def cancel(self, request_id: str) -> None:
        task = self._active.get(request_id)
        if task and task is not asyncio.current_task():
            task.cancel()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in list(self._active.values()):
            if task is not asyncio.current_task():
                task.cancel()
        await self.client.aclose()


__all__ = ["ASRClient", "ASRConfig", "ASRResult"]
