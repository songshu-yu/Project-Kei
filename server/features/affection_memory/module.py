"""Installable-module registration entrypoint for affection and memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import create_context_provider
from .repository import MemoryRepository, RelationshipRepository
from .router import create_affection_memory_router
from .security import AffectionMemoryOriginGuardMiddleware
from .service import MemoryService, RelationshipService


OWNED_ROUTE_PATHS = frozenset(
    {
        "/api/v1/relationship/status",
        "/api/v1/relationship/events",
        "/api/v1/relationship/choices",
        "/api/v1/memories",
        "/api/v1/memories/{memory_id}",
        "/affection/status",
        "/affection/event",
        "/affection/choose",
        "/affection/reset",
        "/memories",
        "/memories/{memory_id}",
        "/memories/clear",
    }
)
_REGISTRATION_STATE = "affection_memory_module_registration_owner"
_MISSING = object()


def _remove_routes(app: Any, routes: tuple[Any, ...]) -> None:
    owned = {id(route) for route in routes}
    app.router.routes[:] = [route for route in app.router.routes if id(route) not in owned]


def _remove_middleware(app: Any, middleware: object | None) -> None:
    if middleware is None:
        return
    app.user_middleware[:] = [item for item in app.user_middleware if item is not middleware]


def _server_root() -> Path:
    """Resolve the server root in both source and installed layouts."""
    for parent in Path(__file__).resolve().parents:
        if parent.name == "server":
            return parent
    raise RuntimeError("affection_memory server root is unavailable")


def _existing_owned_routes(app: Any) -> set[str]:
    return {
        str(getattr(route, "path", ""))
        for route in getattr(app, "routes", ())
        if str(getattr(route, "path", "")) in OWNED_ROUTE_PATHS
    }


def register(app: Any) -> None:
    """Register routes and expose one app-scoped, read-only PK-200 provider."""
    if getattr(app.state, _REGISTRATION_STATE, None) is not None:
        return
    if getattr(app.state, "affection_memory_module_registered", False):
        return

    duplicates = _existing_owned_routes(app)
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise RuntimeError(f"affection_memory routes already registered: {names}")

    relationship_config = getattr(
        app.state, "affection_memory_relationship_path", None
    )
    memory_config = getattr(app.state, "affection_memory_memory_path", None)
    if relationship_config is None or memory_config is None:
        data_root = _server_root() / "data"
        relationship_config = (
            relationship_config or data_root / "affection_state.json"
        )
        memory_config = memory_config or data_root / "memories.json"
    relationship_path = Path(relationship_config)
    memory_path = Path(memory_config)
    relationship = RelationshipService(RelationshipRepository(relationship_path))
    memories = MemoryService(MemoryRepository(memory_path))
    provider = create_context_provider(relationship, memories)
    existing_provider = getattr(
        app.state, "conversation_context_provider", None
    )
    if existing_provider is not None:
        raise RuntimeError("conversation context provider is already registered")

    router_options: dict[str, Any] = {}
    audio_synthesizer = getattr(
        app.state, "affection_memory_audio_synthesizer", None
    )
    local_control_guard = getattr(
        app.state, "affection_memory_local_control_guard", None
    )
    local_read_guard = getattr(
        app.state, "affection_memory_local_read_guard", None
    )
    if audio_synthesizer is not None:
        router_options["audio_synthesizer"] = audio_synthesizer
    if local_control_guard is not None:
        router_options["local_control_guard"] = local_control_guard
    if local_read_guard is not None:
        router_options["local_read_guard"] = local_read_guard

    routes_before = {id(route) for route in app.router.routes}
    middleware_before = {id(item) for item in app.user_middleware}
    previous_context_provider = getattr(
        app.state, "affection_memory_context_provider", _MISSING
    )
    middleware = None
    try:
        app.include_router(
            create_affection_memory_router(relationship, memories, **router_options)
        )
        if not getattr(app.state, "affection_memory_origin_guard_registered", False):
            app.add_middleware(AffectionMemoryOriginGuardMiddleware)
            middleware = next(
                item for item in app.user_middleware if id(item) not in middleware_before
            )
            app.state.affection_memory_origin_guard_registered = True

        routes = tuple(route for route in app.router.routes if id(route) not in routes_before)
        registration = {
            "routes": routes,
            "middleware": middleware,
            "middleware_owned": middleware is not None,
            "provider": provider,
            "previous_context_provider": previous_context_provider,
        }
        # This is the package-owned composition seam.  It contains only the
        # structural get_context() provider, never a repository or mutable service.
        app.state.affection_memory_context_provider = provider
        app.state.conversation_context_provider = provider
        app.state.affection_memory_module_registered = True
        setattr(app.state, _REGISTRATION_STATE, registration)
    except BaseException:
        _remove_routes(
            app,
            tuple(route for route in app.router.routes if id(route) not in routes_before),
        )
        added_middleware = tuple(
            item for item in app.user_middleware if id(item) not in middleware_before
        )
        for item in added_middleware:
            _remove_middleware(app, item)
        if added_middleware and getattr(
            app.state, "affection_memory_origin_guard_registered", None
        ) is True:
            delattr(app.state, "affection_memory_origin_guard_registered")
        raise


def unregister(app: Any) -> None:
    """Remove only app seams and middleware owned by this module instance."""
    registration = getattr(app.state, _REGISTRATION_STATE, None)
    if not isinstance(registration, dict):
        return
    provider = registration["provider"]
    _remove_routes(app, registration["routes"])
    _remove_middleware(app, registration.get("middleware"))
    owned_state = [
        ("affection_memory_context_provider", provider),
        ("conversation_context_provider", provider),
        ("affection_memory_module_registered", True),
        (_REGISTRATION_STATE, registration),
    ]
    if registration.get("middleware_owned"):
        owned_state.append(("affection_memory_origin_guard_registered", True))
    for name, owned in owned_state:
        if getattr(app.state, name, object()) is owned:
            if name == "affection_memory_context_provider":
                previous = registration.get("previous_context_provider", _MISSING)
                if previous is not _MISSING:
                    setattr(app.state, name, previous)
                    continue
            delattr(app.state, name)


__all__ = ["OWNED_ROUTE_PATHS", "register", "unregister"]
