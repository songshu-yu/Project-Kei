"""Compatibility import; PK-210 implementation lives in ``features.voice``."""

from features.voice.providers.asr_http import ASRClient, ASRConfig, ASRResult

__all__ = ["ASRClient", "ASRConfig", "ASRResult"]
