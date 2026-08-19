"""Public, path-safe models for the Project Kei voice boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    operations: tuple[str, ...]
    audio_formats: tuple[str, ...] = ()
    streaming: bool = False
    cancellable: bool = True
    default_timeout_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "operations": list(self.operations),
            "audio_formats": list(self.audio_formats),
            "streaming": self.streaming,
            "cancellable": self.cancellable,
            "default_timeout_seconds": self.default_timeout_seconds,
        }


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    status: str
    latency_ms: Optional[int] = None
    error_code: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class TranscriptionRequest:
    request_id: str
    audio: bytes = field(repr=False)
    filename: str = "audio.wav"
    media_type: str = "audio/wav"
    language: str = "zh"
    vad_filter: bool = False
    timeout_seconds: float = 180.0


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str = ""
    language_probability: float = 0.0
    duration: float = 0.0
    segments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class VoicePackRef:
    """Minimal cross-task reference. ``handle`` is opaque and never serialized."""

    pack_id: str
    pack_version: str
    engine_provider: str
    handle: Any = field(default=None, repr=False, compare=False)

    def to_public_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "engine_provider": self.engine_provider,
        }


@dataclass(frozen=True)
class SynthesisRequest:
    request_id: str
    text: str
    emotion: str = "calm"
    audio_format: str = "wav"
    timeout_seconds: float = 60.0
    segments: tuple["SynthesisTextSegment", ...] = ()


@dataclass(frozen=True)
class SynthesisTextSegment:
    segment_id: str
    sequence: int
    text: str


@dataclass(frozen=True)
class AudioSegment:
    segment_id: str
    sequence: int
    audio: bytes = field(repr=False)
    media_type: str = "audio/wav"
    audio_format: str = "wav"


@dataclass(frozen=True)
class AudioResult:
    audio: bytes = field(repr=False)
    media_type: str = "audio/wav"
    audio_format: str = "wav"
    duration: Optional[float] = None
    segments: tuple[AudioSegment, ...] = ()


@dataclass(frozen=True)
class PcmUtterance:
    pcm_s16le: bytes = field(repr=False)
    sample_rate: int
    channels: int
    sample_width: int
    duration_seconds: float


@dataclass(frozen=True)
class UtteranceEncodingRequest:
    request_id: str
    utterance_id: str
    output_profile: str
    pcm_s16le: bytes = field(repr=False)
    sample_rate: int = 24_000
    channels: int = 1
    sample_width: int = 2
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class EncodedUtterance:
    audio: bytes = field(repr=False)
    media_type: str
    output_profile: str


@dataclass(frozen=True)
class SynthesizedUtterance:
    audio: bytes = field(repr=False)
    media_type: str
    output_profile: str
    duration_seconds: float
    utterance_id: str
    final: bool = True
    pcm: Optional[PcmUtterance] = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class VoiceRequest:
    audio: bytes = field(repr=False)
    filename: str = "audio.wav"
    media_type: str = "audio/wav"
    language: str = "zh"
    vad_filter: bool = False
    include_audio_base64: bool = False
    split_tts: bool = False


@dataclass(frozen=True)
class VoiceDraft:
    request_id: str
    user_text: str
    assistant_text: str
    emotion: str
    timestamp: str
    timings_ms: Dict[str, int]
    asr_segments: List[Dict[str, Any]]
    asr_language: str
    asr_language_probability: float


@dataclass(frozen=True)
class PublishedAudio:
    filename: str
    text: str
    index: int
    total: int
    elapsed_ms: int


@dataclass(frozen=True)
class VoiceResult:
    draft: VoiceDraft
    audio: List[PublishedAudio]
    audio_base64: str
    timings_ms: Dict[str, int]
    mode: str
    degraded: bool
    errors: List[dict]


class VoiceChatResponse(BaseModel):
    user_text: str
    assistant_text: str
    emotion: str
    audio_path: str = ""
    audio_paths: List[str] = Field(default_factory=list)
    audio_base64: str = ""
    audio_available: bool = False
    mode: str = "text_only"
    degraded: bool = False
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str
    timings_ms: dict
    asr_segments: list = Field(default_factory=list)
    asr_language: str = ""
    asr_language_probability: float = 0.0


class VoiceHealthResponse(BaseModel):
    status: str
    providers: dict
