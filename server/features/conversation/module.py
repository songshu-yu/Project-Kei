"""Installable-module registration entrypoint for conversation."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Any

from .composition import create_conversation_service
from .context import AppStateConversationContextProvider
from .router import create_conversation_router


DECLARED_ROUTE_PATHS = frozenset({
    "/api/v1/conversation",
    "/api/v1/conversation/history",
    "/api/v1/llm-profile",
    "/chat",
    "/chat/text-only",
    "/history",
    "/history/clear",
    "/ws/chat",
    "/dashboard/llm/profile",
})
TRUSTED_LOCAL_ORIGINS = frozenset({
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://[::1]:8000",
})


class _ConversationModuleOwnership:
    def __init__(self, service: Any):
        self.service = service
        self.text_generator_provider = lambda: service
        self.close_callback = service.close


def _is_loopback_request(request: Any) -> bool:
    client = getattr(request, "client", None)
    host = getattr(client, "host", "") if client is not None else ""
    try:
        if not ipaddress.ip_address(str(host).split("%", 1)[0]).is_loopback:
            return False
    except ValueError:
        return False
    origin = request.headers.get("origin")
    return origin is None or origin in TRUSTED_LOCAL_ORIGINS


def _default_profile() -> dict[str, Any]:
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    return {
        "provider": "deepseek" if "api.deepseek.com" in base_url.casefold() else "custom",
        "base_url": base_url,
        "model": model,
        "thinking_mode": "disabled",
        "updated_at": None,
    }


def _server_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name.casefold() == "server":
            return parent
    return Path.cwd()


def _create_service(app: Any):
    factory = getattr(app.state, "conversation_service_factory", None)
    if factory is not None:
        service = factory()
        if service is None:
            raise RuntimeError("conversation service factory returned no service")
        return service

    profile_path = getattr(
        app.state,
        "conversation_profile_path",
        Path(os.getenv(
            "PROJECT_KEI_LLM_PROFILE_PATH",
            str(_server_root() / "data" / "llm_profile.json"),
        )),
    )
    return create_conversation_service(
        api_key=os.getenv("LLM_API_KEY", ""),
        default_profile=getattr(
            app.state,
            "conversation_default_profile",
            _default_profile(),
        ),
        profile_path=profile_path,
        context_provider=AppStateConversationContextProvider(app),
        max_history=getattr(app.state, "conversation_max_history", 20),
    )


def _assert_routes_available(app: Any) -> None:
    conflicts = sorted({
        route.path
        for route in app.routes
        if getattr(route, "path", None) in DECLARED_ROUTE_PATHS
    })
    if conflicts:
        raise RuntimeError(
            "conversation routes are already registered: " + ", ".join(conflicts)
        )


def register(app: Any) -> None:
    """Register one service instance and every versioned/legacy route exactly once."""

    if getattr(app.state, "conversation_module_registered", False):
        return
    _assert_routes_available(app)
    service = _create_service(app)
    ownership = _ConversationModuleOwnership(service)
    app.state._conversation_module_ownership = ownership
    local_control_guard = getattr(
        app.state,
        "conversation_local_control_guard",
        _is_loopback_request,
    )
    local_read_guard = getattr(
        app.state,
        "conversation_local_read_guard",
        local_control_guard,
    )
    app.include_router(create_conversation_router(
        lambda: service,
        local_control_guard=local_control_guard,
        local_read_guard=local_read_guard,
        include_legacy=True,
        legacy_command_handler=getattr(
            app.state,
            "conversation_legacy_command_handler",
            None,
        ),
        audio_synthesizer=getattr(
            app.state,
            "conversation_audio_synthesizer",
            None,
        ),
    ))
    app.state.conversation_service = service
    app.state.conversation_text_generator_provider = (
        ownership.text_generator_provider
    )
    app.state.conversation_service_close = ownership.close_callback
    app.state.conversation_module_registered = ownership


def _remove_owned_state(app: Any, name: str, expected: Any) -> None:
    try:
        if getattr(app.state, name, None) is expected:
            delattr(app.state, name)
    except Exception:
        pass


async def unregister(app: Any) -> None:
    """Close this registration and remove only state references it still owns."""

    ownership = getattr(
        app.state,
        "_conversation_module_ownership",
        None,
    )
    if not isinstance(ownership, _ConversationModuleOwnership):
        return

    close_failed = False
    try:
        await ownership.close_callback()
    except Exception:
        close_failed = True
    finally:
        _remove_owned_state(
            app,
            "conversation_service",
            ownership.service,
        )
        _remove_owned_state(
            app,
            "conversation_text_generator_provider",
            ownership.text_generator_provider,
        )
        _remove_owned_state(
            app,
            "conversation_service_close",
            ownership.close_callback,
        )
        _remove_owned_state(
            app,
            "conversation_module_registered",
            ownership,
        )
        _remove_owned_state(
            app,
            "_conversation_module_ownership",
            ownership,
        )
    if close_failed:
        raise RuntimeError("conversation service cleanup failed") from None


__all__ = ["DECLARED_ROUTE_PATHS", "register", "unregister"]
