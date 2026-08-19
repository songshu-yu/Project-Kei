"""Built-in compatibility providers for the PK-210 contracts."""

from .asr_http import ASRClient, ASRConfig
from .conversation import ConversationServiceProvider
from .gpt_sovits import GPTSoVITSConfig, GPTSoVITSProvider
from .static_pack import StaticVoicePackResolver
from .tts_http import TTSClient, TTSConfig, split_text_for_tts

__all__ = [
    "ASRClient",
    "ASRConfig",
    "ConversationServiceProvider",
    "GPTSoVITSConfig",
    "GPTSoVITSProvider",
    "StaticVoicePackResolver",
    "TTSClient",
    "TTSConfig",
    "split_text_for_tts",
]
