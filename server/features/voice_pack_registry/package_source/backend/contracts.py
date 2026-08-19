"""Structural PK-210 values used by the self-contained Voice Pack package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


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
class VoicePackRef:
    """Structural equivalent of the public PK-210 opaque reference."""

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


class VoiceError(Exception):
    """Path-safe error shape consumed by the PK-210 voice boundary."""

    def __init__(
        self,
        *,
        stage: str,
        code: str,
        message: str,
        status_code: int = 500,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
