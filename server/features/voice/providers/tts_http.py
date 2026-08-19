"""Compatibility exports for the PK-211 GPT-SoVITS provider."""

from .gpt_sovits import (
    GPTSoVITSConfig,
    GPTSoVITSProvider,
    TTSClient,
    TTSConfig,
    split_text_for_tts,
)

__all__ = [
    "GPTSoVITSConfig",
    "GPTSoVITSProvider",
    "TTSClient",
    "TTSConfig",
    "split_text_for_tts",
]
