"""Installable-module registration entrypoint for PK-210 voice."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Iterable

from core.calendar_contracts import calendar_summary_registry
from core.local_access import (
    TRUSTED_LOCAL_ORIGINS,
    is_loopback_host,
    is_trusted_local_origin,
)

from .control_router import create_voice_control_router
from .errors import failed, unavailable
from .models import ProviderCapabilities, ProviderHealth
from .router import create_voice_router
from .service import VoiceService
from .storage import VoiceArtifactStore


VOICE_ROUTE_PATHS = frozenset({
    "/api/v1/voice/health",
    "/api/v1/voice/chat",
    "/api/v1/voice/synthesize",
    "/api/v1/voice/chat/stream",
    "/api/v1/voice/audio/{filename}",
    "/voice/health",
    "/voice/chat",
    "/voice/chat/stream",
    "/voice/audio/{filename}",
    "/api/v1/voice-control/status",
    "/api/v1/voice-control/asr/start",
    "/api/v1/voice-control/asr/start-background",
    "/api/v1/voice-control/asr/stop",
    "/api/v1/voice-control/asr/model-directory/status",
    "/api/v1/voice-control/asr/model-directory/select",
    "/api/v1/voice-control/gpt-sovits/start",
    "/api/v1/voice-control/gpt-sovits/start-background",
    "/api/v1/voice-control/gpt-sovits/stop",
})


class ConversationServiceProvider:
    """Adapt only the public PK-200 service surface, without importing its package."""

    def __init__(self, service: Any):
        self._service = service
        self._active: dict[str, asyncio.Task[Any]] = {}
        self._closed = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="pk-200-conversation",
            operations=("chat",),
            default_timeout_seconds=120.0,
        )

    async def health(self) -> ProviderHealth:
        if self._closed:
            return ProviderHealth(
                False,
                "closed",
                error_code="conversation_closed",
            )
        try:
            await self._service.get_profile()
        except Exception:
            return ProviderHealth(
                False,
                "unavailable",
                error_code="conversation_unavailable",
            )
        return ProviderHealth(True, "available")

    async def chat(self, message: str, *, request_id: str):
        if self._closed:
            raise unavailable("conversation")
        task = asyncio.current_task()
        if task is not None:
            self._active[request_id] = task
        try:
            return await self._service.chat(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise failed("conversation") from exc
        finally:
            self._active.pop(request_id, None)

    async def cancel(self, request_id: str) -> None:
        task = self._active.get(request_id)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def close(self) -> None:
        self._closed = True
        for task in list(self._active.values()):
            if task is not asyncio.current_task():
                task.cancel()


class AppConversationProvider:
    """Resolve the strong conversation dependency after all modules are loaded."""

    def __init__(self, app: Any):
        self._app = app
        self._service_adapter: ConversationServiceProvider | None = None
        self._service_identity: Any = None
        self._closed = False

    def _provider(self) -> Any:
        provider = getattr(
            self._app.state,
            "voice_conversation_provider",
            None,
        )
        if provider is not None:
            return provider
        service = getattr(self._app.state, "conversation_service", None)
        if service is None:
            return None
        if service is not self._service_identity:
            self._service_identity = service
            self._service_adapter = ConversationServiceProvider(service)
        return self._service_adapter

    def capabilities(self) -> ProviderCapabilities:
        provider = self._provider()
        if provider is not None:
            try:
                return provider.capabilities()
            except Exception:
                pass
        return ProviderCapabilities(
            provider="pk-200-conversation",
            operations=("chat",),
            default_timeout_seconds=120.0,
        )

    async def health(self) -> ProviderHealth:
        if self._closed:
            return ProviderHealth(
                False,
                "closed",
                error_code="conversation_closed",
            )
        provider = self._provider()
        if provider is None:
            return ProviderHealth(
                False,
                "unavailable",
                error_code="conversation_unavailable",
            )
        try:
            return await provider.health()
        except Exception:
            return ProviderHealth(
                False,
                "unavailable",
                error_code="conversation_unavailable",
            )

    async def chat(self, message: str, *, request_id: str):
        if self._closed:
            raise unavailable("conversation")
        provider = self._provider()
        if provider is None:
            raise unavailable("conversation")
        return await provider.chat(message, request_id=request_id)

    async def cancel(self, request_id: str) -> None:
        provider = self._provider()
        if provider is not None:
            try:
                await provider.cancel(request_id)
            except Exception:
                pass

    async def close(self) -> None:
        self._closed = True
        if self._service_adapter is not None:
            await self._service_adapter.close()


_VOICE_PACK_RESOLVER_METHODS = (
    "health",
    "capabilities",
    "resolve_active_pack",
    "resolve_pack",
    "cancel",
    "close",
)


def _is_voice_pack_resolver(candidate: Any) -> bool:
    return candidate is not None and all(
        callable(getattr(candidate, name, None))
        for name in _VOICE_PACK_RESOLVER_METHODS
    )


class DynamicVoicePackResolver:
    """App-scoped atomic binding seam for independently loaded PK-212."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._resolver: Any = None
        self._active = True

    def bind(self, candidate: Any) -> bool:
        """Atomically bind a valid resolver, or unbind when passed ``None``."""

        with self._lock:
            if not self._active:
                return False
            if candidate is None:
                self._resolver = None
                return True
            if not _is_voice_pack_resolver(candidate):
                return False
            self._resolver = candidate
            return True

    def current(self) -> Any:
        with self._lock:
            return self._resolver if self._active else None

    def capabilities(self) -> ProviderCapabilities:
        resolver = self.current()
        if resolver is not None:
            try:
                return resolver.capabilities()
            except Exception:
                pass
        return ProviderCapabilities(
            provider="dynamic-voice-pack-resolver",
            operations=("resolve",),
            default_timeout_seconds=60.0,
        )

    async def health(self) -> ProviderHealth:
        resolver = self.current()
        if resolver is None:
            return ProviderHealth(
                False,
                "unavailable",
                error_code="voice_pack_unavailable",
            )
        try:
            return await resolver.health()
        except Exception:
            return ProviderHealth(
                False,
                "unavailable",
                error_code="voice_pack_unavailable",
            )

    async def resolve_active_pack(self):
        resolver = self.current()
        if resolver is None:
            raise unavailable("voice_pack")
        return await resolver.resolve_active_pack()

    async def resolve_pack(self, pack_id: str):
        resolver = self.current()
        if resolver is None:
            raise unavailable("voice_pack")
        return await resolver.resolve_pack(pack_id)

    async def cancel(self, request_id: str) -> None:
        resolver = self.current()
        if resolver is not None:
            try:
                await resolver.cancel(request_id)
            except Exception:
                pass

    async def close(self) -> None:
        # PK-212 owns its service lifecycle. Voice only closes this binding seam.
        self.deactivate()

    def deactivate(self) -> None:
        with self._lock:
            self._active = False
            self._resolver = None


def _route_paths(app: Any) -> Iterable[str]:
    return (
        route.path
        for route in getattr(app, "routes", ())
        if isinstance(getattr(route, "path", None), str)
    )


def _conversation_provider(app: Any) -> Any:
    return AppConversationProvider(app)


def _request_origin(request: Any) -> str | None:
    values = request.headers.getlist("origin")
    if len(values) > 1:
        return ""
    return values[0] if values else None


def _voice_control_read_allowed(request: Any) -> bool:
    client = getattr(request, "client", None)
    return (
        client is not None
        and is_loopback_host(getattr(client, "host", None))
        and is_trusted_local_origin(_request_origin(request))
    )


def _voice_control_write_allowed(request: Any) -> bool:
    client = getattr(request, "client", None)
    return (
        client is not None
        and is_loopback_host(getattr(client, "host", None))
        and _request_origin(request) in TRUSTED_LOCAL_ORIGINS
    )


def register(app: Any) -> None:
    if getattr(app.state, "voice_module_registered", False):
        return
    conflicts = VOICE_ROUTE_PATHS.intersection(_route_paths(app))
    if conflicts:
        joined = ", ".join(sorted(conflicts))
        raise RuntimeError(f"voice routes are already registered: {joined}")

    data_root = Path(
        getattr(
            app.state,
            "voice_data_root",
            Path("data") / "modules" / "voice",
        )
    )
    artifacts = VoiceArtifactStore(data_root / "tmp", data_root / "output")
    resolver_binding = DynamicVoicePackResolver()
    resolver_binding.bind(getattr(app.state, "voice_pack_resolver", None))
    previous_resolver_consumer = getattr(
        app.state,
        "voice_pack_resolver_consumer",
        None,
    )

    def consume_voice_pack_resolver(candidate: Any) -> None:
        if callable(previous_resolver_consumer):
            try:
                previous_resolver_consumer(candidate)
            except Exception:
                # A separate delayed consumer cannot corrupt PK-210's binding.
                pass
        resolver_binding.bind(candidate)

    service = VoiceService(
        asr=getattr(app.state, "voice_asr_provider", None),
        conversation=_conversation_provider(app),
        tts=getattr(app.state, "voice_tts_provider", None),
        voice_packs=resolver_binding,
        utterance_encoder=getattr(app.state, "voice_utterance_encoder", None),
        artifacts=artifacts,
    )
    app.include_router(create_voice_router(lambda: service))
    app.include_router(create_voice_control_router(
        lambda: getattr(app.state, "voice_runtime_control_provider", None),
        read_guard=_voice_control_read_allowed,
        write_guard=_voice_control_write_allowed,
    ))
    app.state.voice_service = service
    app.state.voice_module_service_owner = service
    app.state.voice_pack_resolver_binding = resolver_binding
    app.state.voice_pack_resolver_consumer = consume_voice_pack_resolver
    app.state.voice_pack_resolver_consumer_owner = consume_voice_pack_resolver
    app.state.voice_pack_resolver_consumer_previous = previous_resolver_consumer
    app.state.voice_calendar_provider_registry = calendar_summary_registry
    calendar_provider = getattr(app.state, "calendar_summary_provider", None)
    if calendar_provider is not None:
        calendar_summary_registry.register_calendar_summary_provider(
            calendar_provider
        )
    app.state.voice_module_registered = True


async def unregister(app: Any) -> None:
    """Await module-owned cleanup, then release only PK-210 app-state seams."""

    owner = getattr(app.state, "voice_module_service_owner", None)
    close_task = getattr(app.state, "voice_module_close_task", None)
    if close_task is None and isinstance(owner, VoiceService):
        close_task = asyncio.create_task(owner.close())
        app.state.voice_module_close_task = close_task
    if close_task is not None:
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Shutdown remains deterministic even if a custom provider misbehaves.
            pass
        if not close_task.done():
            return

    binding = getattr(app.state, "voice_pack_resolver_binding", None)
    if isinstance(binding, DynamicVoicePackResolver):
        binding.deactivate()
    installed_consumer = getattr(
        app.state,
        "voice_pack_resolver_consumer_owner",
        None,
    )
    current_consumer = getattr(
        app.state,
        "voice_pack_resolver_consumer",
        None,
    )
    if current_consumer is installed_consumer:
        previous = getattr(
            app.state,
            "voice_pack_resolver_consumer_previous",
            None,
        )
        if callable(previous):
            app.state.voice_pack_resolver_consumer = previous
        elif hasattr(app.state, "voice_pack_resolver_consumer"):
            delattr(app.state, "voice_pack_resolver_consumer")
    if (
        owner is not None
        and getattr(app.state, "voice_service", None) is owner
        and hasattr(app.state, "voice_service")
    ):
        delattr(app.state, "voice_service")
    for name in (
        "voice_calendar_provider_registry",
        "voice_pack_resolver_binding",
        "voice_pack_resolver_consumer_owner",
        "voice_pack_resolver_consumer_previous",
        "voice_module_close_task",
        "voice_module_service_owner",
        "voice_module_registered",
    ):
        if hasattr(app.state, name):
            delattr(app.state, name)


__all__ = [
    "AppConversationProvider",
    "ConversationServiceProvider",
    "DynamicVoicePackResolver",
    "VOICE_ROUTE_PATHS",
    "register",
    "unregister",
]
