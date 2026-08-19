"""Bounded PCM normalization and one-shot utterance encoding for PK-210."""
from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import Protocol, Sequence

from .models import (
    AudioResult,
    AudioSegment,
    EncodedUtterance,
    PcmUtterance,
    SynthesisTextSegment,
    SynthesizedUtterance,
)


OUTPUT_PROFILE = "qq_c2c_voice_v1"
OUTPUT_MEDIA_TYPE = "audio/silk"
TARGET_SAMPLE_RATE = 24_000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2
DEFAULT_MAX_DURATION_SECONDS = 60.0
DEFAULT_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_PROVIDER_BYTES = 12 * 1024 * 1024
SUPPORTED_WAVE_TYPES = frozenset({"audio/wav", "audio/x-wav", "audio/vnd.wave"})


class SynthesisMediaError(RuntimeError):
    def __init__(self, code: str, status_code: int = 502) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def duration_milliseconds(duration_seconds: float) -> int:
    """Return the conservative public duration after validating the utterance."""
    if (
        not isinstance(duration_seconds, (int, float))
        or isinstance(duration_seconds, bool)
        or not math.isfinite(duration_seconds)
        or duration_seconds <= 0
        or duration_seconds > DEFAULT_MAX_DURATION_SECONDS
    ):
        raise SynthesisMediaError("audio_invalid")
    value = math.ceil(duration_seconds * 1000)
    if not 1 <= value <= 60_000:
        raise SynthesisMediaError("audio_invalid")
    return value


@dataclass(frozen=True)
class PcmAudio:
    samples: tuple[int, ...]
    sample_rate: int


class PcmDecoder(Protocol):
    def __call__(self, audio: bytes, media_type: str, audio_format: str) -> PcmAudio: ...


def _decode_sample(raw: bytes, width: int) -> int:
    if width == 1:
        return (raw[0] - 128) << 8
    value = int.from_bytes(raw, "little", signed=True)
    if width == 2:
        return value
    if width == 3:
        return max(-32768, min(32767, value >> 8))
    if width == 4:
        return max(-32768, min(32767, value >> 16))
    raise SynthesisMediaError("audio_invalid")


def decode_pcm_wave(audio: bytes, media_type: str, audio_format: str) -> PcmAudio:
    normalized_type = str(media_type or "").split(";", 1)[0].strip().lower()
    if normalized_type not in SUPPORTED_WAVE_TYPES or str(audio_format).lower() != "wav":
        raise SynthesisMediaError("audio_invalid")
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            channels = source.getnchannels()
            width = source.getsampwidth()
            sample_rate = source.getframerate()
            frames = source.getnframes()
            if (
                source.getcomptype() != "NONE"
                or channels not in {1, 2}
                or width not in {1, 2, 3, 4}
                or not 8_000 <= sample_rate <= 96_000
                or frames <= 0
            ):
                raise SynthesisMediaError("audio_invalid")
            raw = source.readframes(frames)
    except SynthesisMediaError:
        raise
    except Exception as exc:
        raise SynthesisMediaError("audio_invalid") from exc
    frame_width = channels * width
    if len(raw) != frames * frame_width:
        raise SynthesisMediaError("audio_invalid")
    mono: list[int] = []
    for offset in range(0, len(raw), frame_width):
        values = [
            _decode_sample(raw[offset + channel * width:offset + (channel + 1) * width], width)
            for channel in range(channels)
        ]
        mono.append(int(sum(values) / channels))
    return PcmAudio(tuple(mono), sample_rate)


def _resample(samples: Sequence[int], source_rate: int) -> list[int]:
    if source_rate == TARGET_SAMPLE_RATE:
        return list(samples)
    count = max(1, int(round(len(samples) * TARGET_SAMPLE_RATE / source_rate)))
    output: list[int] = []
    for index in range(count):
        position = index * source_rate / TARGET_SAMPLE_RATE
        left = min(int(position), len(samples) - 1)
        right = min(left + 1, len(samples) - 1)
        fraction = position - left
        output.append(int(samples[left] * (1.0 - fraction) + samples[right] * fraction))
    return output


def _normalize(samples: Sequence[int]) -> list[int]:
    threshold = 256
    first = next((index for index, value in enumerate(samples) if abs(value) > threshold), None)
    if first is None:
        raise SynthesisMediaError("audio_invalid")
    last = len(samples) - next(
        index for index, value in enumerate(reversed(samples)) if abs(value) > threshold
    )
    trimmed = list(samples[first:last])
    peak = max(abs(value) for value in trimmed)
    rms = math.sqrt(sum(value * value for value in trimmed) / len(trimmed))
    target_rms = 0.125 * 32767
    target_peak = 0.85 * 32767
    scale = min(8.0, target_rms / max(rms, 1.0), target_peak / max(peak, 1))
    normalized = [max(-32768, min(32767, int(value * scale))) for value in trimmed]
    fade_samples = min(len(normalized) // 2, int(TARGET_SAMPLE_RATE * 0.005))
    for index in range(fade_samples):
        gain = (index + 1) / fade_samples
        normalized[index] = int(normalized[index] * gain)
        normalized[-index - 1] = int(normalized[-index - 1] * gain)
    return normalized


class PcmUtterancePipeline:
    """Validate segments and normalize them into one bounded logical utterance."""

    def __init__(
        self,
        *,
        decoder: PcmDecoder = decode_pcm_wave,
        max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        max_provider_bytes: int = DEFAULT_MAX_PROVIDER_BYTES,
    ) -> None:
        self.decoder = decoder
        self.max_duration_seconds = max_duration_seconds
        self.max_output_bytes = max_output_bytes
        self.max_provider_bytes = max_provider_bytes

    @staticmethod
    def _ordered_segments(
        result: AudioResult,
        expected: Sequence[SynthesisTextSegment],
    ) -> list[AudioSegment]:
        if not result.segments:
            if not result.audio:
                raise SynthesisMediaError("audio_invalid")
            return [AudioSegment("utterance", 0, result.audio, result.media_type, result.audio_format)]
        if len(result.segments) != len(expected):
            raise SynthesisMediaError("audio_invalid")
        seen: set[str] = set()
        ordered: list[AudioSegment] = []
        for index, (actual, planned) in enumerate(zip(result.segments, expected)):
            if (
                actual.sequence != index
                or planned.sequence != index
                or actual.segment_id != planned.segment_id
                or actual.segment_id in seen
            ):
                raise SynthesisMediaError("audio_invalid")
            seen.add(actual.segment_id)
            ordered.append(actual)
        return ordered

    def prepare(
        self,
        result: AudioResult,
        expected: Sequence[SynthesisTextSegment],
    ) -> PcmUtterance:
        segments = self._ordered_segments(result, expected)
        provider_bytes = sum(len(segment.audio) for segment in segments)
        if provider_bytes <= 0:
            raise SynthesisMediaError("audio_invalid")
        if provider_bytes > self.max_provider_bytes:
            raise SynthesisMediaError("audio_too_large", 413)
        normalized: list[list[int]] = []
        total_samples = 0
        for segment in segments:
            decoded = self.decoder(segment.audio, segment.media_type, segment.audio_format)
            if not decoded.samples:
                raise SynthesisMediaError("audio_invalid")
            samples = _normalize(_resample(decoded.samples, decoded.sample_rate))
            normalized.append(samples)
            total_samples += len(samples)
        silence = [0] * int(TARGET_SAMPLE_RATE * 0.06)
        total_samples += max(0, len(normalized) - 1) * len(silence)
        duration = total_samples / TARGET_SAMPLE_RATE
        if duration > self.max_duration_seconds:
            raise SynthesisMediaError("audio_too_large", 413)
        merged: list[int] = []
        for index, samples in enumerate(normalized):
            if index:
                merged.extend(silence)
            merged.extend(samples)
        pcm = struct.pack(f"<{len(merged)}h", *merged)
        return PcmUtterance(
            pcm_s16le=pcm,
            sample_rate=TARGET_SAMPLE_RATE,
            channels=TARGET_CHANNELS,
            sample_width=TARGET_SAMPLE_WIDTH,
            duration_seconds=duration,
        )

    def finalize(
        self,
        encoded: EncodedUtterance,
        pcm: PcmUtterance,
        *,
        utterance_id: str,
    ) -> SynthesizedUtterance:
        if (
            encoded.output_profile != OUTPUT_PROFILE
            or encoded.media_type != OUTPUT_MEDIA_TYPE
            or not encoded.audio
        ):
            raise SynthesisMediaError("audio_invalid")
        if len(encoded.audio) > self.max_output_bytes:
            raise SynthesisMediaError("audio_too_large", 413)
        duration_milliseconds(pcm.duration_seconds)
        return SynthesizedUtterance(
            encoded.audio,
            OUTPUT_MEDIA_TYPE,
            OUTPUT_PROFILE,
            pcm.duration_seconds,
            utterance_id,
            True,
            pcm,
        )


__all__ = [
    "OUTPUT_MEDIA_TYPE",
    "OUTPUT_PROFILE",
    "PcmAudio",
    "PcmUtterancePipeline",
    "SynthesisMediaError",
    "duration_milliseconds",
]
