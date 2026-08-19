"""GPT-SoVITS engine provider and controlled-acquisition boundary (PK-211)."""

from .descriptor import DescriptorError, EngineDescriptor, load_descriptor
from .provider import GPTSoVITSConfig, GPTSoVITSProvider, TTSClient, TTSConfig, split_text_for_tts
from .acquisition import AcquisitionError, LocalEngineRegistry, acquire_builtin_engine, register_existing_install
from .sidecar_adapter import (
    ADAPTER_NAME,
    GPTSoVITSSidecarAdapter,
    SidecarAdapterError,
    register_gpt_sovits_sidecar,
)
from .local_selection import EngineSelectionError, LocalEngineSelectionService
from .selection_router import create_gpt_sovits_engine_router

__all__ = [
    "AcquisitionError",
    "ADAPTER_NAME",
    "DescriptorError",
    "EngineDescriptor",
    "EngineSelectionError",
    "GPTSoVITSConfig",
    "GPTSoVITSProvider",
    "GPTSoVITSSidecarAdapter",
    "LocalEngineRegistry",
    "LocalEngineSelectionService",
    "SidecarAdapterError",
    "TTSClient",
    "TTSConfig",
    "acquire_builtin_engine",
    "load_descriptor",
    "create_gpt_sovits_engine_router",
    "register_existing_install",
    "register_gpt_sovits_sidecar",
    "split_text_for_tts",
]
