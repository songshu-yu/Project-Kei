"""Versioned and legacy HTTP routes sharing the PK-160 services."""

from __future__ import annotations

import base64
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request

from .models import MemoryAddRequest, RelationshipChoiceRequest, RelationshipEventRequest
from .repository import (
    MemoryPersistenceError,
    MemoryStateError,
    RelationshipPersistenceError,
    RelationshipStateError,
)
from .service import MemoryService, RelationshipService
from .security import default_local_control_guard


AudioSynthesizer = Callable[[str, str], Awaitable[Optional[bytes]]]
LocalControlGuard = Callable[[Request], bool]


def _require_local_control(request: Request, guard: LocalControlGuard) -> None:
    if not guard(request):
        raise HTTPException(status_code=403, detail="relationship and memory access is local-only")


def _relationship_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RelationshipStateError as exc:
        raise HTTPException(status_code=500, detail="relationship state is invalid") from exc
    except RelationshipPersistenceError as exc:
        raise HTTPException(status_code=500, detail="relationship state could not be saved") from exc


def _memory_call(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MemoryStateError as exc:
        raise HTTPException(status_code=500, detail="memory state is invalid") from exc
    except MemoryPersistenceError as exc:
        raise HTTPException(status_code=500, detail="memory state could not be saved") from exc


def create_affection_memory_router(
    relationship: RelationshipService,
    memories: MemoryService,
    *,
    audio_synthesizer: AudioSynthesizer | None = None,
    local_control_guard: LocalControlGuard = default_local_control_guard,
    local_read_guard: LocalControlGuard | None = None,
) -> APIRouter:
    router = APIRouter(tags=["affection-memory"])
    read_guard = local_read_guard or local_control_guard

    async def relationship_status(http_request: Request) -> dict:
        _require_local_control(http_request, read_guard)
        return _relationship_call(relationship.get_status)

    async def relationship_event(http_request: Request, request: RelationshipEventRequest) -> dict:
        _require_local_control(http_request, local_control_guard)
        result = _relationship_call(lambda: relationship.trigger_event(
            context=request.context,
            force_event=request.force_event,
            seed=request.seed,
        ))
        return result.to_dict()

    async def relationship_choice(http_request: Request, request: RelationshipChoiceRequest) -> dict:
        _require_local_control(http_request, local_control_guard)
        result = _relationship_call(lambda: relationship.choose_response(request.choice_id))
        payload = result.to_dict()
        payload["audio_base64"] = ""
        if result.reply and request.with_audio and audio_synthesizer is not None:
            audio = await audio_synthesizer(result.reply, "happy")
            if audio:
                payload["audio_base64"] = base64.b64encode(audio).decode("ascii")
        return payload

    async def legacy_relationship_reset(http_request: Request) -> dict:
        _require_local_control(http_request, local_control_guard)
        return {"status": "ok", "cleared_history": _relationship_call(relationship.reset)}

    async def list_memories(http_request: Request) -> dict:
        _require_local_control(http_request, read_guard)
        return _memory_call(memories.to_dict)

    async def add_memory(http_request: Request, request: MemoryAddRequest) -> dict:
        _require_local_control(http_request, local_control_guard)
        memory, created = _memory_call(lambda: memories.add_with_status(
            request.content,
            tags=request.tags,
            source=request.source,
            request_id=request.request_id,
        ))
        return {
            "status": "ok",
            "created": created,
            "duplicate": not created,
            "memory": memory.to_public_dict(),
        }

    async def delete_memory(http_request: Request, memory_id: str) -> dict:
        _require_local_control(http_request, local_control_guard)
        removed = _memory_call(lambda: memories.delete(memory_id))
        if removed is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"status": "ok", "memory": removed.to_public_dict()}

    async def legacy_clear_memories(http_request: Request) -> dict:
        _require_local_control(http_request, local_control_guard)
        return {"status": "ok", "cleared": _memory_call(memories.clear)}

    for group, prefix, event_path, choice_path in (
        ("versioned", "/api/v1/relationship", "events", "choices"),
        ("legacy", "/affection", "event", "choose"),
    ):
        router.add_api_route(f"{prefix}/status", relationship_status, methods=["GET"], name=f"relationship_status_{group}")
        router.add_api_route(f"{prefix}/{event_path}", relationship_event, methods=["POST"], name=f"relationship_event_{group}")
        router.add_api_route(f"{prefix}/{choice_path}", relationship_choice, methods=["POST"], name=f"relationship_choice_{group}")
    router.add_api_route("/affection/reset", legacy_relationship_reset, methods=["POST"], name="relationship_reset_legacy")

    for group, prefix in (("versioned", "/api/v1/memories"), ("legacy", "/memories")):
        router.add_api_route(prefix, list_memories, methods=["GET"], name=f"memories_list_{group}")
        router.add_api_route(prefix, add_memory, methods=["POST"], name=f"memories_add_{group}")
        router.add_api_route(f"{prefix}/{{memory_id}}", delete_memory, methods=["DELETE"], name=f"memories_delete_{group}")
    router.add_api_route("/memories/clear", legacy_clear_memories, methods=["POST"], name="memories_clear_legacy")
    return router


__all__ = ["create_affection_memory_router"]
