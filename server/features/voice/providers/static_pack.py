"""No-I/O compatibility resolver until PK-212 supplies the real registry."""
from __future__ import annotations

from ..errors import VoiceError
from ..models import ProviderCapabilities, ProviderHealth, VoicePackRef


class StaticVoicePackResolver:
    def __init__(self, voice_pack: VoicePackRef):
        self._voice_pack = voice_pack
        self._closed = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider="static-voice-pack-ref", operations=("resolve",), default_timeout_seconds=5.0)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(not self._closed, "available" if not self._closed else "closed")

    async def resolve_active_pack(self) -> VoicePackRef:
        if self._closed:
            raise VoiceError(stage="voice_pack", code="voice_pack_unavailable", message="Voice Pack 不可用", status_code=503)
        return self._voice_pack

    async def resolve_pack(self, pack_id: str) -> VoicePackRef:
        if pack_id != self._voice_pack.pack_id:
            raise VoiceError(stage="voice_pack", code="voice_pack_not_found", message="Voice Pack 不存在", status_code=404)
        return await self.resolve_active_pack()

    async def cancel(self, _request_id: str) -> None:
        return None

    async def close(self) -> None:
        self._closed = True
