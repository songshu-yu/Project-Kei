"""Restart-time registration for the installable Voice Pack Registry."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .registry import VoicePackRegistry
from .router import create_voice_pack_router
from .security import (
    VOICE_PACK_API_PREFIX,
    VoicePackOriginGuardMiddleware,
    default_local_control_guard,
)
from .service import VoicePackRegistryService


def _server_root() -> Path:
    source = Path(__file__).resolve()
    for parent in source.parents:
        if parent.name == "server":
            return parent
    return source.parents[4]


def _existing_voice_pack_routes(app: Any) -> bool:
    return any(
        getattr(route, "path", "") == VOICE_PACK_API_PREFIX
        or getattr(route, "path", "").startswith(VOICE_PACK_API_PREFIX + "/")
        for route in getattr(app, "routes", ())
    )


def _has_origin_guard(app: Any) -> bool:
    return any(
        getattr(item, "cls", None) is VoicePackOriginGuardMiddleware
        for item in getattr(app, "user_middleware", ())
    )


def register(app: Any) -> None:
    """Register once, or defer to the frozen static routes during migration."""
    if getattr(app.state, "voice_pack_registry_module_registered", False):
        return
    if _existing_voice_pack_routes(app):
        app.state.voice_pack_registry_module_registered = True
        app.state.voice_pack_registry_module_mode = "existing_routes"
        return

    server_root = _server_root()
    registry_path = Path(
        getattr(
            app.state,
            "voice_pack_registry_path",
            os.getenv(
                "PROJECT_KEI_VOICE_PACK_REGISTRY",
                str(server_root / "data" / "voice_pack_registry.local.json"),
            ),
        )
    )
    runtime_root = Path(
        getattr(
            app.state,
            "voice_pack_runtime_root",
            server_root / "runtime" / "voice_packs",
        )
    )
    activator = getattr(app.state, "voice_pack_activator", None)
    local_control_guard = getattr(
        app.state,
        "voice_pack_local_control_guard",
        default_local_control_guard,
    )
    service = VoicePackRegistryService(
        VoicePackRegistry(registry_path),
        runtime_root=runtime_root,
        activator=activator,
    )
    if not _has_origin_guard(app):
        app.add_middleware(VoicePackOriginGuardMiddleware)
    app.include_router(
        create_voice_pack_router(
            lambda: service,
            local_control_guard=local_control_guard,
        )
    )

    def bind_activator(candidate: Any) -> None:
        service.activator = candidate
        resolver_setter = getattr(candidate, "set_voice_pack_resolver", None)
        if callable(resolver_setter):
            resolver_setter(service)

    app.state.voice_pack_registry_bind_activator = bind_activator
    if activator is not None:
        bind_activator(activator)
    resolver_consumer = getattr(app.state, "voice_pack_resolver_consumer", None)
    if callable(resolver_consumer):
        resolver_consumer(service)

    app.state.voice_pack_registry_service = service
    app.state.voice_pack_resolver = service
    app.state.voice_pack_registry_module_registered = True
    app.state.voice_pack_registry_module_mode = "installable"
