"""Versioned and legacy HTTP routes backed by one VoiceService."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from core.local_access import is_loopback_host, is_trusted_local_origin

from .errors import VoiceError
from .media import SynthesisMediaError, duration_milliseconds
from .models import VoiceChatResponse, VoiceRequest
from .service import VoiceService


DEFAULT_MAX_UPLOAD_BYTES = 16 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
MAX_SYNTHESIS_JSON_BYTES = 8 * 1024
MAX_SYNTHESIS_TEXT_CHARS = 1500
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/x-m4a",
    "audio/flac", "audio/ogg", "application/ogg", "audio/webm", "application/octet-stream",
}
ALLOWED_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}


ServiceProvider = Callable[[], Optional[VoiceService]]
RequestGuard = Callable[[Request], bool]


def _request_origin(request: Request) -> str | None:
    values = request.headers.getlist("origin")
    return values[0] if len(values) == 1 else (None if not values else "")


def _default_synthesis_guard(request: Request) -> bool:
    client = request.client
    return (
        client is not None
        and is_loopback_host(client.host)
        and is_trusted_local_origin(_request_origin(request))
    )


class _DuplicateJsonKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey()
        result[key] = value
    return result


async def _read_synthesis_request(request: Request) -> tuple[str, str]:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise SynthesisMediaError("invalid_request", 415)
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_SYNTHESIS_JSON_BYTES:
            raise SynthesisMediaError("invalid_request", 413)
        chunks.append(chunk)
    try:
        payload = json.loads(
            b"".join(chunks).decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SynthesisMediaError("invalid_request", 422) from exc
    if not isinstance(payload, dict) or set(payload) != {"purpose", "text"}:
        raise SynthesisMediaError("invalid_request", 422)
    purpose = payload.get("purpose")
    text = payload.get("text")
    if purpose != "qq_reply" or not isinstance(text, str):
        raise SynthesisMediaError("invalid_request", 422)
    normalized = text.strip()
    if (
        not normalized
        or len(normalized) > MAX_SYNTHESIS_TEXT_CHARS
        or any(unicodedata.category(character).startswith("C") for character in normalized)
    ):
        raise SynthesisMediaError("invalid_request", 422)
    return purpose, normalized


def _idempotency_key(request: Request) -> str | None:
    values = request.headers.getlist("idempotency-key")
    if not values:
        return None
    if len(values) != 1 or _request_origin(request) is not None:
        raise SynthesisMediaError("invalid_request", 422)
    value = values[0]
    if not IDEMPOTENCY_KEY.fullmatch(value):
        raise SynthesisMediaError("invalid_request", 422)
    return value


def _safe_filename(value: str | None) -> str:
    normalized = str(value or "audio.wav").replace("\\", "/").rsplit("/", 1)[-1]
    return normalized[:180] or "audio.wav"


async def read_limited_audio(upload: UploadFile, max_bytes: int) -> tuple[bytes, str, str]:
    filename = _safe_filename(upload.filename)
    suffix = Path(filename).suffix.lower()
    media_type = str(upload.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_AUDIO_TYPES or suffix not in ALLOWED_AUDIO_SUFFIXES:
        await upload.close()
        raise VoiceError(stage="upload", code="audio_type_not_allowed", message="不支持的音频类型", status_code=415)
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = await upload.read(min(READ_CHUNK_BYTES, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise VoiceError(stage="upload", code="audio_too_large", message="上传音频超过大小限制", status_code=413)
            chunks.append(chunk)
    finally:
        await upload.close()
    if total == 0:
        raise VoiceError(stage="upload", code="audio_empty", message="上传音频为空", status_code=422)
    return b"".join(chunks), filename, media_type


def create_voice_router(
    service_provider: ServiceProvider,
    *,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    synthesis_guard: RequestGuard = _default_synthesis_guard,
) -> APIRouter:
    router = APIRouter(tags=["voice"])

    def service() -> VoiceService:
        value = service_provider()
        if value is None:
            raise HTTPException(status_code=503, detail=VoiceError(stage="voice", code="voice_unavailable", message="语音服务尚未启动", status_code=503).to_public_dict())
        return value

    def audio_prefix(request: Request) -> str:
        return "/api/v1/voice/audio" if request.url.path.startswith("/api/v1/") else "/voice/audio"

    @router.get("/api/v1/voice/health")
    @router.get("/voice/health", include_in_schema=False)
    async def voice_health():
        return await service().health()

    @router.post("/api/v1/voice/synthesize")
    async def synthesize_voice(request: Request):
        if not synthesis_guard(request):
            return JSONResponse({"code": "voice_forbidden"}, status_code=403)
        try:
            purpose, text = await _read_synthesis_request(request)
            idempotency_key = _idempotency_key(request)
            result = await service().synthesize_text(
                purpose=purpose,
                text=text,
                idempotency_key=idempotency_key,
                disconnected=request.is_disconnected,
            )
            duration_ms = duration_milliseconds(result.duration_seconds)
        except SynthesisMediaError as exc:
            return JSONResponse({"code": exc.code}, status_code=exc.status_code)
        except Exception:
            return JSONResponse({"code": "voice_unavailable"}, status_code=503)
        return Response(
            content=result.audio,
            status_code=200,
            media_type=result.media_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Kei-Audio-Final": "true",
                "X-Kei-Audio-Duration-Ms": str(duration_ms),
                "X-Kei-Audio-Profile": result.output_profile,
                "X-Kei-Utterance-Id": result.utterance_id,
            },
        )

    @router.post("/api/v1/voice/chat", response_model=VoiceChatResponse)
    @router.post("/voice/chat", response_model=VoiceChatResponse, include_in_schema=False)
    async def voice_chat(
        request: Request,
        file: UploadFile = File(...),
        language: str = Form(default="zh"),
        vad_filter: bool = Form(default=False),
        include_audio_base64: bool = Form(default=False),
        split_tts: bool = Form(default=False),
    ):
        try:
            audio, filename, media_type = await read_limited_audio(file, max_upload_bytes)
            result = await service().chat(VoiceRequest(
                audio=audio,
                filename=filename,
                media_type=media_type,
                language=language,
                vad_filter=vad_filter,
                include_audio_base64=include_audio_base64,
                split_tts=split_tts,
            ))
        except VoiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.to_public_dict()) from exc
        prefix = audio_prefix(request)
        urls = [f"{prefix}/{item.filename}" for item in result.audio]
        return VoiceChatResponse(
            user_text=result.draft.user_text,
            assistant_text=result.draft.assistant_text,
            emotion=result.draft.emotion,
            audio_path=urls[0] if urls else "",
            audio_paths=urls,
            audio_base64=result.audio_base64,
            audio_available=bool(urls),
            mode=result.mode,
            degraded=result.degraded,
            errors=result.errors,
            timestamp=result.draft.timestamp,
            timings_ms=result.timings_ms,
            asr_segments=result.draft.asr_segments,
            asr_language=result.draft.asr_language,
            asr_language_probability=result.draft.asr_language_probability,
        )

    @router.post("/api/v1/voice/chat/stream")
    @router.post("/voice/chat/stream", include_in_schema=False)
    async def voice_chat_stream(
        request: Request,
        file: UploadFile = File(...),
        language: str = Form(default="zh"),
        vad_filter: bool = Form(default=False),
        split_tts: bool = Form(default=True),
    ):
        try:
            audio, filename, media_type = await read_limited_audio(file, max_upload_bytes)
        except VoiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.to_public_dict()) from exc
        prefix = audio_prefix(request)

        async def events():
            async for event in service().stream(
                VoiceRequest(
                    audio=audio,
                    filename=filename,
                    media_type=media_type,
                    language=language,
                    vad_filter=vad_filter,
                    split_tts=split_tts,
                ),
                disconnected=request.is_disconnected,
            ):
                payload = dict(event)
                if payload.get("event") == "audio_part":
                    filename_value = payload.pop("audio_filename")
                    url = f"{prefix}/{filename_value}"
                    payload.update({"audio_url": url, "audio_path": url})
                elif payload.get("event") == "done":
                    filenames = payload.pop("audio_filenames", [])
                    urls = [f"{prefix}/{item}" for item in filenames]
                    payload.update({"audio_path": urls[0] if urls else "", "audio_paths": urls})
                yield json.dumps(payload, ensure_ascii=False) + "\n"

        return StreamingResponse(events(), media_type="application/x-ndjson")

    @router.get("/api/v1/voice/audio/{filename}")
    @router.get("/voice/audio/{filename}", include_in_schema=False)
    async def get_voice_audio(filename: str):
        path = service().artifacts.resolve_audio(filename)
        if path is None:
            if Path(filename).name != filename or not filename.lower().endswith(".wav"):
                raise HTTPException(status_code=400, detail="Invalid audio filename")
            raise HTTPException(status_code=404, detail="Audio file not found")
        return FileResponse(path, media_type="audio/wav", filename=filename)

    return router
