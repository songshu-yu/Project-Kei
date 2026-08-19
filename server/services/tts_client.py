"""Compatibility import; PK-210 implementation lives in ``features.voice``."""

from features.voice.providers.tts_http import TTSClient, TTSConfig, split_text_for_tts

__all__ = ["TTSClient", "TTSConfig", "split_text_for_tts"]
